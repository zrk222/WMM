"""Real desktop/mobile browser controls against an isolated WMM HTTP server.

Identity and provider responses are synthetic; this never accesses a real account.
"""

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Standalone tool: resolve this checkout before importing its application/fixtures.
from mission_control.apple_analytics import CAMPAIGN_DOWNLOADS, DISCOVERY  # noqa: E402
from mission_control.apple_metrics_schedule import AppleMetricsSchedules  # noqa: E402
from mission_control.common import digest, now  # noqa: E402
from mission_control.device_signin import DeviceSignIns  # noqa: E402
from mission_control.worker import run_once  # noqa: E402
from tests.test_apple_metrics_http_route import AppleMetricsRouteTests  # noqa: E402
from tests.test_device_signin import CLIENT, CODE, TOKEN  # noqa: E402

OUT = ROOT / ".factory/apple-analytics-ui/browser"


def campaign_downloads(root: Any) -> None:
    """Exercise the actual controls and authenticated route without Apple network access."""
    root.get_by_text("Measure App Store campaign downloads", exact=True).click()
    form = root.locator("#apple-campaign-form")
    form.get_by_label("Apple campaign link").fill("https://apps.apple.com/app/apple-store/id123?pt=456&ct=pilot&mt=8")
    form.get_by_label("Storefront country code (two letters)").fill("ca")
    form.get_by_label("Start date").fill("2026-01-01")
    form.get_by_label("End date (included)").fill("2026-01-02")
    form.get_by_role("button", name="Review saved downloads").click()
    results = root.locator("#apple-campaign-results")
    expect(results.get_by_role("columnheader", name="Apple processed")).to_be_visible()
    day = results.get_by_role("row").filter(has_text="2026-01-01")
    expect(day.get_by_role("rowheader")).to_have_text("2026-01-01")
    expect(day.get_by_role("cell", name="Unknown", exact=True)).to_be_visible()
    expect(day.get_by_role("cell", name="No saved file", exact=True)).to_be_visible()
    expect(results).to_contain_text("Keep the existing review window")
    expect(root.locator("#apple-analytics-status")).to_contain_text("Saved Apple campaign results reviewed.")
    root.get_by_text("Measure App Store campaign downloads", exact=True).click()


