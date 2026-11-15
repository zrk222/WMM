"""First-run draft and the existing observable-source approvals on real loopback HTTP."""

import json
import os
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast
from unittest.mock import patch

from mission_control.db import connection
from mission_control.setup_parse import extract
from mission_control.store import Store
from tests import test_agent_grants
from tests.test_aeo_inspection import ROOT as WEBSITE
from tests.test_aeo_inspection import Reader

BROWSER_PROFILE = os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1"
if TYPE_CHECKING or BROWSER_PROFILE:
    from playwright.sync_api import Route, expect, sync_playwright


class SourceIdentityTests(unittest.TestCase):
    def test_direct_listing_identity_is_a_proposal_not_ownership(self) -> None:
        reference = "https://apps.apple.com/app/id123456123"
        approved = extract("<title>Synthetic App</title>", reference)
        fields = approved["fields"]
        actual = fields["store_app_id"]
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]["value"], "123456123")
        self.assertEqual(actual[0]["basis"], "OBSERVED_OFFICIAL_LISTING_URL")
        self.assertEqual(actual[0]["reference"], reference)
        self.assertEqual(approved["ownership"], "NOT_VERIFIED")
        unrelated = extract("<title>Synthetic App</title>", "https://example.com/app/id123456123")
        self.assertEqual(unrelated["fields"]["store_app_id"], [])


class _Fixture(Protocol):
    origin: str
    store: Store

    def setUp(self) -> None: ...
    def doCleanups(self) -> None: ...
    def tearDown(self) -> None: ...


