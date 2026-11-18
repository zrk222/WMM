"""Real desktop/mobile browser controls against an isolated WMM HTTP server.

Identity and provider responses are synthetic; this never accesses a real account.
"""

import gzip
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import fitz
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Standalone tool: resolve this checkout before importing its application/fixtures.
from mission_control.apple_analytics import CAMPAIGN_DOWNLOADS, DISCOVERY, DOWNLOADS  # noqa: E402
from mission_control.apple_metrics_schedule import AppleMetricsSchedules  # noqa: E402
from mission_control.common import digest, now  # noqa: E402
from mission_control.device_signin import DeviceSignIns  # noqa: E402
from mission_control.insights import Insights  # noqa: E402
from mission_control.openseo_read import save_reading  # noqa: E402
from mission_control.operator_client import OperatorClient  # noqa: E402
from mission_control.worker import run_once  # noqa: E402
from tests.test_apple_metrics_http_route import AppleMetricsRouteTests  # noqa: E402
from tests.test_device_signin import CLIENT, CODE, TOKEN  # noqa: E402
from tests.test_measurement_connectors import FakeVault  # noqa: E402
from tests.test_openseo_read import provider_reply  # noqa: E402
from tests.test_openseo_read import setup as open_seo_setup  # noqa: E402

OUT = ROOT / ".factory/apple-analytics-ui/browser"


def rendered_page(page: Any) -> str:
    """Capture the running page with its resolved styles for the design audit."""
    return page.evaluate(r"""() => {
      const styles=Array.from(document.styleSheets).flatMap(sheet=>{
        try{return Array.from(sheet.cssRules).map(rule=>rule.cssText)}catch{return []}
      }).join('\n');
      const snapshot=document.documentElement.cloneNode(true);
      snapshot.querySelectorAll('script,link[rel="stylesheet"]').forEach(node=>node.remove());
      const style=document.createElement('style');style.textContent=styles;
      snapshot.querySelector('head').append(style);
      return '<!doctype html>'+snapshot.outerHTML;
    }""")


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


def performance_report(page: Any, root: Any, fixture: AppleMetricsRouteTests, inventory: dict[str, Any]) -> None:
    """Verify displayed measurements and report provenance through actual owner controls."""
    form = root.locator("#apple-performance-form")
    form.get_by_label("First event date").fill("2026-01-01")
    form.get_by_label("Last event date").fill("2026-01-05")
    form.get_by_role("button", name="Review saved metrics").click()
    expect(root.locator("#apple-performance-results")).to_contain_text("No Apple metrics are saved")
    expect(root.get_by_role("button", name="Performance report / Save PDF")).to_have_count(0)
    report = dict(
        inventory["reports"][1],
        instances=[dict(id="discovery-daily", processing_date="2026-01-04", granularity="DAILY")],
    )
    available = dict(inventory, reports=[inventory["reports"][0], report])
    root.get_by_role("button", name="Read Apple inventory", exact=True).click()
    expect(root.locator("#apple-analytics-status")).to_contain_text("queued")
    with patch("mission_control.worker.read_report", return_value=available):
        assert run_once(fixture.store)
    root.get_by_role("button", name="Refresh saved status", exact=True).click()
    form.get_by_label("First event date").fill("2026-01-01")
    form.get_by_label("Last event date").fill("2026-01-05")
    form.get_by_role("button", name="Collect available Apple files").click()
    expect(root.locator("#apple-performance-status")).to_contain_text("1 Apple file reads")
    raw = gzip.compress(
        b"Date\tApp Apple Identifier\tEvent\tCounts\tUnique Counts\n"
        b"2026-01-01\t123\tImpression\t80\t50\n"
        b"2026-01-01\t123\tPage view\t0\t0\n",
        mtime=0,
    )
    segments = [
        dict(id="segment-1", data=raw, size=len(raw), checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest())
    ]
    with (
        patch("mission_control.provider_reports.credential", return_value="fixture"),
        patch("mission_control.provider_reports.read_analytics", return_value=available),
        patch("mission_control.provider_reports.read_instance_segments", return_value=segments),
    ):
        assert run_once(fixture.store)
    form.get_by_role("button", name="Review saved metrics").click()
    expect(root.get_by_role("columnheader", name="App icon list impressions")).to_be_visible()
    expect(root.get_by_role("columnheader", name="App Store page-view events")).to_be_visible()
    day = root.get_by_role("row").filter(has_text="2026-01-01")
    expect(day.get_by_role("cell", name="80", exact=True)).to_be_visible()
    expect(day.get_by_role("cell", name="0", exact=True)).to_be_visible()
    report_button = root.get_by_role("button", name="Performance report / Save PDF", exact=True)
    report_button.press("Enter")
    preview = page.get_by_role("dialog", name="App Store performance", exact=True)
    expect(preview).to_contain_text("Discovery source SHA-256")
    expect(preview).to_contain_text("Page-view events can include app and in-app event pages.")
    expect(preview).to_contain_text("Unavailable")
    page.keyboard.press("Escape")
    expect(report_button).to_be_focused()


