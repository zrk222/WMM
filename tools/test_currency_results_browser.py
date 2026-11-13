"""Actual Results currency display with isolated SQLite and synthetic observations."""

import json
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import Browser, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(browser: Browser, origin: str, width: int, out: Path) -> dict[str, object]:
    page = browser.new_page(viewport={"width": width, "height": 900}, locale="en-US")
    errors: list[str] = []
    posts: list[str] = []
    module_status: dict[str, int] = {}
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
    page.on(
        "response",
        lambda response: module_status.update({response.url.rsplit("/", 1)[-1]: response.status})
        if response.url.endswith(("/app-money.mjs", "/currency-profile.mjs"))
        else None,
    )
    try:
        page.goto(origin)
        page.wait_for_function(
            "(state) => state.workspace?.app?.id === state.app",
            arg=page.evaluate_handle("async () => (await import('/app.mjs')).state"),
        )
        page.locator("#navigation details > summary").click()
        page.locator('.nav-item[data-view="results"]').click()
        snapshot = page.evaluate("async () => (await import('/app.mjs')).state.workspace.ledger")
        for code, value in (
            ("USD", "USD\u00a012.34"),
            ("JPY", "JPY\u00a01,234"),
            ("KWD", "KWD\u00a01.234"),
            ("CLF", "CLF\u00a00.1234"),
        ):
            panel = page.locator("#main section.ledger-panel").filter(
                has=page.get_by_role("heading", name=f"currency-{code}", exact=True)
            )
            expect(panel).to_contain_text(value)
            panel.screenshot(path=str(out / f"ledger-{code}-{width}.png"))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        assert snapshot == page.evaluate("async () => (await import('/app.mjs')).state.workspace.ledger")
        model = page.evaluate(
            "async () => {const {state}=await import('/app.mjs'); return (await import('/feature-apis.mjs')).WMMPageReports.model(state)}"
        )
        serialized = json.dumps(model)
        report_html = page.evaluate(
            "async () => {const {state}=await import('/app.mjs');const reports=(await import('/feature-apis.mjs')).WMMPageReports;return reports.reportHTML(reports.model(state))}"
        )
        assert "Minor units are not whole currency units" in report_html
        for code in ("USD", "JPY", "KWD", "CLF"):
            assert code in serialized
        assert "1234" in serialized
        assert all(row["contribution_minor"] == 1234 for row in model["cohorts"])
        assert len(model["cohorts"]) == 4
        page.screenshot(path=str(out / f"results-currency-{width}.png"), full_page=True)
        css = page.evaluate(
            "() => Array.from(document.styleSheets).flatMap(sheet => Array.from(sheet.cssRules).map(rule => rule.cssText)).join('\\n')"
        )
        (out / f"results-currency-{width}.html").write_text(
            page.content().replace("</head>", f"<style>{css}</style></head>"), encoding="utf-8"
        )
        assert not errors, errors
        assert not posts, posts
        assert module_status == {"app-money.mjs": 200, "currency-profile.mjs": 200}, module_status
        tiny = page.evaluate(
            "async () => {const {money}=await import('/app-money.mjs');return [money(0.0000001,'USD'),money(-0.0000001,'JPY')]}"
        )
        assert tiny == ["1e-7 minor units (USD; fractional estimate)", "-1e-7 minor units (JPY; fractional estimate)"]
        return {
            "width": width,
            "currencies": ["USD", "JPY", "KWD", "CLF"],
            "source_unchanged": True,
            "raw_report_units": True,
            "provider_calls": 0,
        }
    finally:
        page.close()


def main() -> None:
    from mission_control.ledger import Ledger
    from mission_control.server import Server
    from mission_control.store import Store
    from tests.test_ledger import cohort, event
    from tests.test_mission_control import evidence_data

    out = ROOT / ".factory/marketing-value-review/02-execution"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "currency.sqlite", seed=False)
        store.save_app("sample-one", {"name": "Synthetic currency display", "release": "build-1", "locale": "en-US"})
        ledger = Ledger(store.path)
        for code in ("USD", "JPY", "KWD", "CLF"):
            identity = "currency-" + code
            ledger.define("sample-one", cohort(cohort_id=identity, currency=code))
            rows = [
                event("install", "INSTALL"),
                event("purchase", "PURCHASE", amount=1234),
                event("value", "VALUE", day="2026-09-20"),
                event("cost", "COST_ACQUISITION", amount=0),
                event("delivery", "COST_DELIVERY", amount=0),
            ]
            for row in rows:
                row["currency"] = code
                event_id = row["event_id"]
                assert isinstance(event_id, str)
                row["event_id"] = code + "-" + event_id
            ledger.ingest("sample-one", {"cohort_id": identity, "events": rows})
            data = dict(
                evidence_data("cohort"),
                cohort_id=identity,
                currency=code,
                net_proceeds_minor=1234,
                acquisition_cost_minor=0,
                delivery_cost_minor=0,
            )
            store.save_record(
                "sample-one",
                {
                    "kind": "cohort",
                    "title": identity,
                    "source": "Synthetic currency fixture",
                    "manifest_version": store.app("sample-one")["version"],
                    "data": data,
                },
            )
        before = ledger.reports("sample-one", "2026-11-13T00:00:00+00:00")
        assert all(row["net_proceeds_minor"] == 1234 for row in before)
        server = Server(("127.0.0.1", 0), store)
        server.daemon_threads = False
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch()
                observations = [
                    run(browser, f"http://127.0.0.1:{server.server_port}", width, out) for width in (1440, 390)
                ]
                browser.close()
            assert before == ledger.reports("sample-one", "2026-11-13T00:00:00+00:00")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    result = {"status": "PASS", "observations": observations}
    (out / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
