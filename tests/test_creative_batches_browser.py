"""Real local browser exercise of the owner-reviewed finite batch flow."""
import unittest

from playwright.sync_api import expect, sync_playwright

from mission_control.db import connection
from tests import test_agent_grants as grants
from tests.test_creative_rendering import prepared_render


class CreativeBatchBrowserTests(unittest.TestCase):
    def test_owner_reviews_queues_and_cancels_in_desktop_and_mobile_viewports(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for width in (1440, 390):
                    with self.subTest(width=width):
                        fixture = grants.GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
                        fixture.setUp()
                        context = None
                        try:
                            app = fixture.store.app("sample-one")
                            fixture.store.save_app("sample-one", dict(app["data"], job="Synthetic job",
                                audience="Synthetic audience", activation="Synthetic next step"), app["version"])
                            prepared_render(fixture.store, "sample-one")
                            context = browser.new_context(viewport=dict(width=width, height=900))
                            context.add_cookies([dict(name=c.name, value=c.value, url=fixture.origin, sameSite="Lax")
                                                 for c in fixture.owner.cookies])
                            page = context.new_page(); page.set_default_timeout(10000); errors = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.goto(fixture.origin)
                            page.locator("#navigation summary").click()
                            page.locator('[data-view="research"]').click()
                            page.get_by_role("button", name="Review video batches", exact=True).click()
                            page.locator("#modal").get_by_role("button", name="Prepare a batch", exact=True).click()
                            page.locator('#creative-batch-form input[name="brief"]').first.check()
                            page.get_by_role("button", name="Review batch", exact=True).click()
                            expect(page.locator("#creative-batch-review")).to_contain_text("frames at 24 fps")
                            expect(page.locator("#creative-batch-review")).to_contain_text("Publication is separate")
                            page.get_by_text("Bound source and cleared stills", exact=True).click()
                            expect(page.locator("#creative-batch-review")).to_contain_text("SHA-256")
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                            with connection(fixture.store.path) as db:
                                self.assertEqual(db.execute("SELECT count(*) FROM creative_batches").fetchone()[0], 0)
                            page.get_by_role("button", name="Queue reviewed batch", exact=True).click()
                            expect(page.locator("#modal")).to_contain_text("publication not run")
                            with page.expect_response(lambda response: response.url.endswith("/production/batches/cancel") and response.request.method == "POST") as cancelled:
                                page.locator("#modal").get_by_role("button", name="Cancel batch", exact=True).click()
                            self.assertEqual(cancelled.value.status, 200, cancelled.value.text())
                            with connection(fixture.store.path) as db:
                                row = db.execute("SELECT state FROM creative_batches").fetchone()
                                self.assertEqual(row["state"], "CANCELLED")
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                            page.locator("#modal").get_by_role("button", name="Refresh", exact=True).focus()
                            page.keyboard.press("Tab")
                            self.assertTrue(page.evaluate("document.activeElement.matches('button,input,select,a')"))
                            self.assertEqual(errors, [])
                        finally:
                            if context:
                                context.close()
                            fixture.tearDown()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