def saved_search_reading(fixture: AppleMetricsRouteTests) -> None:
    """Use the real OpenSEO lifecycle with synthetic credentials and provider data."""
    app = fixture.store.app("sample-one")
    setup = open_seo_setup()
    fixture.app = fixture.store.save_app(
        "sample-one",
        dict(app["data"], website=setup["website"], release=setup["release"], locale=setup["locale"]),
        app["version"],
    )
    FakeVault.values, FakeVault.fail_delete = {}, 0
    insights = Insights(fixture.store)
    with (
        patch("mission_control.insights.Vault", FakeVault),
        patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply),
    ):
        source = insights.setup("sample-one", setup)
    reading = insights.list("sample-one")["reports"][0]
    save_reading(
        fixture.store,
        "sample-one",
        source["source_id"],
        dict(id="synthetic-browser-search", manifest_version=fixture.app["version"], report_id=reading["id"]),
    )


def assign_search_step(page: Any, panel: Any, selection: dict[str, Any], action: dict, grant: dict) -> None:
    """Assign one evidenced action through the owner UI to an eligible grant."""
    grant_id = grant["grant"]["id"]
    agent_id = grant["grant"]["agent_id"]
    panel.get_by_role("combobox", name=f"Agent for {action['title']}", exact=True).select_option(grant_id)
    with page.expect_response(lambda item: item.url.endswith("/apple-analytics/search-review-assign")) as response:
        panel.get_by_role("button", name="Assign to agent", exact=True).press("Enter")
    value = response.value.json()
    assert response.value.status == 200, value
    assert response.value.request.post_data_json == dict(selection, action_id=action["id"], grant_id=grant_id)
    assert value["receipt"]["action_id"] == action["id"]
    expect(page.locator("#apple-performance-status")).to_contain_text(f"Step assigned to {agent_id}.")
    expect(panel).to_contain_text("Awaiting agent")


def run_search_team(
    page: Any,
    fixture: AppleMetricsRouteTests,
    panels: dict,
    report: dict,
    selection: dict[str, Any],
    grants: dict[str, dict],
) -> dict:
    """Complete the scoped web step and read its receipt back in the owner's review."""
    review = report["search_review"]
    actions = {item["id"]: item for item in review["actions"]}
    scope = dict(selection, review_hash=review["review_hash"])
    for action_id, grant in grants.items():
        assign_search_step(page, panels[action_id], scope, actions[action_id], grant)
    result = page.locator("#apple-performance-results")
    expect(result).to_contain_text(f"2 of {len(actions)} steps assigned. 0 completed.")
    client = OperatorClient(fixture.client.origin, grant_token=grants["web-baseline"]["token"])
    execution = client.call(
        dict(
            app_id=report["app_id"],
            operation="search.plan.execute",
            input=dict(review_hash=review["review_hash"], action_id="web-baseline"),
        )
    )
    assert isinstance(execution, dict) and execution["action_id"] == "web-baseline"
    assert execution["review_hash"] == review["review_hash"]
    assert execution["assignment"]["status"] == "COMPLETED"
    with page.expect_response(lambda item: item.url.endswith("/apple-analytics/search-review")) as refreshed:
        result.get_by_role("button", name="Refresh plan status", exact=True).press("Enter")
    assert refreshed.value.status == 200, refreshed.value.json()
    assert refreshed.value.request.post_data_json == selection
    web = refreshed.value.json()["search_review"]["assignments"]["web-baseline"]
    assert web["status"] == "COMPLETED"
    assert web["receipt_sha256"] == execution["assignment"]["receipt_sha256"]
    expect(result).to_contain_text(f"2 of {len(actions)} steps assigned. 1 completed.")
    expect(panels["web-baseline"]).to_contain_text(web["receipt_sha256"])
    expect(panels["apple-baseline"]).to_contain_text("Awaiting agent")
    return web


