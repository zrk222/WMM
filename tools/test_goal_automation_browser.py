"""Actual desktop/mobile owner setup and scheduled batch review; synthetic providers."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from playwright.sync_api import Browser, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run(browser: Browser, width: int, out: Path) -> dict[str, object]:
    from mission_control.db import connection
    from mission_control.operator_client import ClientError, OperatorClient
    from mission_control.server import Server
    from mission_control.store import Store
    from mission_control.worker import jobs
    from tests.test_campaign_access import CampaignGatewayTests
    from tests.test_verified_review import OWNER_TOKEN

    class BrowserCampaignFixture(CampaignGatewayTests):
        # GrantTests.setUp supplies these concrete attributes through setUp_base.
        origin: str
        server: Server
        store: Store

    f = BrowserCampaignFixture()
    f.setUp()
    app = f.store.app("sample-one")
    f.store.save_app(
        app["id"],
        dict(
            app["data"],
            currency="",
            job="Compare onboarding",
            audience="Test founders",
            activation="Complete a test step",
            release="test",
            locale="en-US",
        ),
        app["version"],
    )
    link = "https://example.test/app?utm_source=facebook&utm_campaign=" + ("sample-" * 45)
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    errors: list[str] = []
    posts: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
    try:
        page.add_init_script(
            "window.wmmStyleViolations=[];document.addEventListener('securitypolicyviolation',e=>{if(e.effectiveDirective==='style-src-attr')window.wmmStyleViolations.push(e.effectiveDirective)});"
        )
        page.goto(f.origin)
        page.wait_for_function(
            "(state) => state.workspace?.app?.id===state.app",
            arg=page.evaluate_handle("async () => (await import('/app.mjs')).state"),
        )
        channels = page.get_by_role("list", name="Video channels", exact=True)
        expect(channels.locator("svg")).to_have_count(5)
        for name in ("Facebook Page", "Instagram Reels", "TikTok", "YouTube Shorts", "LinkedIn"):
            expect(channels).to_contain_text(name)
        expect(channels).to_have_css("list-style-type", "none")
        expect(channels.locator("svg").first).to_have_css("margin-right", "6px")
        assert page.evaluate("window.wmmStyleViolations") == []
        page.get_by_role("button", name="Build your campaign plan", exact=True).press("Enter")
        plan = page.get_by_role("dialog", name="Campaign plan")
        expect(plan).to_contain_text("this plan does not publish or spend")
        expect(plan).to_contain_text("Proof to verify")
        expect(plan).to_contain_text("no spend authorized")
        (out / f"campaign-plan-{width}.html").write_text(page.content(), encoding="utf-8")
        for label, suffix in (("Download Markdown", ".md"), ("Download JSON", ".json")):
            with page.expect_download() as event:
                plan.get_by_role("button", name=label, exact=True).press("Enter")
            assert event.value.suggested_filename.endswith(suffix)
            assert event.value.path().stat().st_size > 0
        page.keyboard.press("Escape")
        expect(plan).to_be_hidden()
        assert not posts
        page.locator("#navigation > [data-view=activity]").click()
        expect(page.locator("[data-live-worker]")).to_contain_text("Worker starting")
        f.server.runner.supervision.attempt("queue", lambda: 1 / 0)
        f.server.runner.supervision.finish()
        page.get_by_role("button", name="Refresh progress", exact=True).click()
        expect(page.locator("[data-live-worker]")).to_contain_text("Worker needs attention")
        host = page.get_by_text("Keep approved work running", exact=True)
        host.focus()
        host.press("Enter")
        expect(page.get_by_role("link", name="Open the private-host setup guide (new tab)")).to_be_visible()
        expect(page.get_by_text("Closing this browser leaves the worker running.", exact=False)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        styles = page.evaluate(r"""() => Array.from(document.styleSheets).flatMap(sheet=>{
   try{return Array.from(sheet.cssRules).map(rule=>rule.cssText)}catch{return []}
  }).join('\n')""")
        html = page.locator("#main .page-heading, #workflow-monitor").evaluate_all(
            "(nodes) => nodes.map(node => node.outerHTML).join('')"
        )
        (out / f"worker-health-{width}.html").write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Watch the work</title><style>'
            + styles
            + "</style><main>"
            + html
            + "</main></html>",
            encoding="utf-8",
        )
        host.press("Enter")
        f.server.runner.supervision.stopped()
        expect(page.locator("[data-live-worker]")).to_contain_text("Worker stopped")
        page.get_by_role("button", name="Sign in for verified review", exact=True).click()
        page.get_by_label("GitHub identity token", exact=True).fill(OWNER_TOKEN)
        page.get_by_role("button", name="Verify my identity", exact=True).click()
        expect(page.get_by_role("button", name="Sign out of review session")).to_be_visible()
        page.locator("#navigation > [data-view=overview]").click()
        page.get_by_role("button", name="Run an approved campaign", exact=True).click()
        assert (
            page.evaluate("async () => ((await import('/app.mjs')).state.workspace.agent_access.profiles.length)") == 0
        )
        posts.clear()
        page.get_by_role("button", name="Check connections for this goal", exact=True).click()
        expect(page.locator("#goal-readiness-mode")).to_be_visible()
        expect(page.locator("#goal-readiness-form")).to_have_count(0)
        assert not posts, posts
        page.screenshot(path=str(out / f"agent-mode-{width}.png"))
        (out / f"agent-mode-{width}.html").write_text(page.content(), encoding="utf-8")
        page.get_by_role("button", name="Use my personal agent", exact=True).press("Enter")
        expect(page.get_by_role("button", name="Issue an agent grant", exact=True)).to_be_visible()
        expect(page.locator("#goal-readiness-form")).to_have_count(0)
        assert posts == [f.origin + "/api/apps/sample-one/agent-grants/list"], posts
        with connection(f.store.path) as db:
            assert db.execute("SELECT count(*) FROM agent_grants").fetchone()[0] == 0
        page.get_by_role("button", name="Issue an agent grant", exact=True).click()
        form = page.locator("#control-grant-form")
        form.get_by_label("Agent identifier", exact=True).fill("external-browser-agent")
        form.get_by_label("Maximum admitted attempts", exact=True).fill("2")
        form.locator("[data-task-advanced] summary").click()
        form.locator('[name=operations][value="growth.history"]').check()
        form.get_by_role("button", name="Issue scoped grant", exact=True).click()
        token = page.locator("[data-grant-secret]").input_value()
        agent = OperatorClient(f.origin, grant_token=token)
        agent.call(dict(app_id="sample-one", operation="growth.history", input={}))
        assert not jobs(f.store, "sample-one")
        assert f.wire.posts == 0
        page.locator("#close-modal").click()
        page.get_by_role("button", name="Check connections for this goal", exact=True).click()
        page.get_by_role("button", name="Use my personal agent", exact=True).click()
        page.get_by_role("button", name="Review revocation", exact=True).click()
        with page.expect_response(f.origin + "/api/apps/sample-one/agent-grants/revoke") as revoked:
            page.get_by_role("button", name="Revoke this grant", exact=True).click()
        assert revoked.value.ok
        try:
            agent.call(dict(app_id="sample-one", operation="growth.history", input={}))
        except ClientError:
            pass
        else:
            raise AssertionError("Revoked external grant was admitted")
        token = ""
        agent = None
        page.locator("#close-modal").click()
        page.get_by_role("button", name="Check connections for this goal", exact=True).click()
        page.get_by_role("button", name="Check WMM-managed setup", exact=True).press("Enter")
        form = page.locator("#goal-readiness-form")
        form.get_by_label("Agent identifier", exact=True).fill("grok-bot")
        form.locator("[name=social_connection_ids]").check()
        form.get_by_role("button", name="Check selected connections", exact=True).click()
        expect(
            page.get_by_text(
                "Review campaign scope to approve the exact posts, accounts, limits and expiry.", exact=True
            )
        ).to_be_visible()
        code = page.locator("#modal-body code").filter(has_text="EXACT_OWNER_CAMPAIGN_SCOPE_REQUIRED")
        inference_code = page.locator("#modal-body code").filter(has_text="FRESH_INFERENCE_TEST_REQUIRED")
        expect(code).to_be_hidden()
        expect(inference_code).to_be_hidden()
        details = page.locator("#modal-body summary").filter(has_text="Technical details")
        details.focus()
        details.press("Enter")
        expect(code).to_be_visible()
        expect(inference_code).to_be_visible()
        details.press("Enter")
        expect(code).to_be_hidden()
        expect(page.locator("#modal-body")).to_contain_text("No approval, grant, job or campaign")
        expect(page.locator("#modal-body")).to_contain_text("Repair agent connection")
        assert f.wire.posts == 0
        assert not jobs(f.store, "sample-one")
        page.screenshot(path=str(out / f"readiness-{width}.png"))
        (out / f"readiness-{width}.html").write_text(page.content(), encoding="utf-8")
        page.get_by_role("button", name="Review campaign scope", exact=True).click()
        form = page.locator("#campaign-scope-form")
        form.locator("[name=connection_id]").select_option(f.connection)
        form.get_by_label("Approved post copy", exact=True).fill(f.message)
        form.get_by_label("App or landing-page link", exact=True).fill(link)
        form.get_by_label("Rights and claims evidence", exact=True).fill("Original synthetic app claim evidence")
        form.get_by_label("Maximum Meta requests", exact=True).fill("70")
        form.get_by_role("button", name="Review exact automation scope", exact=True).click()
        preview = page.locator("#campaign-review")
        expect(preview.get_by_role("heading", name="What you’re approving")).to_be_visible()
        assert page.locator("#modal").evaluate("(modal) => modal.scrollTop === 0")
        assert page.locator("#modal").get_by_role("complementary", name="Task guide").count() == 0
        steps = preview.get_by_role("list", name="Campaign approval progress")
        expect(steps.locator('[aria-current="step"]')).to_contain_text("Review limits")
        expect(steps.get_by_text("Run separately")).to_be_visible()
        expect(preview).to_contain_text("organic only")
        expect(preview).to_contain_text("no paid ads")
        expect(preview).to_contain_text("Maximum Meta requests")
        assert preview.get_by_text("Meta ad account", exact=True).count() == 0
        expect(preview.get_by_role("heading", name="Exact post copy and links")).to_be_visible()
        expect(preview.get_by_text("Proposed post link", exact=False).locator("span")).to_have_text(link)
        requests = preview.get_by_text("Maximum Meta requests", exact=True).locator("..").locator("dd")
        expect(requests).to_have_text("70")
        expect(preview).to_contain_text("does not publish, schedule, or spend now")
        with connection(f.store.path) as db:
            assert db.execute("SELECT status FROM campaign_scopes").fetchone()[0] == "DRAFT"
        assert f.wire.posts == 0 and not jobs(f.store, "sample-one")
        assert page.locator("#modal").evaluate("(modal) => modal.scrollWidth <= modal.clientWidth")
        page.screenshot(path=str(out / f"campaign-draft-agreement-{width}.png"))
        page.get_by_role("button", name="Approve scope and enable automation", exact=True).click()
        expect(page.locator("#campaign-progress")).to_contain_text("ACTIVE")
        page.get_by_role("button", name="Schedule approved posts", exact=True).click()
        form = page.locator("#campaign-schedule-form")
        form.locator("[name=due_0]").fill((datetime.now() + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M"))
        form.get_by_role("button", name="Review exact scheduled batch", exact=True).click()
        expect(page.locator("#campaign-schedule-review")).to_contain_text(f.message)
        assert f.wire.posts == 0
        assert not jobs(f.store, "sample-one")
        page.get_by_role("button", name="Approve exact batch and schedule", exact=True).click()
        expect(page.locator("#schedule-batch-state")).to_have_text("Scheduled")
        expect(page.locator("#schedule-live-stage")).to_contain_text("WMM must remain running")
        page.screenshot(path=str(out / f"schedule-{width}.png"))
        (out / f"schedule-{width}.html").write_text(page.content(), encoding="utf-8")
        with page.expect_popup() as report_info:
            page.get_by_role("button", name="Report / Save PDF", exact=True).click()
        report = report_info.value
        expect(report.locator("body")).to_contain_text("Scheduled campaign batch")
        assert f.message not in report.locator("body").inner_text()
        assert OWNER_TOKEN not in report.locator("body").inner_text()
        report.close()
        page.get_by_role("button", name="Turn scheduled batch OFF", exact=True).click()
        expect(page.locator("#campaign-schedule-progress")).to_contain_text("CANCELLED")
        page.locator("#close-modal").click()
        page.reload()
        page.wait_for_function(
            "(state) => state.workspace?.app?.id===state.app",
            arg=page.evaluate_handle("async () => (await import('/app.mjs')).state"),
        )
        page.locator("#navigation > details > summary").click()
        page.locator("#navigation [data-view=connections]").click()
        page.get_by_role("button", name="Review campaign automation", exact=True).click()
        page.get_by_role("button", name="Inspect scheduled batch", exact=True).click()
        expect(page.locator("#schedule-batch-state")).to_have_text("Schedule off")
        expect(page.locator("#schedule-live-stage")).to_contain_text("No new items will start")
        page.locator("#close-modal").click()
        page.locator("#navigation > [data-view=overview]").click()
        page.locator("#goal-advanced > summary").click()
        page.get_by_role("button", name="Review combined automation agreement", exact=True).click()
        form = page.locator("#agreement-form")
        form.locator("[name=schedule_batch_id]").select_option(index=1)
        form.get_by_role("button", name="Review combined agreement", exact=True).click()
        expect(page.locator("#agreement-summary")).to_contain_text("No execution authority is issued")
        expect(page.locator("#agreement-summary")).to_contain_text(f.message)
        approved_link = page.locator("#agreement-summary").get_by_text("Approved post link", exact=False)
        expect(approved_link.locator("span")).to_have_text(link)
        expect(approved_link.locator("a")).to_have_count(0)
        assert page.locator("#modal").evaluate("(modal) => modal.scrollWidth <= modal.clientWidth")
        expect(page.locator("#agreement-summary")).to_contain_text("Scheduled executor when the batch is active")
        expect(page.locator("#agreement-summary")).to_contain_text("WMM background worker")
        page.screenshot(path=str(out / f"agreement-{width}.png"))
        (out / f"agreement-{width}.html").write_text(page.content(), encoding="utf-8")
        with page.expect_popup() as agreement_info:
            page.get_by_role("button", name="Agreement report / Save PDF", exact=True).click()
        agreement = agreement_info.value
        expect(agreement.locator("body")).to_contain_text("Combined automation agreement")
        exported = agreement.locator("body").inner_text()
        assert f.message not in exported and link not in exported and OWNER_TOKEN not in exported
        agreement.close()
        assert f.wire.posts == 0
        assert not jobs(f.store, "sample-one")
        saved_runs = (
            ("campaign_post", "Publish approved Facebook post", "BLOCKED"),
            ("campaign_ad", "Launch approved Meta ad", "BLOCKED"),
            ("campaign_monitor", "Check approved campaign delivery", "SUCCEEDED"),
            ("campaign_owner_report", "Save private campaign report", "SUCCEEDED"),
            ("sync", "Provider synchronization", "SUCCEEDED"),
            ("unknown_fixture", "Saved workflow run", "BLOCKED"),
        )
        with connection(f.store.path) as db:
            for action, _, job_status in saved_runs:
                db.execute(
                    "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                    (action, "sample-one", action, "{}", job_status, "2026-11-13", "2026-11-13", action),
                )
        page.reload()
        page.locator("#navigation > [data-view=activity]").click()
        for action, title, _ in saved_runs:
            row = page.locator(f'button[data-action="job"][data-id="{action}"]')
            expect(row).to_contain_text(title, timeout=5000)
        expect(page.locator('button[data-action="job"][data-id="campaign_post"]')).to_contain_text("BLOCKED")
        (out / f"saved-runs-{width}.html").write_text(page.content(), encoding="utf-8")
        assert not errors, errors
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        return dict(
            width=width,
            campaign_plan_and_both_exports_without_writes=True,
            live_worker_and_private_host_guidance=True,
            personal_agent_without_profile=True,
            explicit_grant_and_revocation=True,
            managed_readiness_guards=True,
            owner_readiness=True,
            blockers_preserved=True,
            exact_draft_link_before_activation=True,
            exact_meta_request_ceiling=70,
            exact_schedule_review=True,
            exact_post_link_visible_in_private_review=True,
            no_effect_before_due=True,
            off=True,
            durable_reload=True,
            report_privacy=True,
            saved_campaign_runs_have_distinct_labels=True,
            campaign_does_not_select_agent=True,
            javascript_errors=errors,
            provider="SYNTHETIC_ONLY",
        )
    finally:
        context.close()
        f.tearDown()
        f.doCleanups()


def main() -> None:
    out = ROOT / ".factory/agent-mode-browser"
    out.mkdir(parents=True, exist_ok=True)
    with (
        sync_playwright() as p,
        patch(
            "mission_control.campaign_transport.MetaTransport.request",
            side_effect=AssertionError("Real provider forbidden"),
        ),
    ):
        browser = p.chromium.launch()
        result = {"status": "PASS", "observations": [run(browser, w, out) for w in (1440, 390)]}
        browser.close()
    (out / "automation-browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
