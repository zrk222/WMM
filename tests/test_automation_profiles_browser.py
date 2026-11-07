"""Exercise goal presets and exact expiry consent through the owner UI."""
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from mission_control.apple_metrics_schedule import AppleMetricsSchedules
from mission_control.common import canonical
from mission_control.db import connection
from mission_control.worker import run_once
from tests import test_agent_grants as fixture
from tests import test_apple_metrics_schedule as apple
from tests.test_automation_requirements import PROFILE as CONNECTION_ID


PROFILE = os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1"
ARTIFACTS = os.environ.get("WMM_GOAL_OWNER_ARTIFACTS")
if PROFILE:
    from playwright.sync_api import expect, sync_playwright


@unittest.skipUnless(PROFILE, "Run WMM_BROWSER_TEST_PROFILE=1 with Chromium installed")
class AutomationProfilesBrowserTests(unittest.TestCase):
    def test_profile_and_longer_expiry_render_exact_review_without_activation(self):
        host = fixture.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        stamp = datetime.now(timezone.utc).isoformat()
        agent = dict(
            provider="codex", model="", label="Synthetic agent",
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
                with self.subTest(width=width):
                    with browser.new_context(viewport={"width": width, "height": 900}, timezone_id="UTC") as context:
                        context.add_cookies([
                            dict(name=c.name, value=c.value, domain="127.0.0.1", path=c.path or "/")
                            for c in host.owner.cookies
                        ])
                        context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                        context.route("**/*", lambda route: (
                            route.continue_() if route.request.url.startswith(host.origin + "/") else route.abort()
                        ))
                        page = context.new_page()
                        page.goto(host.origin)
                        page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one'")
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

    def test_watch_work_opens_the_saved_apple_read(self):
        host = fixture.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        app = host.store.app(apple.APP)
        host.store.save_app(apple.APP, dict(app["data"], store_app_id=apple.STORE_APP), app["version"])
        host.server.service.evidence(apple.APP, dict(
            kind="connection", title="Apple analytics", source="Synthetic fixture",
            data=dict(provider="app_store", store_app_id=apple.STORE_APP, env_ref=apple.REF, account_id="0"),
        ))
        schedules = AppleMetricsSchedules(host.store)
        schedules.save(apple.APP, dict(enabled=True, version=None, interval_hours=24, report_id=apple.REPORT))
        self.assertEqual(schedules.tick(), 1)
        read = apple.AppleMetricsScheduleTests().waiting_read
        with patch.dict(os.environ, {apple.REF: "synthetic-private-key"}), patch(
            "mission_control.provider_reports.read_analytics", side_effect=read,
        ):
            self.assertTrue(run_once(host.store))
        before = schedules.get(apple.APP)
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            for width in (390, 1280):
                with self.subTest(width=width), browser.new_context(viewport={"width": width, "height": 900}) as context:
                    context.add_cookies([
                        dict(name=c.name, value=c.value, domain="127.0.0.1", path=c.path or "/")
                        for c in host.owner.cookies
                    ])
                    context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                    page = context.new_page()
                    page.goto(host.origin)
                    page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one'")
                    requests = []
                    page.on("request", lambda req: requests.append((req.method, req.url)))
                    nav = page.get_by_role("button", name="Watch the work", exact=True)
                    nav.press("Enter")
                    card = page.locator('[data-exception-state="WAITING_FOR_REPORTS"]')
                    expect(card).to_contain_text("App Store Connect")
                    expect(card).to_contain_text("This does not mean zero activity.")
                    expect(card).to_contain_text("next due")
                    self.save_render(page, f"waiting-{width}", '[aria-label="Workflow exceptions"]')
                    card.get_by_role("button", name="Review Apple analytics", exact=True).press("Enter")
                    expect(page.get_by_role("dialog")).to_contain_text("Inspect latest refresh")
                    self.assertEqual([url for method, url in requests if method == "POST"],
                                     [f"{host.origin}/api/apps/{apple.APP}/apple-analytics/view"])
                    self.assertTrue(all(url.startswith(host.origin + "/") for _, url in requests))
                    page.keyboard.press("Escape")
                    page.locator("#app-select").select_option("sample-two")
                    page.wait_for_function("() => state.workspace?.app?.id === 'sample-two'")
                    nav.press("Enter")
                    expect(card).to_have_count(0)
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            browser.close()
        self.assertEqual(schedules.get(apple.APP), before)

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