def search_to_store_report(page: Any, fixture: AppleMetricsRouteTests, width: int) -> None:
    """Read both saved sources through the owner UI and verify independent actions and export."""
    path = "/api/apps/sample-one/apple-analytics/search-review"
    selection = dict(manifest_version=fixture.app["version"], start="2026-01-01", end="2026-01-05")
    anonymous = OperatorClient(fixture.client.origin)
    anonymous.bootstrap()
    fixture.reject(anonymous, path, selection, 403)
    fixture.reject(fixture.client, path.replace("sample-one", "sample-two"), selection, 403)
    grants = {
        action_id: fixture.post(
            "/api/apps/sample-one/agent-grants/issue",
            dict(
                agent_id=agent_id,
                manifest_version=selection["manifest_version"],
                operations=["search.plan.execute"],
                expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                max_calls=10,
            ),
        )
        for action_id, agent_id in (("apple-baseline", "apple-review-agent"), ("web-baseline", "web-review-agent"))
    }

    page.get_by_role("button", name="Review results", exact=True).press("Enter")
    entry = page.get_by_role("button", name="Open Search to App Store", exact=True)
    expect(entry).to_be_visible()
    entry.press("Enter")
    root = page.locator("#apple-analytics-root")
    form = root.locator("#apple-performance-form")
    form.get_by_label("First event date").fill(selection["start"])
    form.get_by_label("Last event date").fill(selection["end"])
    with (
        patch("mission_control.openseo_transport.call_tool") as seo_read,
        patch("mission_control.worker.read_report") as apple_read,
        page.expect_response(lambda item: item.url.endswith(path)) as response,
    ):
        form.get_by_role("button", name="Review search and App Store results", exact=True).press("Enter")
    seo_read.assert_not_called()
    apple_read.assert_not_called()
    assert response.value.status == 200
    assert response.value.request.method == "POST"
    assert response.value.request.post_data_json == selection
    report = response.value.json()
    assert report["app_id"] == "sample-one"
    assert report["external_writes"] is False
    assert open_seo_setup()["api_key"] not in json.dumps(report)
    assert all(grant["token"] not in json.dumps(report) for grant in grants.values())
    actions = {item["id"]: item for item in report["search_review"]["actions"]}
    assert {"apple-baseline", "web-baseline", "store-link-check"} <= actions.keys()
    assert actions["apple-baseline"]["depends_on"] == actions["web-baseline"]["depends_on"] == []
    assert actions["store-link-check"]["depends_on"] == ["web-baseline"]

    result = root.locator("#apple-performance-results")
    expect(result.get_by_role("heading", name="Search to App Store", exact=True)).to_be_visible()
    expect(result).to_contain_text("https://sample.example/guide")
    expect(result).to_contain_text("Google organic impressions 100")
    expect(result).to_contain_text("Google organic clicks 4")
    first_day = result.get_by_role("row").filter(has_text="2026-01-01")
    expect(first_day.get_by_role("cell", name="80", exact=True)).to_be_visible()
    expect(first_day.get_by_role("cell", name="0", exact=True)).to_be_visible()
    expect(result.get_by_role("row").filter(has_text="2026-01-05")).to_contain_text("Unavailable")
    panels = {}
    for key in ("apple-baseline", "web-baseline"):
        action = actions[key]
        summary = result.locator("summary").filter(has_text=action["title"])
        expect(summary).to_be_visible()
        summary.press("Enter")
        panel = summary.locator("..")
        expect(panel).to_have_attribute("open", "")
        expect(panel).to_contain_text(action["task"])
        expect(panel.get_by_role("button", name="Download draft", exact=True)).to_be_visible()
        panels[key] = panel
    panels["apple-baseline"].get_by_role("button", name="Open Apple report controls", exact=True).press("Enter")
    expect(root.get_by_role("button", name="Read Apple inventory", exact=True)).to_be_focused()
    with page.expect_download() as selected:
        panels["web-baseline"].get_by_role("button", name="Download draft", exact=True).press("Enter")
    draft = json.loads(Path(selected.value.path()).read_text(encoding="utf-8"))
    assert draft["app_id"] == report["app_id"] and draft["action"] == actions["web-baseline"]
    assert draft["review_hash"] == report["search_review"]["review_hash"]
    with page.expect_download() as full:
        result.get_by_role("button", name="Download action plan", exact=True).press("Enter")
    plan = json.loads(Path(full.value.path()).read_text(encoding="utf-8"))
    assert plan["rows"] == report["rows"]
    assert plan["search_review"]["actions"] == report["search_review"]["actions"]
    assert plan["review_hash"] == draft["review_hash"]
    assert all(grant["token"] not in json.dumps([plan, draft]) for grant in grants.values())
    with page.expect_response(lambda item: item.url.endswith(path + "-save")) as saved:
        panels["web-baseline"].get_by_role("button", name="Save action", exact=True).press("Enter")
    assert saved.value.status == 200, saved.value.json()
    receipt = saved.value.json()["receipt"]
    assert receipt["action"] == actions["web-baseline"] and receipt["status"] == "SAVED"
    assert receipt["review_hash"] == draft["review_hash"] and receipt["saved_by"] == "owner"
    # Saving can redraw the draft list with its receipt.
    web_summary = result.locator("summary").filter(has_text=actions["web-baseline"]["title"])
    web_panel = web_summary.locator("..")
    if not web_panel.evaluate("(element) => element.open"):
        web_summary.press("Enter")
    expect(web_panel).to_contain_text("Draft saved in WMM.")
    completed = run_search_team(page, fixture, panels, report, selection, grants)
    assert root.evaluate("(node) => node.scrollWidth <= node.clientWidth + 1")

    report_button = result.get_by_role("button", name="Search to App Store report / Save PDF", exact=True)
    report_button.press("Enter")
    preview = page.get_by_role("dialog", name="Search to App Store", exact=True)
    expect(preview.get_by_role("heading", name="Search to App Store", exact=True)).to_be_focused()
    for key in ("apple-baseline", "web-baseline"):
        expect(preview).to_contain_text(actions[key]["title"])
    expect(preview).to_contain_text("https://sample.example/guide")
    expect(preview).to_contain_text(receipt["id"])
    expect(preview).to_contain_text(completed["receipt_sha256"])
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.evaluate("window.print = () => { window.searchReportPrintRequested = true; }")
    preview.get_by_role("button", name="Print / Save as PDF", exact=True).press("Enter")
    assert page.evaluate("window.searchReportPrintRequested === true")
    page.emulate_media(media="print")
    try:
        pdf = page.pdf(prefer_css_page_size=True)
        with fitz.open(stream=pdf, filetype="pdf") as document:
            text = " ".join(" ".join(str(p.get_text()).split()) for p in document)
        assert actions["apple-baseline"]["title"] in text and actions["web-baseline"]["title"] in text
        assert "https://sample.example/guide" in text and open_seo_setup()["api_key"] not in text
        assert completed["receipt_sha256"] in "".join(text.split())
        assert all(grant["token"] not in text for grant in grants.values())
        if width == 1440:
            (OUT / "search-to-app-store.pdf").write_bytes(pdf)
    finally:
        page.emulate_media(media="screen")
    page.keyboard.press("Escape")
    expect(report_button).to_be_focused()
    web_panel.get_by_role("button", name="Review OpenSEO source", exact=True).press("Enter")
    inspector = page.get_by_role("dialog", name="OpenSEO · dedicated-project", exact=True)
    expect(inspector.get_by_role("heading", name="Saved observations", exact=True)).to_be_visible()


