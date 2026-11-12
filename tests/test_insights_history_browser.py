"""Open saved analytics through the real Results page with synthetic provider reads."""

import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from mission_control.insights import Insights
from mission_control.store import Store
from tests import test_agent_grants as fixture
from tests.test_measurement_connectors import FakeVault, setup_body


PROFILE = os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1"
ARTIFACTS = os.environ.get("WMM_INSIGHTS_HISTORY_ARTIFACTS")
if PROFILE:
    from playwright.sync_api import expect, sync_playwright


@unittest.skipUnless(PROFILE, "Run WMM_BROWSER_TEST_PROFILE=1 with Chromium installed")
class InsightsHistoryBrowserTests(unittest.TestCase):
    def test_retained_observation_selection_and_exact_download(self):
        host = fixture.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        store = host.server.service.store
        with (
            patch("mission_control.insights.Vault", FakeVault),
            patch(
                "mission_control.insights_transport.request",
                side_effect=[
                    {"id": 123},
                    {"results": [["signup_completed", 0]]},
                    {"id": 123},
                    {"results": [["signup_completed", 7]]},
                ],
            ),
        ):
            source_id = Insights(store).setup("sample-one", setup_body())["source_id"]
            Insights(store).setup("sample-one", dict(setup_body(), version=1))
        reopened = Store(store.path, seed=False)
        newest, older = Insights(reopened).list("sample-one")["reports"]
        self.assertEqual(older["data"]["rows"][0]["value"], 0)

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            for width in (390, 1280):
                with self.subTest(width=width):
                    with browser.new_context(
                        viewport={"width": width, "height": 900}, accept_downloads=True
                    ) as context:
                        context.add_cookies(
                            [
                                dict(name=c.name, value=c.value, domain="127.0.0.1", path=c.path or "/")
                                for c in host.owner.cookies
                            ]
                        )
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
                            "() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one'"
                        )
                        nav = page.locator('[data-view="results"]')
                        if not nav.is_visible():
                            page.locator("details").filter(has=nav).locator("summary").first.click()
                        nav.click()
                        page.locator(f'[data-action="insights-inspect"][data-id="{source_id}"]').click()
                        picker = page.get_by_label("Reading", exact=True)
                        expect(picker).to_have_value(newest["id"])
                        expect(page.locator("#insights-observation")).to_contain_text("Current setup version")
                        picker.focus()
                        picker.press("ArrowDown")
                        expect(picker).to_have_value(older["id"])
                        expect(picker).to_be_focused()
                        expect(page.locator("#insights-observation")).to_contain_text("Earlier setup version")
                        row = page.locator("#insights-observation tbody tr")
                        expect(row.get_by_role("cell").nth(0)).to_have_text("0")
                        expect(row.get_by_role("cell").nth(2)).to_have_text("last_7_days")
                        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                        if ARTIFACTS:
                            self.save_render(page, width)
                        with page.expect_download() as captured:
                            page.get_by_role("button", name="Download selected reading (JSON)").click()
                        data = json.loads(Path(captured.value.path()).read_text(encoding="utf-8"))
                        self.assertEqual(data, older)
            browser.close()

    def save_render(self, page, width):
        target = Path(ARTIFACTS)
        target.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target / f"insights-{width}.png"))
        dialog = page.locator("#modal").evaluate("(node) => node.outerHTML")
        heading = page.locator("#main h1").first.evaluate("(node) => node.outerHTML")
        style = (Path(__file__).resolve().parents[1] / "mission_control/static/style.css").read_text(encoding="utf-8")
        (target / f"insights-{width}.html").write_text(
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>WMM saved observations</title><style>{style}</style></head>"
            f"<body><main>{heading}{dialog}</main></body></html>",
            encoding="utf-8",
        )
