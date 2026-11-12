"""Actual local GUI and worker restart checks with isolated synthetic workspaces."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from mission_control.db import connection
from mission_control.server import Server
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import jobs, run_once


def start(path):
    server = Server(("127.0.0.1", 0), Store(path))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, "http://127.0.0.1:" + str(server.server_port)


def stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join()


def choose(page, origin):
    page.goto(origin)
    page.wait_for_function('(context) => {const state=context.state;return (() => state.workspace?.app?.id===state.app)(context.original);}', arg={'state': page.evaluate_handle("async () => (await import('/app.mjs')).state"), 'original': None})
    page.locator("#app-select").select_option("sample-one")
    page.get_by_role("button", name="Find a useful marketing angle", exact=True).click()
    page.get_by_role("button", name="Open your first packet", exact=True).press("Enter")


def run(browser, width, out):
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "state.sqlite"
        server, thread, origin = start(path)
        context = browser.new_context(viewport=dict(width=width, height=1000))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            choose(page, origin)
            dialog = page.get_by_role("dialog")
            page.get_by_role("button", name="Save packet in this workspace", exact=True).press("Enter")
            expect(dialog).to_contain_text("Preparing a local draft")
            first = jobs(server.service.store, "sample-one")[0]
            assert first["status"] == "QUEUED"
            run_once(server.service.store)
            page.get_by_role("button", name="Refresh saved packet", exact=True).press("Enter")
            expect(dialog).to_contain_text("Saved local draft — current source matches")
            expect(dialog).to_contain_text(first["id"])
            with page.expect_download() as downloaded:
                page.get_by_role("button", name="Download saved packet JSON", exact=True).click()
            saved = json.loads(Path(downloaded.value.path()).read_text(encoding="utf-8"))
            assert saved["packet_id"] == first["id"] and len(saved["outputs"]) == 2
            snapshot_hash = saved["source_hash"]
            page.get_by_role("button", name="Open current packet", exact=True).click()
            page.get_by_role("button", name="Save packet in this workspace", exact=True).click()
            expect(dialog).to_contain_text(first["id"])
            assert len(jobs(server.service.store, "sample-one")) == 1

            stop(server, thread)
            server, thread, origin = start(path)
            choose(page, origin)
            page.get_by_role("button", name="Open saved packet", exact=True).press("Enter")
            expect(dialog).to_contain_text(first["id"])
            expect(dialog).to_contain_text("Saved local draft — current source matches")
            Service(server.service.store).evidence(
                "sample-one",
                dict(
                    kind="learning",
                    title="Synthetic changed evidence",
                    source="Browser fixture",
                    data=dict(change="Changed", heldout_test="Synthetic", rollback="Synthetic", result="NOT_RUN"),
                ),
            )
            page.get_by_role("button", name="Refresh saved packet", exact=True).press("Enter")
            expect(dialog).to_contain_text("Historical snapshot")
            with page.expect_popup() as opened:
                page.get_by_role("button", name="Report / Save PDF", exact=True).click()
            report = opened.value
            expect(report.locator("body")).to_contain_text(snapshot_hash)
            expect(report.locator("body")).to_contain_text("Measured campaign outcomes")
            expect(report.locator("body")).to_contain_text("Unavailable")
            pdf = report.pdf(path=str(out / f"saved-packet-{width}.pdf"))
            assert pdf.startswith(b"%PDF")
            report.close()
            dialog.locator(".modal-content").evaluate("(node) => node.scrollTop=0")
            page.screenshot(path=str(out / f"historical-{width}.png"), full_page=True)
            css = page.evaluate(
                "() => [...document.styleSheets].map(s => [...s.cssRules].map(r => r.cssText).join(String.fromCharCode(10))).join(String.fromCharCode(10))"
            )
            html = page.content().replace(
                "</head>", '<style data-audit="actual-loaded-styles">' + css + "</style></head>"
            )
            (out / f"historical-{width}.html").write_text(html, encoding="utf-8")

            page.get_by_role("button", name="Open current packet", exact=True).click()
            page.get_by_role("button", name="Save packet in this workspace", exact=True).click()
            expect(dialog).to_contain_text("Preparing a local draft")
            pending = jobs(server.service.store, "sample-one")[0]
            assert pending["id"] != first["id"]
            with connection(server.service.store.path) as db:
                db.execute(
                    "UPDATE jobs SET status='FAILED',result=? WHERE id=?",
                    (json.dumps(dict(error="Synthetic terminal failure")), pending["id"]),
                )
            page.get_by_role("button", name="Refresh saved packet", exact=True).click()
            expect(dialog).to_contain_text("Packet was not saved")
            expect(dialog).not_to_contain_text("Preparing a local draft")
            expect(dialog.locator('[data-action="automatic-goal-saved-json"]')).to_have_count(0)
            assert not errors, errors
            return dict(
                width=width,
                browser=browser.version,
                job_id=first["id"],
                snapshot_hash=snapshot_hash,
                actual_runtime_restart=True,
                duplicate_save_single_job=True,
                historical_visible=True,
                terminal_failure_not_pending=True,
                keyboard=True,
                pdf_sha256=hashlib.sha256(pdf).hexdigest(),
                data="SYNTHETIC_TEMPORARY_WORKSPACE",
                external_effects=0,
            )
        finally:
            context.close()
            stop(server, thread)


def main():
    out = ROOT / ".factory/goal-packet-history"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            result = dict(status="PASS", observations=[run(browser, width, out) for width in (1440, 390)])
        finally:
            browser.close()
    (out / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