def fetch_provider_fixture() -> tuple[dict[str, Any], dict[tuple[str, str], bytes]]:
    """Only the two upstream response families are synthetic."""
    processing_date = "2026-01-04"
    inventory = dict(
        operation="analytics_reports",
        status="METRIC_DOWNLOAD_REQUIRED",
        coverage="COMPLETE",
        reports=[
            dict(
                id=report_id,
                name=family,
                coverage="COMPLETE",
                instances=[dict(id=instance, granularity="DAILY", processing_date=processing_date)],
            )
            for report_id, family, instance in (
                ("fetch-discovery", DISCOVERY, "fetch-discovery-daily"),
                ("fetch-downloads", DOWNLOADS, "fetch-downloads-daily"),
            )
        ],
    )
    rows = {
        ("fetch-discovery", "fetch-discovery-daily"): (
            b"Date\tApp Apple Identifier\tEvent\tCounts\tUnique Counts\n"
            b"2026-01-01\t123\tImpression\t80\t50\n"
            b"2026-01-01\t123\tPage view\t0\t0\n"
        ),
        ("fetch-downloads", "fetch-downloads-daily"): (
            b"Date\tApp Apple Identifier\tDownload Type\tCounts\n2026-01-01\t123\tFirst-time download\t6\n"
        ),
    }
    return inventory, rows


