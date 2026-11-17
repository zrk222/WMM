"""Exercise goal presets and exact expiry consent through the owner UI."""

import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

from mission_control import automation_proposal_schedule as rule_schedules
from mission_control.apple_metrics_schedule import AppleMetricsSchedules
from mission_control.automation_store import save as save_rules
from mission_control.common import canonical
from mission_control.db import connection
from mission_control.worker import run_once
from tests import test_agent_grants as fixture
from tests import test_apple_metrics_schedule as apple
from tests.test_automation_requirements import PROFILE as CONNECTION_ID
from tests.test_automation_rules import EXAMPLE
from tests.test_verified_review import OWNER

PROFILE = os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1"
ARTIFACTS = os.environ.get("WMM_GOAL_OWNER_ARTIFACTS")
if TYPE_CHECKING:
    from playwright.sync_api import BrowserContext


def add_owner_cookies(context: "BrowserContext", host: fixture.GrantTests) -> None:
    context.add_cookies(
        [
            {"name": c.name, "value": c.value, "domain": "127.0.0.1", "path": c.path or "/"}
            for c in host.owner.cookies
            if c.value is not None
        ]
    )


@unittest.skipUnless(PROFILE, "Run WMM_BROWSER_TEST_PROFILE=1 with Chromium installed")
class AutomationProfilesBrowserTests(unittest.TestCase):
    def test_profile_and_longer_expiry_render_exact_review_without_activation(self):
        from playwright.sync_api import expect, sync_playwright

        host = fixture.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        stamp = datetime.now(timezone.utc).isoformat()
        agent = dict(
            provider="codex",
            model="",
            label="Synthetic agent",
            capabilities=["campaign_plan", "original_copy"],
            tool=dict(executable="synthetic", fingerprint="synthetic-fingerprint"),
        )
        with connection(host.store.path) as db:
            db.execute(
                "INSERT INTO agent_connections VALUES(?,?,?,?,?,?,?,?)",
                ("sample-one", CONNECTION_ID, 1, canonical(agent), "TESTED", stamp, stamp, stamp),
            )

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            for width in (390, 1280):
                with (
                    self.subTest(width=width),
                    browser.new_context(viewport={"width": width, "height": 900}, timezone_id="UTC") as context,
                ):
                    add_owner_cookies(context, host)
                    context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                    context.route(
                        "**/*",
                        lambda route: (
                            route.continue_() if route.request.url.startswith(host.origin + "/") else route.abort()
                        ),
                    )
                    page = context.new_page()
                    page.goto(host.origin)
                    page.wait_for_function(
                        "(context) => {const state=context.state;return (() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one')(context.original);}",
                        arg={
                            "state": page.evaluate_handle("async () => (await import('/app.mjs')).state"),
                            "original": None,
                        },
                    )
                    nav = page.locator('[data-view="agents"]')
                    if not nav.is_visible():
                        page.locator("details").filter(has=nav).locator("summary").first.click()
                    nav.click()
                    page.get_by_role("button", name="Open automation controls").click()
                    page.get_by_role("switch", name="Review scope to switch ON").click()
                    form = page.locator("#standing-scope-form")
                    picker = form.get_by_label("Automation profile")
                    picker.select_option("organic")
                    expect(form.locator('[name="workflows"][value="hypit_caption_render"]')).to_be_checked()
                    form.locator('[name="workflows"][value="hypit_caption_render"]').uncheck()
                    expect(picker).to_have_value("custom")
                    picker.select_option("research")
                    form.get_by_label("Agent identifier").fill("fixture-agent")
                    form.get_by_label("Purpose").fill("Review app research and experiment evidence.")
                    form.get_by_label("Inference connection").select_option(CONNECTION_ID)
                    end = datetime.now(timezone.utc) + timedelta(days=2)
                    form.locator('[name="expires_at"]').fill(end.strftime("%Y-%m-%dT%H:%M"))
                    form.locator('[name="extended_expiry_consent"]').check()
                    with page.expect_response(lambda r: r.url.endswith("/automation-preview")) as preview:
                        form.get_by_role("button", name="Review exact agreement").click()
                    self.assertEqual(preview.value.status, 200)
                    response = preview.value.json()
                    self.assertTrue(response["proposal"]["extended_expiry_consent"])
                    self.assertFalse(response["authority_issued"])
                    expect(page.locator("#modal")).to_contain_text("You explicitly consented")
                    expect(page.locator("#modal")).to_contain_text(response["summary_hash"])
                    self.save_render(page, f"agreement-{width}", "#modal")
            browser.close()
        with connection(host.store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM automation_policies").fetchone()[0], 0)

    def test_watch_work_focuses_apple_availability_before_loading_the_saved_read(self):
        from playwright.sync_api import expect, sync_playwright

        host = fixture.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        app = host.store.app(apple.APP)
        host.store.save_app(apple.APP, dict(app["data"], store_app_id=apple.STORE_APP), app["version"])
        host.server.service.evidence(
            apple.APP,
            dict(
                kind="connection",
                title="Apple analytics",
                source="Synthetic fixture",
                data=dict(provider="app_store", store_app_id=apple.STORE_APP, env_ref=apple.REF, account_id="0"),
            ),
        )
        schedules = AppleMetricsSchedules(host.store)
        schedules.save(apple.APP, dict(enabled=True, version=None, interval_hours=24, report_id=apple.REPORT))
        self.assertEqual(schedules.tick(), 1)
        read = apple.AppleMetricsScheduleTests().waiting_read
        with (
            patch.dict(os.environ, {apple.REF: "synthetic-private-key"}),
            patch(
                "mission_control.provider_reports.read_analytics",
                side_effect=read,
            ),
        ):
            self.assertTrue(run_once(host.store))
        with connection(host.store.path) as db:
            db.execute(
                "UPDATE apple_metrics_schedules SET next_due=? WHERE app_id=?",
                (datetime.now(timezone.utc).timestamp() - 60, apple.APP),
            )
        before = schedules.get(apple.APP)
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            for width in (390, 1280):
                with (
                    self.subTest(width=width),
                    browser.new_context(viewport={"width": width, "height": 900}) as context,
                ):
                    add_owner_cookies(context, host)
                    context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                    page = context.new_page()
                    page.goto(host.origin)
                    page.wait_for_function(
                        "(context) => {const state=context.state;return (() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one')(context.original);}",
                        arg={
                            "state": page.evaluate_handle("async () => (await import('/app.mjs')).state"),
                            "original": None,
                        },
                    )
                    requests = []
                    page.on("request", lambda req, seen=requests: seen.append((req.method, req.url)))
                    nav = page.get_by_role("button", name="Watch the work", exact=True)
                    nav.press("Enter")
                    card = page.locator('[data-exception-state="WAITING_FOR_REPORTS"]')
                    expect(card).to_contain_text("App Store Connect")
                    expect(card).to_contain_text("This does not mean zero activity.")
                    expect(card).to_contain_text("next due")
                    expect(card).to_contain_text("The scheduled refresh is overdue.")
                    expect(card).to_contain_text("Check that the WMM worker is running")
                    self.save_render(page, f"waiting-{width}", '[aria-label="Workflow exceptions"]')
                    card.get_by_role("button", name="Review Apple report availability", exact=True).press("Enter")
                    panel = page.get_by_role("region", name="Apple analytics", exact=True)
                    expect(panel.get_by_role("heading", name="Keep Apple analytics current")).to_be_focused()
                    self.assertEqual([url for method, url in requests if method == "POST"], [])
                    panel.get_by_role("button", name="Review Apple analytics", exact=True).press("Enter")
                    expect(page.get_by_role("dialog")).to_contain_text("Inspect latest refresh")
                    self.assertEqual(
                        [url for method, url in requests if method == "POST"],
                        [f"{host.origin}/api/apps/{apple.APP}/apple-analytics/view"],
                    )
                    self.assertTrue(all(url.startswith(host.origin + "/") for _, url in requests))
                    page.keyboard.press("Escape")
                    page.locator("#app-select").select_option("sample-two")
                    page.wait_for_function(
                        "(context) => {const state=context.state;return (() => state.workspace?.app?.id === 'sample-two')(context.original);}",
                        arg={
                            "state": page.evaluate_handle("async () => (await import('/app.mjs')).state"),
                            "original": None,
                        },
                    )
                    nav.press("Enter")
                    expect(card).to_have_count(0)
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            browser.close()
        self.assertEqual(schedules.get(apple.APP), before)

    def test_watch_stopped_rule_review_is_owner_only_and_read_only(self) -> None:
        from playwright.sync_api import expect, sync_playwright

        class FixtureServer(fixture.Server):
            # Join request handlers before Windows removes the test database.
            daemon_threads = False

        host = fixture.GrantTests()
        with patch.object(fixture, "Server", FixtureServer):
            host.setUp()
        self.addCleanup(host.tearDown)
        app = "sample-one"
        owner = OWNER["principal"]
        path = f"/api/apps/{app}/automation/proposals"
        start = datetime.now(timezone.utc) - timedelta(hours=3)
        saved = save_rules(host.store, app, OWNER, EXAMPLE)
        assert saved is not None
        with patch.object(rule_schedules, "now", return_value=start.isoformat()):
            rule_schedules.configure(
                host.store,
                app,
                owner,
                dict(
                    enabled=True,
                    version=None,
                    app_version=1,
                    saved=dict(version=saved["version"], hash=saved["hash"]),
                    study=None,
                    interval_hours=1,
                    expires_at=(start + timedelta(days=2)).isoformat(),
                    max_runs=2,
                ),
            )
        rule_schedules.evaluate_due(host.store, app, start + timedelta(hours=1))
        original = host.store.app(app)
        host.store.save_app(app, dict(original["data"], name="Updated synthetic app"), original["version"])
        rule_schedules.evaluate_due(host.store, app, start + timedelta(hours=2))
        reason = "Internal fixture stop diagnostic"
        with connection(host.store.path, write=True) as db:
            db.execute("UPDATE automation_rule_schedules SET stopped_reason=? WHERE app_id=?", (reason, app))

        def database_state():
            with connection(host.store.path) as db:
                return tuple(
                    [tuple(row) for row in db.execute(query)]
                    for query in (
                        "SELECT * FROM automation_rule_schedules",
                        "SELECT * FROM automation_rule_runs",
                        "SELECT * FROM automation_rule_proposals",
                        "SELECT * FROM jobs",
                    )
                )

        before = database_state()
        status = rule_schedules.read(host.store, app, owner)
        assert status is not None
        self.assertEqual(status["status"], "BLOCKED")
        self.assertTrue(before[2], "The fixture must retain a real saved recommendation")
        self.assertEqual(before[3], [])
        card_selector = '[data-exception-state="RULE_SCHEDULE_BLOCKED"]'
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            for width in (320, 1440):
                with (
                    self.subTest(width=width),
                    browser.new_context(viewport={"width": width, "height": 900}) as context,
                ):
                    add_owner_cookies(context, host)
                    context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                    page = context.new_page()
                    requests = []
                    page.on("request", lambda request, seen=requests: seen.append((request.method, request.url)))
                    page.goto(host.origin)
                    page.get_by_role("button", name="Watch the work", exact=True).press("Enter")
                    card = page.locator(card_selector)
                    expect(card).to_contain_text("Scheduled reviews need attention")
                    expect(card).not_to_contain_text(reason)
                    expect(card).not_to_contain_text(saved["hash"])
                    self.assertNotIn(("GET", host.origin + path), requests)
                    with page.expect_response(lambda response: response.url == host.origin + path) as review:
                        card.get_by_role("button", name="Review scheduled rules", exact=True).press("Enter")
                    self.assertEqual(review.value.status, 200)
                    self.assertTrue(review.value.json()["proposals"])
                    disclosure = page.locator('[aria-label="Automation rule preview"] > details')
                    expect(disclosure).to_have_attribute("open", "")
                    expect(disclosure.locator(":scope > summary")).to_be_focused()
                    expect(page.locator("#automation-proposal-inbox")).to_contain_text("From an earlier app version")
                    self.assertEqual([method for method, _ in requests if method not in {"GET", "HEAD"}], [])
                    self.assertTrue(all(url.startswith(host.origin + "/") for _, url in requests))
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    page.locator("#app-select").select_option("sample-two")
                    page.wait_for_function(
                        "async () => (await import('/app.mjs')).state.workspace?.app?.id === 'sample-two'"
                    )
                    page.get_by_role("button", name="Watch the work", exact=True).press("Enter")
                    expect(card).to_have_count(0)
            with browser.new_context() as guest:
                guest.add_init_script("localStorage.setItem('growth-app','sample-one')")
                page = guest.new_page()
                page.goto(host.origin)
                page.get_by_role("button", name="Watch the work", exact=True).press("Enter")
                expect(page.locator(card_selector)).to_have_count(0)
                denied = guest.request.get(host.origin + path)
                self.assertIn(denied.status, (401, 403))
                self.assertNotIn(reason, denied.text())
            browser.close()
        self.assertEqual(database_state(), before)

    def save_render(self, page, name, selector):
        if not ARTIFACTS:
            return
        target = Path(ARTIFACTS)
        page.screenshot(path=str(target / f"{name}.png"))
        heading = page.locator("#main h1").first.evaluate("(node) => node.outerHTML")
        section = page.locator(selector).evaluate("(node) => node.outerHTML")
        css = (Path(__file__).resolve().parents[1] / "mission_control/static/style.css").read_text(encoding="utf-8")
        (target / f"{name}.html").write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>WMM workflow review</title><style>{css}</style></head>"
            f"<body><main>{heading}{section}</main></body></html>",
            encoding="utf-8",
        )