@unittest.skipUnless(BROWSER_PROFILE, "Set WMM_BROWSER_TEST_PROFILE=1 to run Chromium acceptance")
class SourceFirstBrowserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = cast(_Fixture, test_agent_grants.GrantTests())
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)

    def exercise(self, width: int) -> None:
        target = self.fixture
        reader = Reader()
        escaped: list[str] = []

        def protect(route: Route) -> None:
            if route.request.url.startswith(target.origin + "/"):
                route.continue_()
            else:
                escaped.append("blocked external request")
                route.abort()

        with (
            sync_playwright() as playwright,
            patch("mission_control.setup_discovery.PublicReader", return_value=reader) as source,
        ):
            browser = playwright.chromium.launch(channel=os.environ.get("WMM_BROWSER_CHANNEL") or None)
            page = browser.new_page(viewport={"width": width, "height": 844})
            page.route("**/*", protect)
            try:
                page.goto(target.origin)
                trigger = page.locator("#add-app" if width >= 900 else '[data-action="add-app"]')
                trigger.press("Enter")
                modal = page.get_by_role("dialog", name="Add your app")
                expect(modal.locator("#app-form")).to_be_visible()
                modal.get_by_text("Start with an App Store link or public website", exact=True).press("Enter")
                form = modal.locator("#app-link-setup-form")
                form.get_by_label("App name", exact=True).fill("Synthetic link draft")
                url = form.get_by_label("Public HTTPS link", exact=True)
                url.fill("http://example.com/page")
                save = form.get_by_role("button", name="Save draft and review source", exact=True)
                save.press("Enter")
                expect(form.locator("#app-link-error")).to_contain_text("starts with https")
                expect(url).to_have_value("http://example.com/page")
                url.fill(WEBSITE + "/page")
                with page.expect_response(
                    lambda r: r.url == target.origin + "/api/apps" and r.request.method == "POST"
                ) as draft:
                    save.press("Enter")
                self.assertEqual(draft.value.status, 201)
                review = page.get_by_role("dialog", name="Discover app details")
                expect(review).to_contain_text(WEBSITE + "/page")
                self.assertEqual(source.call_count, 0)
                saved = target.store.app("synthetic-link-draft")
                self.assertEqual(saved["data"]["website"], WEBSITE + "/page")
                self.assertEqual(saved["data"]["job"], "")
                self.assertEqual(saved["data"]["authorized_spend_minor"], 0)
                self.assertTrue(review.evaluate("(e) => e.scrollWidth <= e.clientWidth"))
                review.get_by_role("button", name="Read saved website", exact=True).press("Enter")
                expect(page.locator("#setup-review")).to_be_visible()
                self.assertGreater(len(reader.calls), 0)
                self.assertEqual(target.store.app("synthetic-link-draft")["version"], saved["version"])
                with connection(target.store.path) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)
                linked_review = page.content()
                page.keyboard.press("Escape")
                expect(review).to_be_hidden()
                trigger.press("Enter")
                manual = modal.locator("#app-form")
                for key, value in {
                    "name": "Synthetic manual app",
                    "audience": "Practice users",
                    "job": "Rehearse decisions",
                    "activation": "Save a practice decision",
                    "release": "test-build",
                    "locale": "en-US",
                }.items():
                    manual.locator(f'[name="{key}"]').fill(value)
                with page.expect_response(
                    lambda r: r.url == target.origin + "/api/apps" and r.request.method == "POST"
                ) as manual_save:
                    manual.get_by_role("button", name="Save and choose a goal", exact=True).press("Enter")
                self.assertEqual(manual_save.value.status, 201)
                expect(modal).to_be_hidden()
                expect(page.get_by_role("heading", name="Set your goal", exact=True)).to_be_visible()
                self.assertEqual(target.store.app("synthetic-manual-app")["data"]["website"], "")
                self.assertEqual(source.call_count, 1)
                page.evaluate("""() => {
                    const fetch = window.fetch;
                    window.fetch = async (target, init) => {
                        const response = await fetch(target, init);
                        if (init?.method === 'POST' && new URL(target, location.href).pathname === '/api/apps') {
                            await new Promise(resolve => {
                                window.releaseDraftResponse = resolve;
                                document.body.dataset.draftResponse = 'held';
                            });
                            const json = response.json.bind(response);
                            response.json = async () => {
                                const result = await json();
                                setTimeout(() => { document.body.dataset.draftResponse = 'delivered'; }, 0);
                                return result;
                            };
                        }
                        return response;
                    };
                }""")
                trigger.press("Enter")
                modal.get_by_text("Start with an App Store link or public website", exact=True).press("Enter")
                form.get_by_label("App name", exact=True).fill("Synthetic background draft")
                url.fill(WEBSITE + "/page")
                save.press("Enter")
                expect(page.locator("body")).to_have_attribute("data-draft-response", "held")
                page.keyboard.press("Escape")
                expect(modal).to_be_hidden()
                page.evaluate("window.releaseDraftResponse()")
                expect(page.locator("body")).to_have_attribute("data-draft-response", "delivered")
                # The draft is local and discoverable, but its late response cannot replace the active app.
                self.assertEqual(target.store.app("synthetic-background-draft")["data"]["website"], WEBSITE + "/page")
                expect(review).to_be_hidden()
                self.assertEqual(
                    page.evaluate("async () => (await import('/app.mjs')).state.app"),
                    "synthetic-manual-app",
                )
                self.assertEqual(source.call_count, 1)
                self.assertFalse(escaped)
                self.save_browser_evidence(linked_review, width)
            finally:
                browser.close()

    def save_browser_evidence(self, html: str, width: int) -> None:
        folder = Path(".factory/source-first-app-setup")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"screen-{width}.html").write_text(html, encoding="utf-8")
        report = {
            "width": width,
            "draft_no_network": True,
            "explicit_source_review": True,
            "no_job_or_spend": True,
            "manual_form_saved_without_link": True,
            "dismissed_draft_preserves_active_app": True,
        }
        (folder / f"browser-{width}.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def test_source_first_on_mobile(self) -> None:
        self.exercise(390)

    def test_source_first_on_desktop(self) -> None:
        self.exercise(1440)