def open_fetch_form(page: Any, origin: str) -> Any:
    """Reach the protected fetch control through the product's owner entry."""
    page.goto(origin)
    page.locator("#main h1").wait_for()
    page.locator("#app-select").select_option("sample-one")
    page.get_by_role("button", name="Review results", exact=True).press("Enter")
    page.get_by_role("button", name="Open Search to App Store", exact=True).press("Enter")
    dialog = page.locator("#modal")
    dialog.get_by_role("button", name="Sign in", exact=True).press("Enter")
    page.locator("#identity-token").fill("synthetic_owner_identity_token")
    dialog.get_by_role("button", name="Verify my identity", exact=True).press("Enter")
    form = dialog.locator("#apple-performance-form")
    form.get_by_label("First event date").fill("2026-01-01")
    form.get_by_label("Last event date").fill("2026-01-05")
    return form


def fetch_apple_reports(page: Any, form: Any, fixture: AppleMetricsRouteTests) -> dict[str, Any]:
    """Drive the real owner route, worker, auto-readback and repeat request."""
    route = "/api/apps/sample-one/apple-analytics/performance-refresh"
    status_route = route + "-status"
    selection = dict(manifest_version=fixture.app["version"], start="2026-01-01", end="2026-01-05")
    inventory, rows = fetch_provider_fixture()

    def read_inventory(reader, store_app_id):
        assert store_app_id == "123"
        reader.hashes.append(digest(inventory))
        return inventory

    def read_segments(_reader, store_app_id, report_id, instance_id):
        assert store_app_id == "123"
        raw = gzip.compress(rows[(report_id, instance_id)], mtime=0)
        return [
            dict(id=instance_id, data=raw, size=len(raw), checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest())
        ]

    trigger = form.get_by_role("button", name="Fetch Apple analytics", exact=True)
    with (
        patch("mission_control.provider_reports.credential", return_value="fixture"),
        patch("mission_control.provider_reports.read_analytics", side_effect=read_inventory),
        patch("mission_control.provider_reports.read_instance_segments", side_effect=read_segments) as segments,
        patch("mission_control.openseo_transport.call_tool") as web,
    ):
        with page.expect_response(lambda item: item.url.endswith(route)) as response:
            trigger.press("Enter")
        assert response.value.ok, response.value.json()
        original = response.value.json()
        body = response.value.request.post_data_json
        assert all(body[key] == value for key, value in selection.items())
        assert original["status"] == "INVENTORY"
        assert original["store_app_id"] == "123"
        anonymous = OperatorClient(fixture.client.origin)
        anonymous.bootstrap()
        fixture.reject(anonymous, route, body, 403)
        fixture.reject(fixture.client, route.replace("sample-one", "sample-two"), body, 403)
        fixture.reject(fixture.client, status_route.replace("sample-one", "sample-two"), selection, 403)

        replay = fixture.post(route, body)
        assert replay["refresh_id"] == original["refresh_id"]
        assert replay["inventory_job_id"] == original["inventory_job_id"]
        assert run_once(fixture.store)
        collecting = fixture.post(status_route, selection)
        assert collecting["status"] == "COLLECTING"
        assert {item["report_family"] for item in collecting["files"]} == {DISCOVERY, DOWNLOADS}
        assert len(collecting["files"]) == 2

        page.locator("#close-modal").press("Enter")
        page.get_by_role("button", name="Open Search to App Store", exact=True).press("Enter")
        form.get_by_label("First event date").fill(selection["start"])
        form.get_by_label("Last event date").fill(selection["end"])
        with page.expect_response("**/apple-analytics/performance-refresh-status") as recovered:
            form.get_by_role("button", name="Check fetch status", exact=True).press("Enter")
        assert recovered.value.ok, recovered.value.json()
        assert recovered.value.json()["refresh_id"] == collecting["refresh_id"]

        with page.expect_response("**/apple-analytics/search-review", timeout=20000) as reviewed:
            assert run_once(fixture.store)
            assert run_once(fixture.store)
        assert reviewed.value.ok, reviewed.value.json()
        first_day = reviewed.value.json()["rows"][0]
        assert first_day["date"] == "2026-01-01"
        assert first_day["discovery"]["source_sha256"] and first_day["downloads"]["source_sha256"]
        result = page.locator("#apple-performance-results")
        expect(result.get_by_role("heading", name="Search to App Store", exact=True)).to_be_visible()
        day = result.get_by_role("row").filter(has_text="2026-01-01")
        for count in ("80", "0", "6"):
            expect(day.get_by_role("cell", name=count, exact=True)).to_be_visible()
        expect(result.get_by_role("row").filter(has_text="2026-01-05")).to_contain_text("Unavailable")
        ready = fixture.post(status_route, selection)
        assert ready["status"] == "READY" and len(ready["files"]) == 2
        receipt = page.locator("#apple-performance-receipt")
        receipt.locator("summary").press("Enter")
        expect(receipt.locator("details")).to_have_attribute("open", "")
        expect(receipt).to_contain_text(ready["refresh_id"])
        for item in ready["files"]:
            expect(receipt).to_contain_text(item["job_id"])
        assert page.locator("#apple-analytics-root").evaluate("(node) => node.scrollWidth <= node.clientWidth + 1")
        assert fixture.post(route, body)["refresh_id"] == ready["refresh_id"]
        assert segments.call_count == 2
        assert not run_once(fixture.store)

        with page.expect_response(lambda item: item.url.endswith(route)) as retried:
            trigger.press("Enter")
        assert retried.value.ok, retried.value.json()
        second = retried.value.json()
        assert second["inventory_job_id"] != original["inventory_job_id"]
        with page.expect_response("**/apple-analytics/search-review", timeout=20000):
            assert run_once(fixture.store)
        repeated = fixture.post(status_route, selection)
        assert repeated["status"] == "READY"
        assert {item["job_id"] for item in repeated["files"]} == {item["job_id"] for item in ready["files"]}
        assert segments.call_count == 2
        assert not run_once(fixture.store)
        web.assert_not_called()
    return dict(
        owner_fetch="INVENTORY_AND_TWO_SAVED_FILES",
        reopened_existing_receipt=True,
        cross_app_denied=True,
        duplicate_collection=False,
        unrelated_web_fetch=False,
    )


