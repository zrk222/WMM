"""Actual paid-agreement UI/PDF checks using synthetic historical SQLite state.

The existing AutomationAgreementTests method seeds a saved 80 CAD paid intent
under a 100 CAD scope, then marks its dispatch pending. This demonstrates owner
review and reconciliation guidance, never provider delivery or business lift.
"""

from pathlib import Path
import hashlib
import json
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Direct script execution needs the repository root before project imports.

from playwright.sync_api import expect, sync_playwright  # noqa: E402
from mission_control.db import connection  # noqa: E402
from mission_control.server import Server  # noqa: E402
from tests.test_automation_agreement import AutomationAgreementTests, BATCH, SCOPE  # noqa: E402
from tests.test_verified_review import OWNER, OWNER_TOKEN, synthetic_identity  # noqa: E402

OUT = ROOT / ".factory" / "goal-first-automation"


def run(browser, width):
    """Exercise real owner session, current UI, immutable review and private PDF."""
    fixture = AutomationAgreementTests(
        "test_scheduled_request_paid_historical_end_budget_target_and_remote_ids"
    )
    fixture.setUp()
    server = None
    thread = None
    context = None
    try:
        fixture.test_scheduled_request_paid_historical_end_budget_target_and_remote_ids()
        # Saved local authority becomes blocked after its inference revision
        # changes. The agreement must show its existing repair instruction.
        with connection(fixture.store.path) as db:
            db.execute("UPDATE agent_connections SET version=version+1")
        server = Server(("127.0.0.1", 0), fixture.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = "http://127.0.0.1:" + str(server.server_port)
        context = browser.new_context(viewport=dict(width=width, height=1000))
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(origin)
        page.wait_for_function("() => state.workspace?.app?.id === state.app")
        page.locator("#navigation > [data-view=activity]").click()
        page.get_by_role(
            "button", name="Sign in for verified review", exact=True
        ).click()
        page.get_by_label("GitHub identity token", exact=True).fill(OWNER_TOKEN)
        page.get_by_role("button", name="Verify my identity", exact=True).click()
        expect(
            page.get_by_role("button", name="Sign out of review session")
        ).to_be_visible()
        page.locator("#navigation > [data-view=overview]").click()
        baseline = fixture.fixture.dump()
        requests = []
        page.on(
            "request", lambda request: requests.append((request.method, request.url))
        )
        page.locator("#goal-advanced > summary").click()
        page.get_by_role(
            "button", name="Review combined automation agreement", exact=True
        ).click()
        form = page.locator("#agreement-form")
        form.locator("[name=workflow_policy_id]").select_option(
            fixture.issued["policy_id"]
        )
        form.locator("[name=schedule_batch_id]").select_option(BATCH)
        form.get_by_role("button", name="Review combined agreement", exact=True).click()
        summary = page.locator("#agreement-summary")
        for text in (
            "No execution authority is issued",
            "NEEDS_RECONCILIATION",
            "Exact media budget 80 minor CAD",
            "Maximum media commitment 100 minor CAD; held 80",
            "Retained commitment 80 minor CAD",
            "Audience countries CA",
            "campaign: 101",
            "adset: 102",
            "creative: 103",
            "ad: 104",
            "SCHEDULE_ITEM_NEEDS_REVIEW",
            "Review current owner, app, credential and expiry facts before reapproval.",
            "Stop rules:",
            "Uncertain dispatch: reconcile before retry",
            "Scheduled executor when the batch is active",
            "WMM background worker",
            "Owner " + OWNER["principal"],
            "Batch " + BATCH,
            "Campaign scope " + SCOPE,
        ):
            expect(summary).to_contain_text(text)
        expect(summary).to_contain_text("PENDING_ACTIVATE_campaign")
        expect(summary).to_contain_text("Promotion of verified Page post 123_777")
        assert not errors, errors
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert summary.evaluate("(node) => node.scrollWidth <= node.clientWidth + 1")
        page.screenshot(path=str(OUT / f"agreement-paid-{width}.png"), full_page=True)
        (OUT / f"agreement-paid-{width}.html").write_text(
            page.content(), encoding="utf-8"
        )
        summary.locator("article").first.scroll_into_view_if_needed()
        page.screenshot(
            path=str(OUT / f"agreement-paid-detail-{width}.png"), full_page=True
        )
        with page.expect_popup() as report_info:
            page.get_by_role(
                "button", name="Agreement report / Save PDF", exact=True
            ).click()
        report = report_info.value
        expect(report.locator("body")).to_contain_text("Combined automation agreement")
        expect(report.locator("body")).to_contain_text("100 CAD")
        report_text = report.locator("body").inner_text()
        for expected in ("WMM background worker", "Owner " + OWNER["principal"],
                         "Batch " + BATCH, "Campaign scope " + SCOPE):
            assert expected in report_text, expected
        for private in (
            fixture.post["message"],
            OWNER_TOKEN,
            "PRIVATE-TOKEN",
            "PRIVATE-CONFIG",
            "synthetic-private-marker-never-public",
        ):
            assert private not in report_text
        report.screenshot(
            path=str(OUT / f"agreement-paid-report-{width}.png"), full_page=True
        )
        (OUT / f"agreement-paid-report-{width}.html").write_text(
            report.content(), encoding="utf-8"
        )
        report.close()
        assert baseline == fixture.fixture.dump(), (
            "Read-only agreement changed durable state"
        )
        allowed = (
            "/agent-grants/automation-status",
            "/campaigns/history",
            "/campaigns/schedule-history",
            "/agent-grants/agreement-preview",
        )
        writes = [url for method, url in requests if method != "GET"]
        assert len(writes) == 4, writes
        assert all(any(url.endswith(suffix) for suffix in allowed) for url in writes), (
            writes
        )
        assert not errors, errors
        return dict(
            width=width,
            status="PASS",
            protected_owner_http=True,
            scheduled_executor_identified=True,
            owner_and_exact_scope_identified=True,
            paid_budget_minor=80,
            scope_ceiling_minor=100,
            currency="CAD",
            pending_reconciliation_visible=True,
            exact_receipt_ids=True,
            local_repair_visible=True,
            stop_rules_visible=True,
            pdf_privacy=True,
            no_overflow=True,
            no_business_writes=True,
            read_only_posts=len(writes),
            provider="SYNTHETIC_HISTORY_ONLY",
            javascript_errors=errors,
        )
    finally:
        if context is not None:
            context.close()
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join()
        fixture.doCleanups()


def main():
    """Forbid inference, provider and vault access while running both viewports."""
    sources = [
        "tools/test_agreement_paid_browser.py",
        "mission_control/static/guided-workflow.js",
        "mission_control/static/app.js",
        "mission_control/automation_agreement.py",
        "tests/test_automation_agreement.py",
    ]
    initial_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources
    }
    OUT.mkdir(parents=True, exist_ok=True)
    with (
        sync_playwright() as playwright,
        patch(
            "mission_control.operator_identity.github_read",
            side_effect=synthetic_identity,
        ),
        patch(
            "mission_control.campaign_transport.MetaTransport.request",
            side_effect=AssertionError("Provider access forbidden"),
        ),
        patch(
            "mission_control.agent_access.AgentAccess.secret",
            side_effect=AssertionError("Inference secret access forbidden"),
        ),
        patch(
            "mission_control.social_secrets.Secrets.load",
            side_effect=AssertionError("Social vault access forbidden"),
        ),
    ):
        browser = playwright.chromium.launch()
        try:
            observations = [run(browser, width) for width in (1440, 390)]
        finally:
            browser.close()
    final_hashes = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources
    }
    assert initial_hashes == final_hashes, (
        "Acceptance sources changed while the browser ran"
    )
    result = dict(
        status="PASS",
        observations=observations,
        source_sha256=final_hashes,
    )
    (OUT / "agreement-paid-browser.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
