"""Real desktop/mobile page reports and PDFs using isolated synthetic app data."""
from pathlib import Path
import json
import platform
import sys
import tempfile
import threading
import fitz
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mission_control.server import Server
from mission_control.store import Store
from playwright.sync_api import sync_playwright, expect
from tests.test_mission_control import evidence_data


def seed(store):
    for identity, name in (("sample-one", "Synthetic Café 東京"), ("sample-two", "Other synthetic workspace")):
        store.save_app(identity, dict(name=name, job="Synthetic task", audience="Test", activation="Saved step", release="build-1", locale="en-US"))
    store.save_record("sample-one", dict(kind="cohort", title="Supplied pilot", source="Synthetic fixture only",
        manifest_version=store.app("sample-one")["version"], data=evidence_data("cohort")))


def snapshot_html(page, target, css):
    html = page.content().replace("</head>", "<style>" + css + "</style></head>")
    target.write_text(html, encoding="utf-8")


def export_report(page, view, width, out):
    page.locator("[data-report-page]").focus()
    with page.expect_popup() as waiting:
        page.keyboard.press("Enter")
    popup = waiting.value
    popup.locator("h1").wait_for()
    popup.wait_for_load_state("load")
    assert popup.evaluate("window.opener===null")
    assert not popup.locator("input,textarea").count()
    assert "PRIVATE_SENTINEL" not in popup.content()
    popup.evaluate("window.print=()=>{window.printRequested=true}")
    popup.get_by_role("button", name="Print / Save as PDF", exact=True).focus()
    popup.keyboard.press("Enter")
    assert popup.evaluate("window.printRequested===true")
    pdf_path = out / f"{view}-{width}.pdf"
    popup.pdf(path=str(pdf_path), format="A4", print_background=True)
    with fitz.open(pdf_path) as pdf:
        text = "\n".join(p.get_text() for p in pdf)
        assert "Evidence boundaries" in text
        assert "PRIVATE_SENTINEL" not in text
        assert "Print / Save as PDF" not in text
        assert "Generated" in text and "Loaded / evaluated" in text
        if view == "weekly":
            assert "PORTFOLIO_DISPLAYED_PAGE" in text
        else:
            assert "sample-one" in text and "Café" in text and "東京" in text
        pages = len(pdf)
    css = (ROOT / "mission_control/static/page-reporting.css").read_text(encoding="utf-8")
    snapshot_html(popup, out / f"report-{view}-{width}.html", css)
    if view.startswith("results"):
        assert "USD" in text and "D30" in text and "100" in text
    if view == "results-long":
        assert pages > 2
        assert all(f"Long synthetic cohort {number}" in text for number in range(6))
    if view == "overview":
        popup.screenshot(path=str(out / f"report-{width}.png"), full_page=True)
    popup.close()
    return dict(view=view, viewport_width=width, pdf_pages=pages, text_verified=True, secret_excluded=True, keyboard=True)


def viewport_pass(browser, origin, width, height, out):
    page = browser.new_page(viewport=dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(origin)
    page.locator(".page-reporting").wait_for()
    expect(page.locator("#main h1")).to_contain_text("A clearer next step")
    expect(page.locator(".wmm-story-steps li")).to_have_count(3)
    expect(page.locator(".wmm-overview-story")).to_contain_text("What can you expect?")
    expect(page.locator(".wmm-overview-story")).to_contain_text("cannot guarantee")
    page.locator(".hero [data-view=workflow]").focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-view="workflow"].nav-item')).to_have_attribute("aria-current", "page")
    page.evaluate("state.workspace.private_test_data='PRIVATE_SENTINEL'")
    views = page.locator(".nav-item").evaluate_all("nodes=>nodes.map(n=>n.dataset.view)")
    observations = []
    for view in views:
        page.locator(f'.nav-item[data-view="{view}"]').click()
        expect(page.locator(".page-reporting")).to_have_count(1)
        expect(page.locator(".page-reporting")).to_contain_text("Next:")
        if view == "weekly":
            expect(page.locator(".page-reporting")).to_contain_text("Unavailable")
            page.get_by_role("button", name="Review apps", exact=True).click()
            expect(page.locator(".page-reporting")).to_contain_text("Displayed portfolio page")
            expect(page.locator(".page-reporting .page-metric-grid>div strong").first).to_have_text("2")
        if view == "evidence":
            page.locator("#evidence-search").fill("no matching record")
            expect(page.locator(".page-reporting .page-metric-grid>div").first).to_contain_text("0")
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), view
        observations.append(export_report(page, view, width, out))
        if view == "overview":
            page.screenshot(path=str(out / f"overview-{width}.png"))
            page.locator(".page-reporting").screenshot(path=str(out / f"panel-{width}.png"))
            css = (ROOT / "mission_control/static/style.css").read_text(encoding="utf-8") + (ROOT / "mission_control/static/page-reporting.css").read_text(encoding="utf-8")
            snapshot_html(page, out / f"overview-{width}.html", css)
    # The blocked-window path must preserve state and avoid a false export receipt.
    page.evaluate("window.savedOpen=window.open;window.open=()=>null")
    page.locator("[data-report-page]").click()
    expect(page.locator("#toast")).to_contain_text("Allow a report window")
    page.evaluate("window.open=window.savedOpen")
    if width == 1440:
        page.locator('.nav-item[data-view="results"]').click()
        page.evaluate("state.workspace.metrics.cohorts=Array.from({length:6},(_,i)=>({...state.workspace.metrics.cohorts[0],cohort_id:'Long synthetic cohort '+i}));render()")
        observations.append(export_report(page, "results-long", width, out))
    # App switching must immediately remove the prior app's report context.
    page.locator("#app-select").select_option("sample-two")
    expect(page.locator(".page-reporting")).to_contain_text("Other synthetic workspace")
    assert "Synthetic Café" not in page.locator(".page-reporting").inner_text()
    assert not errors, errors
    page.close()
    return observations


def main():
    out = ROOT / ".factory/page-reporting"
    out.mkdir(parents=True, exist_ok=True)
    observations = []
    with tempfile.TemporaryDirectory() as folder:
        store = Store(Path(folder) / "test.sqlite", seed=False)
        seed(store)
        server = Server(("127.0.0.1", 0), store)
        server.daemon_threads = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch()
                version = browser.version
                for width, height in ((1440, 900), (390, 844)):
                    observations.extend(viewport_pass(browser, f"http://127.0.0.1:{server.server_port}/", width, height, out))
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    result = dict(status="PASS", browser=version, python=platform.python_version(), observations=observations,
        scope="Ten top-level views only. Synthetic local data, no provider acceptance. PDFs generated by Chromium print engine and inspected with PyMuPDF; actual OS save-dialog completion remains user-controlled. Secondary dialogs are incomplete.")
    (out / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