def journey(browser: Any, width: int, height: int) -> dict[str, Any]:
    fixture = AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
    fixture.setUp()
    use_device = width == 1440
    clock = [0.0]
    if use_device:
        fixture.server.device_signins = DeviceSignIns(fixture.server.identities, CLIENT, clock=lambda: clock[0])
    origin = "http://127.0.0.1:" + str(fixture.server.server_port)
    context = browser.new_context(viewport={"width": width, "height": height})
    # The complete application runs; external requests are forbidden.
    context.route(
        "**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    apple_requests: list[str] = []
    page.on(
        "request", lambda request: apple_requests.append(request.url) if "/apple-analytics/" in request.url else None
    )
    try:
        page.goto(origin)
        page.locator("#main h1").wait_for()
        page.locator("#app-select").select_option("sample-one")
        page.get_by_text("Advanced tools", exact=True).click()
        page.locator('[data-view="connections"]').click()
        page.locator('[data-action="apple-analytics-open"]').click()
        dialog = page.locator("#modal")
        expect(dialog).to_contain_text("Sign in with the app owner account")
        expect(dialog).to_contain_text("WMM will return here")
        (OUT / f"sign-in-{width}.html").write_text(page.content(), encoding="utf-8")
        dialog.get_by_role("button", name="Sign in", exact=True).click()
        if use_device:
            identity = dict(principal="owner", login="owner", provider="GITHUB", verified_at=now())
            with (
                patch("mission_control.device_signin.request", side_effect=[CODE, TOKEN]),
                patch("mission_control.device_signin.github_read", return_value=identity),
            ):
                dialog.get_by_role("button", name="Start GitHub sign-in", exact=True).click()
                expect(dialog).to_contain_text(CODE["user_code"])
                clock[0] = float(CODE["interval"])
                dialog.get_by_role("button", name="Check GitHub sign-in", exact=True).click()
                dialog.get_by_role("button", name="Confirm this account", exact=True).click()
        else:
            page.locator("#identity-token").fill("synthetic_owner_identity_token")
            dialog.get_by_role("button", name="Verify my identity", exact=True).click()
        root = page.locator("#apple-analytics-root")
        expect(root).to_contain_text("No saved refresh schedule")
        expect(root).to_contain_text("No current report inventory")
        assert apple_requests == [f"{origin}/api/apps/sample-one/apple-analytics/view"]
        form = root.locator("#apple-analytics-form")
        choose_purpose = form.get_by_label("What should WMM check?", exact=True)
        expect(choose_purpose).to_have_value("@inventory")
        expect(form).to_contain_text("does not collect download counts")
        form.get_by_role("button", name="Enable refresh", exact=True).click()
        expect(root).to_contain_text("On · Report availability")
        schedules = AppleMetricsSchedules(fixture.store)
        assert schedules.tick() == 1
        result = dict(
            provider="app_store",
            operation="analytics_reports",
            app_id="sample-one",
            store_app_id="123",
            status="METRIC_DOWNLOAD_REQUIRED",
            coverage="COMPLETE",
            request={"operation": "analytics_reports"},
            external_writes=False,
            metric_observations=None,
            source_hash=digest({"fixture": "scheduled-inventory"}),
            observed_at=now(),
            reports=[
                dict(id="report-1", name="App Downloads Standard", coverage="COMPLETE", instances=[]),
                dict(id="discovery-1", name=DISCOVERY, coverage="COMPLETE", instances=[]),
                dict(
                    id="campaign-report-1",
                    name=CAMPAIGN_DOWNLOADS,
                    coverage="COMPLETE",
                    instances=[dict(id="campaign-instance-1", granularity="DAILY", processing_date="2026-01-02")],
                ),
            ],
        )
        with patch("mission_control.worker.read_report", return_value=result) as provider:
            assert run_once(fixture.store)
            provider.assert_called_once()
        root.get_by_role("button", name="Refresh saved status", exact=True).click()
        expect(root).to_contain_text("0 report instances")
        expect(root).to_contain_text("Missing metrics remain unknown")
        expect(root).to_contain_text("Unique counts can overlap")
        campaign_downloads(root)
        control = root.get_by_role("button", name="Collect store impressions", exact=True)
        control.focus()
        page.keyboard.press("Enter")
        expect(root.locator("#apple-analytics-status")).to_contain_text("Store impressions read queued")

        def discovery_inventory(reader, store_app_id):
            assert store_app_id == "123"
            reader.hashes.append(digest(result))
            return result

        with (
            patch("mission_control.provider_reports.credential", return_value="fixture"),
            patch("mission_control.provider_reports.read_analytics", side_effect=discovery_inventory),
            patch("mission_control.provider_reports.read_instance_segments") as download,
        ):
            assert run_once(fixture.store)
            download.assert_not_called()
        impressions = [
            job
            for job in fixture.server.service.workspace("sample-one")["jobs"]
            if job["data"].get("options", {}).get("report_family") == DISCOVERY
        ]
        assert len(impressions) == 1 and impressions[0]["status"] == "SUCCEEDED"
        assert impressions[0]["result"]["status"] == "WAITING_FOR_REPORTS"
        assert impressions[0]["result"]["metric_observations"] is None
        form = root.locator("#apple-analytics-form")
        expect(choose_purpose).to_have_value("@inventory")
        choose_purpose.select_option("report-1")
        choose_purpose.focus()
        page.keyboard.press("Tab")
        expect(form.get_by_label("Refresh every (hours)", exact=True)).to_be_focused()
        form.get_by_label("Refresh every (hours)", exact=True).fill("48")
        form.get_by_role("button", name="Save refresh settings", exact=True).click()
        expect(root).to_contain_text("ENABLED")
        expect(root).not_to_contain_text("On · Report availability")
        expect(choose_purpose).to_have_value("report-1")
        saved = AppleMetricsSchedules(fixture.store).get("sample-one")
        assert saved is not None and saved["enabled"] and saved["interval_hours"] == 48
        assert saved["last_success"] is None
        # A queued read and saved schedule are not fabricated numeric evidence.
        expect(root).to_contain_text("Last metrics collected: Not recorded")
        assert root.evaluate("(node) => node.scrollWidth <= node.clientWidth + 1")
        page.locator("#modal").screenshot(path=str(OUT / f"analytics-{width}.png"))
        rendered = page.evaluate(r"""() => {
          const styles=Array.from(document.styleSheets).flatMap(sheet=>{
            try{return Array.from(sheet.cssRules).map(rule=>rule.cssText)}catch{return []}
          }).join('\n');
          const snapshot=document.documentElement.cloneNode(true);
          snapshot.querySelectorAll('script,link[rel="stylesheet"]').forEach(node=>node.remove());
          const style=document.createElement('style');style.textContent=styles;
          snapshot.querySelector('head').append(style);
          return '<!doctype html>'+snapshot.outerHTML;
        }""")
        (OUT / f"analytics-{width}.html").write_text(rendered, encoding="utf-8")
        root.get_by_role("button", name="Pause refresh", exact=True).focus()
        page.keyboard.press("Enter")
        expect(root).to_contain_text("PAUSED")
        paused = AppleMetricsSchedules(fixture.store).get("sample-one")
        assert paused is not None and paused["enabled"] is False
        # Report uses actual inventory counts and its caveats, not synthetic app metrics.
        reports = []
        page.on("popup", lambda popup: reports.append(popup))
        root.get_by_role("button", name="Report / Save PDF", exact=True).click()
        page.wait_for_timeout(200)
        assert reports, "Report action did not open its printable report"
        report = reports[-1]
        report.wait_for_load_state()
        expect(report.locator("body")).to_contain_text("Apple analytics inventory")
        expect(report.locator("body")).to_contain_text("unavailable measurements remain unknown")
        report.close()
        page.locator("#close-modal").click()
        # An app switch must not retain another app's owner/source controls.
        page.locator("#app-select").select_option("sample-two")
        page.locator('[data-action="apple-analytics-open"]').click()
        expect(root).to_contain_text("requires the current app owner")
        expect(root.locator("#apple-analytics-form")).to_have_count(0)
        assert not errors, errors
        return dict(
            width=width,
            height=height,
            status="PASS",
            keyboard="VERIFIED",
            inventory="SYNTHETIC_HTTP_VERIFIED",
            owner_sign_in="RESUMED_SAME_APP_SAVED_VIEW_WITHOUT_PROVIDER_READ",
            owner_sign_in_method="DEVICE" if use_device else "MANUAL",
            schedule_save_pause="VERIFIED",
            availability_watch="OWNER_OPT_IN_THEN_SCHEDULED_INVENTORY",
            impressions="OWNER_QUEUE_AND_UNKNOWN_IF_NO_DAILY_REPORT",
            apple_campaign_downloads="OWNER_READ_AND_UNKNOWN_WITHOUT_MATCHING_ROWS",
            pdf_report="PRINTABLE_REPORT_VERIFIED",
            app_isolation="VERIFIED",
            overflow=False,
            page_errors=errors,
        )
    except Exception:
        # Synthetic-only diagnostics; retain the first failed browser state.
        target = OUT / f"first-failure-{width}.html"
        if not target.exists():
            target.write_text(page.content(), encoding="utf-8")
        raise
    finally:
        context.close()
        fixture.doCleanups()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            observations = [journey(browser, width, height) for width, height in ((1440, 900), (390, 844))]
            result = dict(
                status="PASS",
                browser=browser.version,
                observations=observations,
                data="DISPOSABLE_SYNTHETIC",
                live_provider_execution="NOT_RUN",
            )
            (OUT / "observations.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
