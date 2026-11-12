"""Real desktop/mobile page reports and PDFs using isolated synthetic app data."""

import json
import platform
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import fitz
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def seed(store):
    from mission_control.experiments import Experiments
    from mission_control.ledger import Ledger
    from tests.test_experiments import ANALYZE, EXPOSE, REGISTER, observations, prepared
    from tests.test_ledger import cohort
    from tests.test_measurement_economics import definition, rows
    from tests.test_mission_control import evidence_data

    for identity, name in (("sample-one", "Synthetic Café 東京"), ("sample-two", "Other synthetic workspace")):
        store.save_app(
            identity,
            dict(
                name=name,
                job="Synthetic task",
                audience="Test",
                activation="Saved step",
                release="build-1",
                locale="en-US",
            ),
        )
    store.save_record(
        "sample-one",
        dict(
            kind="cohort",
            title="Supplied pilot",
            source="Synthetic fixture only",
            manifest_version=store.app("sample-one")["version"],
            data=evidence_data("cohort"),
        ),
    )
    ledger = Ledger(store.path)
    ledger.define("sample-one", definition(coverage_through="2027-01-01T00:00:00+00:00"))
    ledger.ingest("sample-one", {"cohort_id": "pilot-1", "events": rows()})
    ledger.define("sample-one", cohort(cohort_id="legacy-no-economics"))
    experiments = Experiments(store)
    plan = prepared(store)
    with patch("mission_control.experiments.now", return_value=REGISTER):
        experiment = experiments.create("sample-one", plan)
    with patch("mission_control.experiments.now", return_value=EXPOSE):
        experiments.act(
            "sample-one",
            experiment["id"],
            dict(
                operation="observe",
                version=experiment["version"],
                source="Synthetic exposure receipt",
                observed_at=EXPOSE,
            ),
        )
    with patch("mission_control.experiments.now", return_value=ANALYZE):
        # Preserve the first incomplete/null assessment before supplying observations.
        experiments.evaluate("sample-one", experiment["id"])
    for arm in ("control", "treatment"):
        ledger.ingest(
            "sample-one",
            {"cohort_id": "experiment-" + arm, "events": observations(arm, activations=10 if arm == "control" else 2)},
        )
    with patch("mission_control.experiments.now", return_value=ANALYZE):
        result = experiments.evaluate("sample-one", experiment["id"])
        current = next(row for row in experiments.list("sample-one") if row["id"] == experiment["id"])
        experiments.act(
            "sample-one",
            experiment["id"],
            dict(
                operation="decide",
                version=current["version"],
                assessment_hash=result["hash"],
                decision="NEXT_TEST",
                reason="Synthetic review of negative descriptive result",
            ),
        )
    assert result["result"]["effect"]["difference"] < 0


def snapshot_html(page, target, css):
    html = page.content().replace("</head>", "<style>" + css + "</style></head>")
    target.write_text(html, encoding="utf-8")


def export_report(page, view, width, out):
    page.locator("[data-report-page]").focus()
    inline = page.evaluate(
        "async () => {const {state}=await import('/app.mjs');return (await import('/feature-apis.mjs')).WMMPageReports.model(state).sections.length>0}"
    )
    if inline:
        page.keyboard.press("Enter")
        popup = page
        report = page.locator(".wmm-report-dialog[open]")
        expect(report).to_be_visible()
    else:
        with page.expect_popup() as waiting:
            page.keyboard.press("Enter")
        popup = waiting.value
        popup.wait_for_load_state("load")
        report = popup.locator("body")
        assert popup.evaluate("window.opener===null")
    report.locator("h1").wait_for()
    assert report.evaluate("element=>element.scrollWidth<=element.clientWidth+1")
    assert not report.locator("input,textarea").count()
    assert "PRIVATE_SENTINEL" not in report.inner_text()
    popup.evaluate("window.print=()=>{window.printRequested=true}")
    report.get_by_role("button", name="Print / Save as PDF", exact=True).focus()
    popup.keyboard.press("Enter")
    assert popup.evaluate("window.printRequested===true")
    pdf_path = out / f"{view}-{width}.pdf"
    popup.pdf(path=str(pdf_path), format="A4", print_background=True)
    with fitz.open(pdf_path) as pdf:
        text = "\n".join(str(p.get_text()) for p in pdf)
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
    if inline:
        # Snapshot only the scoped report, never the underlying app or open controls.
        (out / f"report-{view}-{width}.html").write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><style>'
            + css
            + '</style></head><body class="wmm-print-report">'
            + report.evaluate("element=>element.outerHTML")
            + "</body></html>",
            encoding="utf-8",
        )
    else:
        snapshot_html(popup, out / f"report-{view}-{width}.html", css)
    if view.startswith("results"):
        assert "USD" in text and "D30" in text and "100" in text
        for phrase in (
            "Customer acquisition cost",
            "500 minor currency units",
            "UNIQUE_ACQUIRED_PAYERS",
            "D7 net proceeds ROAS",
            "4×",
            "MATCHED_SPEND_MISSING",
            "Assessment history",
            "INCONCLUSIVE",
            "-0.4",
            "95% interval",
            "NEXT_TEST",
        ):
            assert phrase in text, (phrase, text[-1000:])
    if view == "results-long":
        assert pages > 2
        assert all(f"Long synthetic cohort {number}" in text for number in range(6))
    if view == "overview":
        popup.screenshot(path=str(out / f"report-{width}.png"), full_page=True)
    if inline:
        report.get_by_role("button", name="Close report", exact=True).focus()
        popup.keyboard.press("Enter")
        expect(report).to_have_count(0)
        expect(page.locator("[data-report-page]")).to_be_focused()
    else:
        popup.close()
    return dict(
        view=view, viewport_width=width, pdf_pages=pages, text_verified=True, secret_excluded=True, keyboard=True
    )


