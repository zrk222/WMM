"""Actual Chromium inventory rendering with isolated synthetic workspace input."""

import json
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from test_page_reporting_browser import seed

    from mission_control.server import Server
    from mission_control.store import Store

    out = Path(".factory/marketing-value-review/retention-repair")
    out.mkdir(parents=True, exist_ok=True)
    observations = []
    with tempfile.TemporaryDirectory() as folder:
        store = Store(Path(folder) / "data.sqlite", seed=False)
        seed(store)
        server = Server(("127.0.0.1", 0), store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch()
                for width in (1440, 390):
                    page = browser.new_page(viewport={"width": width, "height": 900})
                    page.goto(f"http://127.0.0.1:{server.server_port}/")
                    page.locator("#main h1").first.wait_for()
                    page.evaluate("""async () => {
                      const {state}=await import('/app.mjs');
                      const {analyticsOverviewPanel}=await import('/app-campaign.mjs');
                      state.workspace.metrics={cohorts:[{status:'MEASURED'}],retention:[],event_ledger:[{cohort:{cohort_id:'synthetic-retention',ends_at:'2030-01-08',matures_at:'2030-01-15'},mature:true,status:'SUPPLIED_RECONCILED',observability:'OBSERVED',costs_complete:true,installs:4,retained:3,retention_rate:0.75,as_of:'2030-01-16'}]};
                      state.workspace.install_attribution={campaigns:[{}]};
                      state.workspace.measurement_integrity={state:'MEASURED',rows:[]};
                      document.querySelector('#main').innerHTML='<h1>Results</h1>'+analyticsOverviewPanel();
                    }""")
                    panel = page.get_by_role("region", name="Analytics overview")
                    expect(panel).to_contain_text("3/4 (75%)")
                    expect(panel).to_contain_text("2030-01-08 to 2030-01-15")
                    expect(panel.get_by_role("button", name="Add retention evidence", exact=True)).to_have_count(0)
                    button = panel.get_by_role(
                        "button", name="Download retention report: synthetic-retention", exact=True
                    )
                    expect(button).to_have_attribute("data-action", "ledger-report")
                    expect(button).to_have_attribute("data-id", "synthetic-retention")
                    button.focus()
                    expect(button).to_be_focused()
                    expect(button).to_be_visible()
                    page.screenshot(path=str(out / f"retention-{width}.png"), full_page=True)
                    css = page.evaluate(
                        "async () => (await Promise.all([...document.querySelectorAll('link[rel=stylesheet]')].map(async n => (await fetch(n.href)).text()))).join('\\n')"
                    )
                    (out / f"retention-{width}.html").write_text(
                        page.content().replace("</head>", "<style>" + css + "</style></head>"), encoding="utf-8"
                    )
                    observations.append(
                        {
                            "width": width,
                            "status": "PASS",
                            "numerator": 3,
                            "denominator": 4,
                            "rate": "75%",
                            "keyboard_focus": True,
                            "duplicate_retention_prompt": False,
                        }
                    )
                    page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    result = {
        "status": "PASS",
        "observations": observations,
        "scope": "Actual Chromium rendering and keyboard focus using synthetic injected workspace data on real loopback app; no provider, OS download completion or customer acceptance.",
    }
    (out / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
