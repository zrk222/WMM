"""Saved automation simulation, through the real local owner UI."""
import json
import os
import unittest

from tests import test_agent_grants as fixture


@unittest.skipUnless(os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1", "Enable the WMM browser profile")
class AutomationRulesBrowserTests(unittest.TestCase):
    def test_owner_can_simulate_an_older_version_at_desktop_and_mobile_widths(self):
        from playwright.sync_api import expect, sync_playwright

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
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
        context.add_cookies([dict(name=c.name, value=c.value, domain="127.0.0.1", path=c.path or "/")
                             for c in host.owner.cookies])
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
        page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one'")
        nav = page.locator('[data-view="results"]')
        if not nav.is_visible():
            page.locator("details").filter(has=nav).locator("summary").first.click()
        nav.click()
        section = page.get_by_role("region", name="Automation rule preview")
        section.get_by_text("Automation rules", exact=True).press("Enter")
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
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        self.assertFalse(errors, errors)
        self.assertFalse(external, external)
