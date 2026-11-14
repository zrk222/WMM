"""Real owner controls, synthetic failed requests, no external effect or credential."""

import json
import os
import re
import unittest
from pathlib import Path
from typing import cast

from mission_control.server import Handler
from tests import test_agent_grants as fixtures


@unittest.skipUnless(os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1", "Enable browser profile")
class OperationFeedbackBrowserTests(unittest.TestCase):
    def test_packaged_startup_timeout_retains_research_boundary_without_secrets(self):
        import tempfile
        from unittest.mock import patch

        from playwright.sync_api import TimeoutError as BrowserTimeout

        from tests.test_packaged_first_packet_contract import harness

        host = fixtures.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        handler = cast(type[Handler], host.server.RequestHandlerClass)
        original = handler.do_GET

        def unavailable(request):
            if request.path == "/api/research":
                return request.send(503, dict(error="Synthetic research source unavailable"))
            return original(request)

        with tempfile.TemporaryDirectory() as folder, patch.object(handler, "do_GET", unavailable):
            with self.assertRaises(BrowserTimeout) as caught:
                harness.verify_packet_browser(host.origin, folder)
            raw = (Path(folder) / "failure-1440.json").read_text()
            report = json.loads(raw)
        self.assertEqual(report["exception_type"], "TimeoutError")
        self.assertTrue(report["readiness"]["boot_loaded"])
        self.assertFalse(report["readiness"]["research_loaded"])
        self.assertFalse(report["readiness"]["workspace_loaded"])
        self.assertTrue(report["readiness"]["retry_visible"])
        self.assertIn(dict(path="/api/research", method="GET", status=503), report["api_boundaries"])
        self.assertNotIn("csrf", raw)
        self.assertIn("Packaged startup diagnostics:", caught.exception.__notes__[0])
        self.assertEqual(host.owner.request("GET", "/api/apps/sample-one/jobs"), [])

    def test_signed_out_campaign_history_offers_sign_in_without_replaying(self):
        from playwright.sync_api import expect, sync_playwright

        host = fixtures.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        history = host.origin + "/api/apps/sample-one/campaigns/history"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel=os.environ.get("WMM_BROWSER_CHANNEL") or None)
            for width in (1440, 390):
                with (
                    self.subTest(width=width),
                    browser.new_context(viewport={"width": width, "height": 900}) as context,
                ):
                    context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                    context.route(
                        "**/*",
                        lambda route: route.continue_()
                        if route.request.url.startswith(host.origin + "/")
                        else route.abort(),
                    )
                    page = context.new_page()
                    requests = []
                    page.on(
                        "request",
                        lambda request, requests=requests: requests.append(request.method)
                        if request.url == history
                        else None,
                    )
                    page.goto(host.origin)
                    expect(page.get_by_role("button", name="Find a useful marketing angle", exact=True)).to_be_visible()
                    with page.expect_response(history) as refused:
                        page.evaluate(
                            """async () => {
                                const { api, showActionError } = await import('/app.mjs');
                                try { await api('/api/apps/sample-one/campaigns/history', {}); }
                                catch (error) { showActionError(error); }
                            }"""
                        )
                    self.assertEqual(refused.value.status, 403)
                    panel = page.locator("#toast")
                    expect(panel).to_be_focused()
                    expect(panel).to_contain_text("Your saved work will still be here")
                    expect(panel.get_by_text("HTTP 403", exact=False)).not_to_be_visible()
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                    artifacts = os.environ.get("WMM_FEEDBACK_ARTIFACTS")
                    if artifacts and width == 1440:
                        target = Path(artifacts)
                        target.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(target / "sign-in-1440.png"))
                        markup = re.sub(r"<script\b[^>]*>.*?</script>", "", page.content(), flags=re.S)
                        styles = Path("mission_control/static/style.css").read_text(encoding="utf-8")
                        (target / "sign-in.html").write_text(
                            markup.replace("</head>", "<style>" + styles + "</style></head>"), encoding="utf-8"
                        )
                    button = panel.get_by_role("button", name="Sign in with GitHub", exact=True)
                    button.focus()
                    page.keyboard.press("Enter")
                    expect(page.get_by_role("dialog", name="Sign in for verified review")).to_be_visible()
                    self.assertEqual(requests, ["POST"])

    def test_failed_packet_save_keeps_safe_guidance_and_never_retries(self):
        from playwright.sync_api import TimeoutError as BrowserTimeout
        from playwright.sync_api import expect, sync_playwright

        host = fixtures.GrantTests()
        host.setUp()
        self.addCleanup(host.tearDown)
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        browser = playwright.chromium.launch(channel=os.environ.get("WMM_BROWSER_CHANNEL") or None)
        self.addCleanup(browser.close)
        for width in (1440, 390):
            for case in ("admission", "unknown", "interrupted", "unreadable"):
                with self.subTest(width=width, case=case):
                    context = browser.new_context(viewport={"width": width, "height": 900})
                    self.addCleanup(context.close)
                    context.add_init_script("localStorage.setItem('growth-app','sample-one')")
                    context.route(
                        "**/*",
                        lambda route: route.continue_()
                        if route.request.url.startswith(host.origin + "/")
                        else route.abort(),
                    )
                    calls = []

                    def reject(route, _request, *, calls=calls, case=case):
                        calls.append(route.request.method)
                        if case == "interrupted":
                            route.abort("failed")
                        elif case == "unreadable":
                            route.fulfill(status=403, content_type="text/html", body="<h1>Request rejected</h1>")
                        else:
                            body: dict[str, str | bool] = dict(error="Protected batch admission is required")
                            if case == "unknown":
                                body.update(outcome="UNKNOWN", reconciliation_required=True)
                            route.fulfill(
                                status=409 if case == "unknown" else 403,
                                content_type="application/json",
                                body=json.dumps(body),
                            )

                    context.route(host.origin + "/api/apps/sample-one/jobs", reject)
                    page = context.new_page()
                    page.set_default_timeout(8000)
                    errors = []
                    failed = []
                    page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                    page.on(
                        "requestfailed",
                        lambda request, failed=failed: failed.append(dict(url=request.url, failure=request.failure)),
                    )
                    page.goto(host.origin)
                    try:
                        page.wait_for_function(
                            "(context) => {const state=context.state;return (() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one')(context.original);}",
                            arg={
                                "state": page.evaluate_handle("async () => (await import('/app.mjs')).state"),
                                "original": None,
                            },
                        )
                    except BrowserTimeout:
                        self.fail(
                            json.dumps(dict(page_errors=errors, displayed=page.locator("#main").inner_text()[:1600]))
                        )
                    goal = page.get_by_role("button", name="Find a useful marketing angle", exact=True)
                    try:
                        goal.wait_for(state="visible", timeout=3000)
                    except BrowserTimeout:
                        self.fail(
                            json.dumps(
                                dict(
                                    page_errors=errors,
                                    failed_requests=failed,
                                    displayed=page.locator("body").inner_text()[:2200],
                                )
                            )
                        )
                    goal.click()
                    page.get_by_role("button", name="Open your first packet", exact=True).click()
                    page.get_by_role("button", name="Save packet in this workspace", exact=True).click()
                    panel = page.locator("#form-error")
                    expect(panel).to_be_visible()
                    expected = {
                        "admission": "Your agent needs permission for this task.",
                        "unreadable": "WMM rejected this request.",
                    }.get(case, "WMM could not confirm the result.")
                    expect(panel).to_contain_text(expected)
                    expect(panel).to_be_focused()
                    expect(panel.get_by_text("Protected batch admission is required", exact=True)).not_to_be_visible()
                    panel.get_by_text("Technical details", exact=True).focus()
                    page.keyboard.press("Enter")
                    expect(panel).to_contain_text(
                        {"admission": "AGENT_APPROVAL_NEEDED", "unreadable": "REQUEST_REJECTED"}.get(
                            case, "RESULT_NOT_CONFIRMED"
                        )
                    )
                    self.assertEqual(calls, ["POST"])
                    self.assertEqual(errors, [])
                    self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), width)
                    artifacts = os.environ.get("WMM_FEEDBACK_ARTIFACTS")
                    if artifacts:
                        target = Path(artifacts)
                        target.mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(target / f"{case}-{width}.png"))
                        if case == "admission" and width == 1440:
                            markup = re.sub(r"<script\b[^>]*>.*?</script>", "", page.content(), flags=re.S)
                            styles = Path("mission_control/static/style.css").read_text()
                            (target.parent / "render.html").write_text(
                                markup.replace("</head>", "<style>" + styles + "</style></head>"), encoding="utf-8"
                            )
                    context.close()
        self.assertEqual(host.store.app("sample-one")["version"], 1)
        self.assertEqual(host.owner.request("GET", "/api/apps/sample-one/jobs"), [])
