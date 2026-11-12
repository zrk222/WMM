"""Real browser exercise run by the separately provisioned browser CI profile."""

import os
import json
from pathlib import Path
import tempfile
import threading
import unittest

BROWSER_PROFILE = os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1"
if BROWSER_PROFILE:
    # Missing dependencies must fail the declared profile, rather than skip it.
    from playwright.sync_api import expect, sync_playwright

from mission_control.db import connection
from mission_control.server import Server
from mission_control.store import Store
from tests import test_agent_grants as grants
from tests.test_creative_rendering import prepared_render


@unittest.skipUnless(BROWSER_PROFILE, "Run with WMM_BROWSER_TEST_PROFILE=1 in the declared browser profile")
class CreativeBatchBrowserTests(unittest.TestCase):
    def test_owner_reviews_queues_and_cancels_in_desktop_and_mobile_viewports(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for width in (1440, 390):
                    with self.subTest(width=width):
                        fixture = grants.GrantTests(
                            "test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority"
                        )
                        fixture.setUp()
                        context = None
                        try:
                            app = fixture.store.app("sample-one")
                            fixture.store.save_app(
                                "sample-one",
                                dict(
                                    app["data"],
                                    job="Synthetic job",
                                    audience="Synthetic audience",
                                    activation="Synthetic next step",
                                ),
                                app["version"],
                            )
                            prepared_render(fixture.store, "sample-one")
                            context = browser.new_context(viewport=dict(width=width, height=900))
                            context.add_cookies(
                                [
                                    dict(name=c.name, value=c.value, url=fixture.origin, sameSite="Lax")
                                    for c in fixture.owner.cookies
                                ]
                            )
                            page = context.new_page()
                            page.set_default_timeout(10000)
                            errors = []
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
                            page.evaluate("""() => {
                                const original = window.fetch;
                                window.delayedBatchRefreshes = 0;
                                window.fetch = async (...args) => {
                                    const response = await original(...args);
                                    if (String(args[0]).endsWith('/production/batches/list')) {
                                        window.delayedBatchRefreshes++;
                                        await new Promise(resolve => setTimeout(resolve, 300));
                                    }
                                    return response;
                                };
                            }""")
                            with page.expect_response(
                                lambda response: response.url.endswith("/production/batches/cancel")
                                and response.request.method == "POST"
                            ) as cancelled:
                                page.locator("#modal").get_by_role("button", name="Cancel batch", exact=True).click()
                            self.assertEqual(cancelled.value.status, 200, cancelled.value.text())
                            with connection(fixture.store.path) as db:
                                row = db.execute("SELECT state FROM creative_batches").fetchone()
                                self.assertEqual(row["state"], "CANCELLED")
                            # The cancel response precedes the list refresh and modal replacement.
                            expect(page.locator("#modal .next-step strong")).to_contain_text("CANCELLED")
                            self.assertEqual(page.evaluate("window.delayedBatchRefreshes"), 1)
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                            page.locator("#modal").get_by_role("button", name="Refresh", exact=True).focus()
                            page.keyboard.press("Tab")
                            self.assertTrue(page.evaluate("document.activeElement.matches('button,input,select,a')"))
                            expect(
                                page.locator("#modal").get_by_role("button", name="Close", exact=True)
                            ).to_be_focused()
                            self.assertEqual(errors, [])
                        finally:
                            if context:
                                context.close()
                            fixture.tearDown()
            finally:
                browser.close()


@unittest.skipUnless(BROWSER_PROFILE, "Run with WMM_BROWSER_TEST_PROFILE=1 in the declared browser profile")
class FirstAppBrowserTests(unittest.TestCase):
    def test_blank_workspace_add_app_lands_on_goal_and_preserves_current_packets(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for width in (1440, 390):
                    with self.subTest(width=width), tempfile.TemporaryDirectory() as directory:
                        store = Store(Path(directory) / "blank.sqlite", seed=False)
                        server = Server(("127.0.0.1", 0), store)
                        server.daemon_threads = False
                        thread = threading.Thread(target=server.serve_forever, daemon=True)
                        thread.start()
                        origin = "http://127.0.0.1:" + str(server.server_port)
                        context = browser.new_context(viewport=dict(width=width, height=900), accept_downloads=True)
                        unexpected = []
                        errors = []

                        def only_loopback(route):
                            if route.request.url.startswith(origin + "/"):
                                route.continue_()
                            else:
                                unexpected.append(route.request.url)
                                route.abort()

                        context.route("**/*", only_loopback)
                        try:
                            page = context.new_page()
                            page.set_default_timeout(10000)
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            page.goto(origin)
                            self.assertEqual(store.apps(), [])
                            if width == 390:
                                page.locator('[data-action="add-app"]').click()
                            else:
                                page.locator("#add-app").click()
                            form = page.locator("#app-form")
                            expect(form).to_be_visible()
                            values = dict(
                                name="Synthetic first app",
                                job="Help users rehearse decisions",
                                audience="Synthetic test users",
                                activation="Save a practice decision",
                                release="test-build",
                                locale="en-US",
                            )
                            expect(form.get_by_text("Optional settings", exact=True)).to_be_visible()
                            expect(form.locator('[name="id"]')).to_be_hidden()
                            expect(form.locator('[name="website"]')).to_be_hidden()
                            save = form.get_by_role("button", name="Save and choose a goal", exact=True)
                            capture = os.environ.get("WMM_FIRST_APP_CAPTURE")
                            if capture:
                                target = Path(capture)
                                target.mkdir(parents=True, exist_ok=True)
                                page.locator("#modal").screenshot(path=str(target / f"app-setup-{width}.png"))
                                if width == 1440:
                                    html = page.evaluate(r"""() => {
                                        const body = document.body.cloneNode(true);
                                        body.querySelectorAll('script').forEach(script => script.remove());
                                        const css = Array.from(document.styleSheets,
                                          sheet => Array.from(sheet.cssRules, rule => rule.cssText).join('\n')).join('\n');
                                        return '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
                                          '<meta name="viewport" content="width=device-width, initial-scale=1">' +
                                          '<title>Add your app</title><style>' + css + '</style></head>' +
                                          body.outerHTML + '</html>';
                                    }""")
                                    (target / "app-setup.html").write_text(html, encoding="utf-8")
                            save.press("Enter")
                            expect(form.locator('[name="name"]')).to_be_focused()
                            self.assertEqual(store.apps(), [])
                            for key, value in values.items():
                                form.locator('[name="' + key + '"]').fill(value)
                            self.assertEqual(
                                form.evaluate("f => [...f.elements].filter(e => !e.checkValidity()).map(e => e.name)"),
                                [],
                            )
                            with page.expect_response(
                                lambda r: r.url.endswith("/api/apps") and r.request.method == "POST"
                            ) as saved:
                                save.press("Enter")
                            self.assertEqual(saved.value.status, 201, saved.value.text())
                            expect(page.get_by_role("heading", name="Set your goal", exact=True)).to_be_visible()
                            if capture:
                                page.screenshot(path=str(target / f"goal-home-{width}.png"), full_page=True)
                                (target / f"goal-home-{width}.html").write_text(page.content(), encoding="utf-8")
                            page.get_by_role("button", name="Find a useful marketing angle", exact=True).click()
                            expect(page.get_by_role("region", name="Your selected goal")).to_contain_text(
                                "Find a useful marketing angle"
                            )
                            self.assertEqual(
                                page.evaluate("localStorage.getItem('wmm-goal-choice:synthetic-first-app')"), "research"
                            )
                            page.get_by_role("button", name="Open your first packet", exact=True).press("Enter")
                            expect(page.locator("#modal")).to_contain_text(
                                "Find a useful marketing angle — evidence packet"
                            )
                            with page.expect_download() as received:
                                page.get_by_role("button", name="Download goal packet", exact=True).press("Enter")
                            payload = json.loads(Path(received.value.path()).read_text(encoding="utf-8"))
                            self.assertEqual(payload["app_id"], "synthetic-first-app")
                            self.assertEqual(payload["classification"], "LOCAL_DRAFT_NO_AUTHORITY")
                            self.assertEqual([row["stage"] for row in payload["outputs"]], [5, 6])
                            page.reload()
                            expect(page.get_by_role("region", name="Your selected goal")).to_contain_text(
                                "Find a useful marketing angle"
                            )
                            if page.locator("#navigation details").get_attribute("open") is None:
                                page.locator("#navigation summary").click()
                            page.locator('#navigation [data-view="workflow"]').click()
                            expect(page.get_by_role("heading", name="Your guided workflow", exact=True)).to_be_visible()
                            with page.expect_popup() as opened:
                                page.get_by_role("button", name="Report / Save PDF", exact=True).click()
                            report = opened.value
                            expect(report.locator("body")).to_contain_text("Synthetic first app")
                            expect(report.locator("body")).to_contain_text("No file has been saved")
                            report.close()
                            page.get_by_role("button", name="Inspect current packets", exact=True).click()
                            expect(page.locator("#modal")).to_contain_text("Your prepared workflow")
                            expect(page.locator("#modal")).to_contain_text("not completed campaigns")
                            with page.expect_download() as received:
                                page.get_by_role("button", name="Download all packets", exact=True).click()
                            download = received.value
                            self.assertEqual(download.suggested_filename, "synthetic-first-app-current-work.json")
                            payload = json.loads(Path(download.path()).read_text(encoding="utf-8"))
                            self.assertEqual(payload["app_id"], "synthetic-first-app")
                            self.assertEqual(payload["classification"], "CURRENT_LOCAL_DRAFTS")
                            self.assertEqual(len(payload["outputs"]), 12)
                            self.assertEqual(
                                payload["source_hash"], page.evaluate("state.workspace.preparation.source_hash")
                            )
                            page.keyboard.press("Escape")
                            if width == 390:
                                page.locator('[data-action="add-app"]').click()
                            else:
                                page.locator("#add-app").click()
                            for key, value in values.items():
                                form.locator('[name="' + key + '"]').fill(value)
                            form.locator('[name="job"]').fill("Different app with the same name")
                            save.press("Enter")
                            expect(page.locator("#app-select")).to_have_value("synthetic-first-app-2")
                            expect(page.get_by_role("heading", name="Set your goal", exact=True)).to_be_visible()
                            expect(form).to_be_hidden()
                            self.assertEqual(store.app("synthetic-first-app")["data"]["job"], values["job"])
                            self.assertEqual(
                                store.app("synthetic-first-app-2")["data"]["job"], "Different app with the same name"
                            )
                            with connection(store.path) as db:
                                for table in ("jobs", "operator_roles", "agent_grants"):
                                    self.assertEqual(
                                        db.execute("SELECT count(*) FROM " + table).fetchone()[0], 0, table
                                    )
                            self.assertFalse(page.evaluate("document.documentElement.scrollWidth > innerWidth"))
                            self.assertEqual(unexpected, [])
                            self.assertEqual(errors, [])
                        finally:
                            context.close()
                            server.shutdown()
                            server.server_close()
                            thread.join(timeout=10)
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
