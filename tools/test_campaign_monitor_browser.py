"""Real owner monitor UI, protected HTTP and synthetic worker pause acceptance."""

from pathlib import Path
from datetime import datetime, timedelta
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from tests.test_campaign_monitor_integration import CampaignMonitorIntegrationTests
from mission_control.db import connection

OUT = ROOT / ".factory/goal-first-automation"


def run(browser, width):
    f = CampaignMonitorIntegrationTests()
    f.setUp()
    context = browser.new_context(viewport={"width": width, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f.client.origin)
        page.wait_for_function("() => state.workspace?.app?.id===state.app")
        page.locator("#app-select").select_option("sample")
        page.wait_for_function("() => state.app==='sample' && state.workspace?.app?.id==='sample'")
        page.locator("#navigation > [data-view=activity]").click()
        page.get_by_role("button", name="Sign in for verified review", exact=True).click()
        page.get_by_label("GitHub identity token", exact=True).fill("synthetic_owner_identity_token")
        page.get_by_role("button", name="Verify my identity", exact=True).click()
        expect(page.get_by_role("button", name="Sign out of review session")).to_be_visible()
        page.get_by_role("button", name="Monitor approved campaigns", exact=True).click()
        page.locator('[data-action=campaign-monitor-select][data-id="' + f.scope["scope_id"] + '"]').click()
        form = page.locator("#campaign-monitor-form")
        form.locator("[name=targets]").check()
        form.locator("[name=expires_at]").fill((datetime.now() + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"))
        form.locator("[name=configuration_drift]").check()
        form.locator("[name=max_pause_attempts]").fill("1")
        form.get_by_role("button", name="Review exact monitoring plan", exact=True).click()
        review = page.locator("#monitor-review")
        expect(review).to_contain_text("Pause after verified configuration drift")
        expect(review).to_contain_text("80")
        expect(review).to_contain_text("cannot publish, create, activate")
        assert f.job() is None
        review.get_by_role("button", name="Approve exact monitor", exact=True).click()
        progress = page.locator("#monitor-progress")
        expect(progress).to_contain_text("Monitoring active")
        f.wire.objects[f.intent["ids"]["adset"]]["lifetime_budget"] = 999
        assert f.server.runner.poll()
        progress.get_by_role("button", name="Refresh monitor receipts", exact=True).click()
        progress = page.locator("#monitor-progress")
        expect(progress).to_contain_text("Protective pause verified")
        expect(progress).to_contain_text("SUCCEEDED")
        expect(progress).to_contain_text("Provider units reserved")
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        page.screenshot(path=str(OUT / f"monitor-{width}.png"), full_page=True)
        (OUT / f"monitor-{width}.html").write_text(page.content(), encoding="utf-8")
        with page.expect_popup() as info:
            progress.get_by_role("button", name="Monitor report / Save PDF", exact=True).click()
        report = info.value
        expect(report.locator("body")).to_contain_text("Campaign monitoring")
        assert "synthetic-token" not in report.locator("body").inner_text()
        assert "synthetic-secret" not in report.locator("body").inner_text()
        report.close()
        progress.get_by_role("button", name="Turn monitor OFF", exact=True).click()
        expect(page.locator("#monitor-progress")).to_contain_text("Monitoring off")
        assert f.job()["status"] == "SUCCEEDED"
        with connection(f.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='UNKNOWN' WHERE id=?", (f.intent["id"],))
        page.locator("#close-modal").click()
        page.locator("#navigation > details > summary").click()
        page.locator("#navigation [data-view=weekly]").click()
        page.get_by_role("button", name="Refresh review", exact=True).click()
        card = page.locator("article.panel").filter(
            has=page.get_by_role("heading", name="Reconcile uncertain campaign delivery", exact=True)
        )
        expect(card).to_be_visible()
        card.get_by_role("button", name="Open recovery", exact=True).click()
        expect(page.locator("#campaign-progress")).to_contain_text("UNKNOWN")
        page.locator("#close-modal").click()
        page.locator("#navigation > [data-view=activity]").click()
        page.get_by_role("button", name="Sign out of review session", exact=True).click()
        expect(page.get_by_role("button", name="Sign in for verified review", exact=True)).to_be_visible()
        page.locator("#navigation [data-view=weekly]").click()
        expect(page.get_by_role("heading", name="Reconcile uncertain campaign delivery", exact=True)).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        assert not errors, errors
        return dict(
            width=width,
            status="PASS",
            exact_review=True,
            no_job_before_approval=True,
            worker_pause="SYNTHETIC_PAUSED_VERIFIED",
            private_report=True,
            owner_exception_recovery=True,
            signed_out_private_cache_hidden=True,
            off=True,
            no_overflow=True,
            javascript_errors=errors,
        )
    except Exception:
        print(json.dumps({"errors": errors, "body": page.locator("body").inner_text()[-5000:]}))
        raise
    finally:
        context.close()
        f.doCleanups()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            observations = [run(browser, w) for w in (1440, 390)]
        finally:
            browser.close()
    result = dict(status="PASS", observations=observations)
    (OUT / "monitor-browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