def fetch_journey(browser: Any, width: int, height: int) -> dict[str, Any]:
    """Start from a freshly isolated owner workspace without Apple report data."""
    fixture = AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
    fixture.setUp()
    origin = fixture.client.origin
    context = browser.new_context(viewport={"width": width, "height": height})
    context.route(
        "**/*", lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort()
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        saved_search_reading(fixture)
        with patch("mission_control.insights.Vault", FakeVault):
            result = fetch_apple_reports(page, open_fetch_form(page, origin), fixture)
        assert page.locator("#apple-analytics-root").evaluate("(node) => node.scrollWidth <= node.clientWidth + 1")
        assert not errors, errors
        return result
    finally:
        context.close()
        fixture.doCleanups()


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
        saved_search_reading(fixture)
        page.goto(origin)
        page.locator("#main h1").wait_for()
        page.locator("#app-select").select_option("sample-one")
        page.get_by_role("button", name="Review results", exact=True).press("Enter")
        page.get_by_role("button", name="Open Search to App Store", exact=True).press("Enter")
        dialog = page.locator("#modal")
        expect(dialog).to_contain_text("Sign in with the app owner account")
        expect(dialog).to_contain_text("WMM will return here")
        assert not apple_requests
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
        stop = (datetime.now() + timedelta(hours=1)).replace(second=0, microsecond=0)
        form.get_by_label("Stop checking at (optional)", exact=True).fill(stop.isoformat(timespec="minutes"))
        form.get_by_role("button", name="Enable refresh", exact=True).click()
        expect(root).to_contain_text("On · Report availability")
        expect(root).to_contain_text("Stop time:")
        schedules = AppleMetricsSchedules(fixture.store)
        schedule = schedules.get("sample-one")
        assert schedule is not None and schedule["stop_at"] == stop.timestamp()
        (OUT / f"bounded-watch-{width}.html").write_text(rendered_page(page), encoding="utf-8")
        form.get_by_label("Stop checking at (optional)", exact=True).scroll_into_view_if_needed()
        page.screenshot(path=str(OUT / f"bounded-watch-{width}.png"))
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
        rendered = rendered_page(page)
        (OUT / f"analytics-{width}.html").write_text(rendered, encoding="utf-8")
        root.get_by_role("button", name="Pause refresh", exact=True).focus()
        page.keyboard.press("Enter")
        expect(root).to_contain_text("PAUSED")
        paused = AppleMetricsSchedules(fixture.store).get("sample-one")
        assert paused is not None and paused["enabled"] is False
        # Report uses actual inventory counts and its caveats, not synthetic app metrics.
        reports = []
        page.on("popup", lambda popup: reports.append(popup))
        root.get_by_role("button", name="Inventory report / Save PDF", exact=True).click()
        page.wait_for_timeout(200)
        assert reports, "Report action did not open its printable report"
        report = reports[-1]
        report.wait_for_load_state()
        expect(report.locator("body")).to_contain_text("Apple analytics inventory")
        expect(report.locator("body")).to_contain_text("unavailable measurements remain unknown")
        report.close()
        performance_report(page, root, fixture, result)
        page.locator("#close-modal").click()
        search_to_store_report(page, fixture, width)
        page.locator("#close-modal").click()
        # An app switch must not retain another app's owner/source controls.
        page.locator("#app-select").select_option("sample-two")
        page.get_by_role("button", name="Review results", exact=True).press("Enter")
        page.get_by_role("button", name="Open Search to App Store", exact=True).press("Enter")
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
            schedule_stop_time="VERIFIED_LOCAL_TIME_TO_SAVED_DEADLINE",
            availability_watch="OWNER_OPT_IN_THEN_SCHEDULED_INVENTORY",
            impressions="OWNER_QUEUE_AND_UNKNOWN_IF_NO_DAILY_REPORT",
            apple_campaign_downloads="OWNER_READ_AND_UNKNOWN_WITHOUT_MATCHING_ROWS",
            app_store_performance="SAVED_COUNTS_SOURCES_AND_MISSING_DAYS_VERIFIED",
            search_to_app_store="OWNER_ONLY_SYNTHETIC_EVIDENCE_DISTINCT_ACTIONS_AND_ASSIGNED_RECEIPT_VERIFIED",
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
            observations = [
                dict(journey(browser, width, height), report_fetch=fetch_journey(browser, width, height))
                for width, height in ((1440, 900), (390, 844))
            ]
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
