"""Synthetic real-browser acceptance of app-scoped OpenSEO import and reports."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import patch

from tests import test_market_research_browser as browser_fixture
from tests.test_measurement_connectors import FakeVault
from tests.test_openseo_read import provider_reply
from tests.test_web_search_evidence import observation, packet

if browser_fixture.PROFILE or TYPE_CHECKING:
    from playwright._impl._api_structures import SetCookieParam
    from playwright.sync_api import expect

ARTIFACTS = Path(__file__).resolve().parents[1] / ".factory/openseo-evidence/browser"


class OpenSEOBrowserTests(browser_fixture.MarketResearchBrowserTests):
    def test_builtin_connection_and_selected_reading_reaches_growth_report(self):
        FakeVault.values, FakeVault.fail_delete = {}, 0
        app = self.f.store.app("sample-one")
        self.f.store.save_app("sample-one", dict(app["data"], website="https://sample.example"), app["version"])
        context = self.browser.new_context(viewport={"width": 1440, "height": 1000})
        self.addCleanup(context.close)
        context.add_cookies(
            [
                cast(
                    "SetCookieParam",
                    dict(
                        name=c.name,
                        value=c.value,
                        domain="127.0.0.1",
                        path=c.path or "/",
                        httpOnly=True,
                        sameSite="Lax",
                    ),
                )
                for c in self.f.owner.cookies
            ]
        )
        context.add_init_script("localStorage.setItem('growth-app','sample-one')")
        page = context.new_page()
        page.goto(self.f.origin)
        page.wait_for_function("async () => (await import('/app.mjs')).state.workspace?.app?.id === 'sample-one'")
        nav = page.locator('[data-view="connections"]')
        if not nav.is_visible():
            page.locator("details").filter(has=nav).locator("summary").first.click()
        nav.click()
        page.get_by_role("button", name="Connect OpenSEO", exact=True).click()
        page.get_by_label("Project ID", exact=True).fill("dedicated-project")
        page.get_by_label("Read API key / export token").fill("oseo_" + "X" * 24)
        page.locator('[name="dedicated_project"]').check()
        page.locator('[name="confirm_read"]').check()
        self.assertFalse(page.locator('[name="automatic"]').is_checked())
        with (
            patch("mission_control.insights.Vault", FakeVault),
            patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply),
        ):
            with page.expect_response(lambda r: r.url.endswith("/insights/setup")) as response:
                page.locator('#insights-setup-form [type="submit"]').click()
            self.assertEqual(response.value.status, 201, response.value.json())
            expect(page.get_by_role("button", name="Use reading for next marketing test")).to_be_visible()
            with page.expect_response(lambda r: r.url.endswith("/save-web-evidence")) as response:
                page.get_by_role("button", name="Use reading for next marketing test").click()
            self.assertEqual(response.value.status, 201, response.value.json())
        self.assertEqual(len(FakeVault.values), 1)
        history = self.f.owner.request("GET", "/api/apps/sample-one/subscription-growth/history")
        assert history is not None
        saved = history["history"][0]
        self.assertTrue(saved["readout"]["analysis"]["native_connection_read"])
        self.assertEqual(saved["readout"]["analysis"]["recommendation"]["observed_rate"]["value"], 0.04)
        page.wait_for_load_state("networkidle")

    def run_journey(self, width):
        app = self.f.store.app("sample-one")
        self.f.store.save_app("sample-one", dict(app["data"], website="https://sample.example"), app["version"])
        context = self.browser.new_context(viewport={"width": width, "height": 1000}, accept_downloads=True)
        self.addCleanup(context.close)
        context.add_cookies(
            [
                cast(
                    "SetCookieParam",
                    dict(
                        name=c.name,
                        value=c.value,
                        domain="127.0.0.1",
                        path=c.path or "/",
                        httpOnly=True,
                        sameSite="Lax",
                    ),
                )
                for c in self.f.owner.cookies
            ]
        )
        context.add_init_script("localStorage.setItem('growth-app','sample-one')")
        external = []

        def route(request):
            if request.request.url.startswith(self.f.origin + "/"):
                request.continue_()
            else:
                external.append(request.request.url)
                request.abort()

        context.route("**/*", route)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(self.f.origin)
        page.wait_for_function("async () => (await import('/app.mjs')).state.workspace?.app?.id === 'sample-one'")
        nav = page.locator('[data-view="results"]')
        if not nav.is_visible():
            page.locator("details").filter(has=nav).locator("summary").first.click()
        nav.click()
        page.get_by_role("button", name="Import OpenSEO evidence").click()
        source = observation(clicks=2, impressions=100, ctr=0.02, position=8.5)
        source["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        data = dict(packet(source)["data"], release="build-1")
        field = page.get_by_label("OpenSEO evidence file")
        field.set_input_files(
            {"name": "research.json", "mimeType": "application/json", "buffer": json.dumps(data).encode()}
        )
        submit = page.locator('#growth-review-form button[type="submit"]')
        submit.click()
        expect(page.locator("#market-research-preview")).to_contain_text("Review web search evidence")
        with page.expect_response(
            lambda response: "/subscription-growth/entries" in response.url and response.request.method == "POST"
        ) as response:
            submit.click()
        self.assertEqual(response.value.status, 201)
        page.wait_for_function("() => !document.querySelector('#modal').open")
        page.locator('[data-action="growth-detail"]').filter(has_text="web seo evidence").click()
        expect(page.locator("#modal")).to_contain_text("2.00% (2 / 100)")
        expect(page.locator("#modal")).to_contain_text("provider verification has not run")
        with page.expect_download() as download:
            page.locator('#modal [data-action="growth-json"]').click()
        report = json.loads(Path(download.value.path()).read_text())
        self.assertEqual(report["title"], "OpenSEO web acquisition report")
        self.assertEqual(report["filters"]["website"], "https://sample.example")
        self.assertEqual(report["metrics"], [])
        page.locator('#modal [data-action="growth-report"]').click()
        preview = page.locator(".wmm-report-dialog[open]")
        expect(preview.get_by_role("heading", name="OpenSEO web acquisition report")).to_be_focused()
        expect(preview).to_contain_text("2.00%")
        self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS / f"{width}-report.png"))
        page.emulate_media(media="print")
        pdf = page.pdf(prefer_css_page_size=True)
        self.assertTrue(pdf.startswith(b"%PDF"))
        if width == 1440:
            (ARTIFACTS / "report.pdf").write_bytes(pdf)
            css = (Path(__file__).resolve().parents[1] / "mission_control/static/page-reporting.css").read_text()
            html = preview.evaluate("(node) => node.innerHTML")
            (ARTIFACTS / "report.html").write_text(
                '<!doctype html><html lang="en"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                "<title>WMM OpenSEO report</title><style>"
                + css
                + '</style></head><body class="wmm-print-report">'
                + html
                + "</body></html>",
                encoding="utf-8",
            )
        self.assertEqual(errors, [])
        self.assertEqual(external, [])
        page.wait_for_load_state("networkidle")