def viewport_pass(browser, origin, width, height, out):
    page = browser.new_page(viewport=dict(width=width, height=height))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(origin)
    expect(page.locator("#main h1").first).to_have_text("Set your goal")
    expect(page.locator("#goal-advanced")).not_to_have_attribute("open", "")
    page.locator("#goal-advanced > summary").click()
    page.locator(".page-reporting").wait_for()
    expect(page.locator("#goal-advanced .hero h2")).to_contain_text("Plan your app marketing")
    for phrase in (
        "Your next marketing move, with evidence",
        "Missing measurements stay unknown",
        "You still approve what goes live",
    ):
        expect(page.locator("[aria-label='Start your first experiment']")).to_contain_text(phrase)
    page.locator(".hero [data-view=workflow]").focus()
    page.keyboard.press("Enter")
    expect(page.locator('[data-view="workflow"].nav-item')).to_have_attribute("aria-current", "page")
    page.evaluate("async () => ((await import('/app.mjs')).state.workspace.private_test_data='PRIVATE_SENTINEL')")
    page.locator("#navigation details > summary").click()
    views = page.locator(".nav-item").evaluate_all("nodes=>nodes.map(n=>n.dataset.view)")
    observations = []
    for view in views:
        page.locator(f'.nav-item[data-view="{view}"]').click()
        if view == "overview":
            page.locator("#goal-advanced > summary").click()
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
        if view == "results":
            expect(page.locator("#main")).to_contain_text("500 minor currency units")
            expect(page.locator("#main")).to_contain_text("MATCHED_SPEND_MISSING")
            expect(page.locator("#main")).to_contain_text("-0.4")
            expect(page.locator("#main")).to_contain_text("INCONCLUSIVE")
            page.screenshot(path=str(out / f"results-{width}.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+1"), view
        observations.append(export_report(page, view, width, out))
        if view == "overview":
            page.screenshot(path=str(out / f"overview-{width}.png"))
            page.locator(".page-reporting").screenshot(path=str(out / f"panel-{width}.png"))
            css = (ROOT / "mission_control/static/style.css").read_text(encoding="utf-8") + (
                ROOT / "mission_control/static/page-reporting.css"
            ).read_text(encoding="utf-8")
            snapshot_html(page, out / f"overview-{width}.html", css)
    # A blocked popup falls back to an in-page preview without saving a file.
    page.evaluate("window.savedOpen=window.open;window.open=()=>null")
    page.locator("[data-report-page]").click()
    preview = page.locator(".wmm-report-dialog[open]")
    expect(preview).to_be_visible()
    expect(preview).to_contain_text("No file has been saved")
    assert "PRIVATE_SENTINEL" not in preview.inner_text()
    assert not preview.locator("input,textarea").count()
    preview.get_by_role("button", name="Close report", exact=True).click()
    expect(preview).to_have_count(0)
    page.evaluate("window.open=window.savedOpen")
    if width == 1440:
        page.locator('.nav-item[data-view="results"]').click()
        page.evaluate(
            "async () => {const {state,render}=await import('/app.mjs');state.workspace.metrics.cohorts=Array.from({length:6},(_,i)=>({...state.workspace.metrics.cohorts[0],cohort_id:'Long synthetic cohort '+i}));render();}"
        )
        observations.append(export_report(page, "results-long", width, out))
    # App switching must immediately remove the prior app's report context.
    page.locator("#app-select").select_option("sample-two")
    expect(page.locator(".page-reporting")).to_contain_text("Other synthetic workspace")
    assert "Synthetic Café" not in page.locator(".page-reporting").inner_text()
    assert not errors, errors
    page.close()
    return observations


def main():
    from mission_control.server import Server
    from mission_control.store import Store

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
                    observations.extend(
                        viewport_pass(browser, f"http://127.0.0.1:{server.server_port}/", width, height, out)
                    )
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    result = dict(
        status="PASS",
        browser=version,
        python=platform.python_version(),
        observations=observations,
        scope="Ten top-level views, including real SQLite economics and complete experiment assessments on Results. Synthetic local data, no provider acceptance. PDFs generated by Chromium print engine and inspected with PyMuPDF; actual OS save-dialog completion remains user-controlled. Secondary dialogs are incomplete.",
    )
    (out / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
