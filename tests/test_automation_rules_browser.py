"""Saved automation simulation, through the real local owner UI."""

import json
import os
import unittest
from datetime import datetime, timedelta, timezone

from mission_control.automation_proposal_schedule import evaluate_due
from tests import test_agent_grants as fixture
from tests import test_automation_rule_report_integration as report_fixture


@unittest.skipUnless(os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1", "Enable the WMM browser profile")
class AutomationRulesBrowserTests(unittest.TestCase):
    def test_owner_can_simulate_an_older_version_at_desktop_and_mobile_widths(self):
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as runtime:
            executable = os.environ.get("WMM_TEST_CHROMIUM_PATH")
            browser = runtime.chromium.launch(executable_path=executable)
            for width in (390, 1440):
                with self.subTest(width=width):
                    host = fixture.GrantTests()
                    host.setUp()
                    try:
                        with browser.new_context(viewport={"width": width, "height": 900}) as context:
                            self.exercise(host, context, expect)
                    finally:
                        host.tearDown()

    def exercise(self, host, context, expect):
        context.add_cookies(
            [dict(name=c.name, value=c.value, domain="127.0.0.1", path=c.path or "/") for c in host.owner.cookies]
        )
        context.add_init_script("localStorage.setItem('growth-app','sample-one')")
        external = []

        def local_only(route):
            if route.request.url.startswith(host.origin + "/"):
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()

        context.route("**/*", local_only)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(host.origin)
        page.wait_for_function(
            "(context) => {const state=context.state;return (() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one')(context.original);}",
            arg={"state": page.evaluate_handle("async () => (await import('/app.mjs')).state"), "original": None},
        )
        nav = page.locator('[data-view="results"]')
        if not nav.is_visible():
            page.locator("details").filter(has=nav).locator("summary").first.click()
        nav.click()
        section = page.get_by_role("region", name="Automation rule preview")
        section.get_by_text("Automation rules", exact=True).press("Enter")
        section.get_by_text("Advanced rule editor", exact=True).press("Enter")
        editor = section.get_by_label("Rule to preview (JSON)")
        section.get_by_role("button", name="Save rules").click()
        expect(section.locator("#automation-rules-status")).to_contain_text("Saved version 1")
        second = json.loads(editor.input_value())
        second["rules"][0]["enabled"] = False
        editor.fill(json.dumps(second))
        section.get_by_role("button", name="Save rules").click()
        expect(section.locator("#automation-rules-status")).to_contain_text("Saved version 2")
        editor.fill("{}")
        section.get_by_role("button", name="Load latest into editor").click()
        expect(section.locator("#automation-rules-status")).to_contain_text("Loaded version 2")
        section.get_by_role("button", name="Preview draft").click()
        expect(section.locator("#automation-rules-result")).to_contain_text("Draft (not a saved version)")
        section.get_by_text("Saved rule versions", exact=True).press("Enter")
        section.get_by_role("button", name="Show saved versions").click()
        section.get_by_role("button", name="Preview saved version 1", exact=True).click()
        result = section.locator("#automation-rules-result")
        expect(result).to_contain_text("Saved version 1")
        expect(result).to_contain_text("review measurement setup")
        result.get_by_text("Facts used for this preview", exact=True).press("Enter")
        expect(result.get_by_role("rowheader", name="metrics.cohort_count")).to_be_visible()
        expect(result).to_contain_text("Preview fingerprint")
        self.assertFalse(json.loads(editor.input_value())["rules"][0]["enabled"])
        history = section.locator("#automation-rules-history")
        first_version = history.get_by_role("listitem").filter(has_text="Version 1")
        page.route(
            "**/automation/proposals", lambda route: route.fulfill(status=503, json={"error": "fixture"}), times=1
        )
        first_version.get_by_role("button", name="Run and save recommendations").click()
        expect(section.locator("#automation-proposal-status")).to_contain_text("Your change was saved")
        section.get_by_role("button", name="View saved recommendations").click()
        inbox = section.locator("#automation-proposal-inbox")
        expect(inbox).to_contain_text("Ready for review")
        expect(inbox).to_contain_text("review measurement setup")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        inbox.get_by_role("button", name="Dismiss recommendation").click()
        expect(inbox).to_contain_text("Dismissed")
        first_version.get_by_role("button", name="Review schedule").click()
        expect(inbox.get_by_role("group", name="Schedule local review for rule version 1")).to_be_visible()
        inbox.get_by_role("button", name="Start scheduled reviews").click()
        expect(inbox).to_contain_text("Rule version 1")
        expect(inbox).to_contain_text("Scheduled")
        inbox.get_by_role("button", name="Turn off reviews").click()
        expect(inbox).to_contain_text("Off")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.assertFalse(errors, errors)
        self.assertFalse(external, external)

    def test_owner_selects_a_real_private_report_and_reads_the_worker_receipt(self) -> None:
        from playwright._impl._api_structures import SetCookieParam
        from playwright.sync_api import expect, sync_playwright

        trial = report_fixture.RuleReportIntegrationTests(
            "test_match_saves_one_private_report_with_receipt_and_survives_restart"
        )
        self.addCleanup(trial.doCleanups)
        trial.setUp()
        host = trial.fixture.fixture
        origin = "http://127.0.0.1:" + str(host.server.server_port)
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(executable_path=os.environ.get("WMM_TEST_CHROMIUM_PATH"))
            with browser.new_context(viewport={"width": 390, "height": 900}) as session:
                cookies: list[SetCookieParam] = [
                    SetCookieParam(name=c.name, value=c.value or "", domain="127.0.0.1", path=c.path or "/")
                    for c in host.client.cookies
                ]
                session.add_cookies(cookies)
                session.add_init_script("localStorage.setItem('growth-app','sample')")
                session.route(
                    "**/*",
                    lambda route: route.continue_() if route.request.url.startswith(origin + "/") else route.abort(),
                )
                page = session.new_page()
                page.goto(origin)
                nav = page.locator('[data-view="results"]')
                if not nav.is_visible():
                    page.locator("details").filter(has=nav).locator("summary").first.click()
                nav.click()
                section = page.get_by_role("region", name="Automation rule preview")
                section.get_by_text("Automation rules", exact=True).press("Enter")
                section.get_by_text("Saved rule versions", exact=True).press("Enter")
                section.get_by_role("button", name="Show saved versions").click()
                section.get_by_role("button", name="Review schedule").click()
                inbox = section.locator("#automation-proposal-inbox")
                chooser = inbox.get_by_label("When a Results review is ready")
                expect(chooser).to_have_value("")
                chooser.select_option(index=1)
                inbox.get_by_role("button", name="Start scheduled reviews").click()
                expect(inbox).to_contain_text("This schedule can save one private report")
                evaluate_due(trial.store, trial.app, datetime.now(timezone.utc) + timedelta(hours=25))
                section.get_by_role("button", name="View saved recommendations").click()
                expect(inbox).to_contain_text("Private report saved.")
                expect(inbox.get_by_role("button", name="Open private campaign reports")).to_be_visible()
                section.get_by_role("button", name="Review schedule").click()
                chooser.select_option(index=1)
                inbox.get_by_role("button", name="Start scheduled reviews").click()
                expect(inbox).to_contain_text("This schedule can save one private report")
                expect(inbox).not_to_contain_text("Private report saved.")
                self.assertEqual(len(trial.receipts()), 2)
                self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                inbox.get_by_role("button", name="Turn off reviews").click()
                expect(inbox).to_contain_text("Off")
