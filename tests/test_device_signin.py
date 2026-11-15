"""Device sign-in tests with a synthetic GitHub transport and real loopback sessions."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
import threading
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.device_signin import DeviceSignIns, VERIFY_URL, request
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.operator_identity import Identities
from tests import test_agent_grants as grant
from tests import test_verified_review as identity


CLIENT = "synthetic_device_client"
DEVICE = "synthetic_hidden_device_code"
CODE = {
    "device_code": DEVICE,
    "user_code": "SYN1-TH22",
    "expires_in": 900,
    "interval": 5,
    "verification_uri": VERIFY_URL,
}
TOKEN = {"access_token": identity.OWNER_TOKEN, "token_type": "bearer", "scope": ""}


class DeviceFlowTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.identity = Identities()
        self.device = DeviceSignIns(self.identity, CLIENT, clock=lambda: self.now)
        self.binding = ("sample-one", 1)

    def begin(self):
        with patch("mission_control.device_signin.request", return_value=CODE) as provider:
            result = self.device.begin("session", self.binding)
        provider.assert_called_once_with("begin", {"client_id": CLIENT, "scope": ""})
        self.assertNotIn(DEVICE, json.dumps(result))
        return result["flow_id"]

    def test_fixed_tls_transport_and_bounded_response(self):
        with patch("mission_control.device_signin._github_opener") as opener:
            response = opener.return_value.open.return_value.__enter__.return_value
            response.read.return_value = json.dumps(CODE).encode()
            self.assertEqual(request("begin", {"client_id": CLIENT, "scope": ""}), CODE)
            req = opener.return_value.open.call_args.args[0]
            self.assertEqual(req.full_url, VERIFY_URL + "/code")
            self.assertEqual(req.get_method(), "POST")
            response.read.assert_called_once_with(8193)
            response.read.return_value = b"x" * 8193
            with self.assertRaises(Invalid):
                request("poll", {"client_id": CLIENT})

    def test_timing_confirmation_and_shorter_provider_lifetime(self):
        flow = self.begin()
        with (
            patch(
                "mission_control.device_signin.request",
                side_effect=[
                    {"error": "slow_down"},
                    dict(TOKEN, expires_in=60),
                ],
            ) as provider,
            patch("mission_control.device_signin.github_read", return_value=identity.OWNER),
        ):
            self.assertEqual(self.device.poll("session", self.binding, flow)["retry_after"], 5)
            provider.assert_not_called()
            self.now = 5
            self.assertEqual(self.device.poll("session", self.binding, flow)["retry_after"], 10)
            self.now = 14
            self.assertEqual(self.device.poll("session", self.binding, flow)["retry_after"], 1)
            self.now = 15
            result = self.device.poll("session", self.binding, flow)
            self.assertEqual(result["principal"], identity.OWNER["principal"])
            self.assertNotIn(identity.OWNER_TOKEN, json.dumps(result))
        self.assertEqual(self.identity.public("session")["status"], "SIGNED_OUT")
        with self.assertRaises(PermissionError):
            self.device.confirm("session", self.binding, flow, identity.CHECKER["principal"])
        result = self.device.confirm("session", self.binding, flow, result["principal"])
        self.assertEqual(result["status"], "AUTHENTICATED")
        self.assertNotIn(identity.OWNER_TOKEN, json.dumps(result))
        with self.assertRaises(PermissionError):
            self.device.confirm("session", self.binding, flow, result["principal"])

    def test_different_binding_expiry_and_broader_token_fail_closed(self):
        flow = self.begin()
        self.now = 5
        for session, binding in (
            ("other", self.binding),
            ("session", ("sample-two", 1)),
            ("session", ("sample-one", 2)),
        ):
            with self.assertRaises(PermissionError):
                self.device.poll(session, binding, flow)
        with (
            patch("mission_control.device_signin.request", return_value=dict(TOKEN, scope="repo")),
            patch("mission_control.device_signin.github_read") as read,
        ):
            with self.assertRaisesRegex(Invalid, "expected access"):
                self.device.poll("session", self.binding, flow)
            read.assert_not_called()
        flow = self.begin()
        self.now = 906
        with self.assertRaises(PermissionError):
            self.device.poll("session", self.binding, flow)

    def test_cancel_while_provider_reply_is_in_flight(self):
        flow = self.begin()
        self.now = 5
        entered, release = threading.Event(), threading.Event()

        def respond(*_):
            entered.set()
            if not release.wait(5):
                raise AssertionError("Fixture did not release the provider reply")
            return TOKEN

        with (
            patch("mission_control.device_signin.request", side_effect=respond),
            patch("mission_control.device_signin.github_read", return_value=identity.OWNER),
            ThreadPoolExecutor(max_workers=1) as pool,
        ):
            future = pool.submit(self.device.poll, "session", self.binding, flow)
            self.assertTrue(entered.wait(5))
            self.device.cancel("session")
            release.set()
            with self.assertRaises(PermissionError):
                future.result(5)
        self.assertEqual(self.identity.public("session")["status"], "SIGNED_OUT")

    def test_browser_handoff_opens_only_the_official_fixed_url(self):
        flow = self.begin()
        with patch("webbrowser.open", return_value=True) as browser:
            self.assertTrue(self.device.open_browser("session", self.binding, flow)["browser_opened"])
        browser.assert_called_once_with(VERIFY_URL, new=2)


class DeviceRouteTests(unittest.TestCase):
    def setUp(self):
        self.fixture = grant.GrantTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.now = 0
        server = self.fixture.server
        server.device_signins = DeviceSignIns(server.identities, CLIENT, clock=lambda: self.now)

    def test_loopback_device_requests_are_bound_and_leave_existing_role_checks_intact(self):
        client = OperatorClient(self.fixture.origin)
        client.bootstrap()
        prefix = "/api/identity/device/"
        binding = dict(app_id="sample-one", app_version=1)
        with (
            patch("mission_control.device_signin.request", side_effect=[CODE, TOKEN]),
            patch("mission_control.device_signin.github_read", return_value=identity.OWNER),
        ):
            result = client.request("POST", prefix + "begin", binding)
            check = dict(binding, flow_id=result["flow_id"])
            with self.assertRaises(ClientError) as error:
                client.request("POST", prefix + "poll", dict(check, app_id="sample-two"))
            self.assertEqual(error.exception.status, 403)
            self.now = 5
            verified = client.request("POST", prefix + "poll", check)
            self.assertEqual(client.request("GET", "/api/bootstrap")["identity"]["status"], "SIGNED_OUT")
            client.request("POST", prefix + "confirm", dict(check, principal=verified["principal"]))
        self.assertEqual(client.request("GET", "/api/bootstrap")["identity"]["principal"], identity.OWNER["principal"])
        workspace = client.request("GET", "/api/apps/sample-one")
        self.assertTrue(workspace["device_signin_available"])
        self.assertNotIn(identity.OWNER_TOKEN, json.dumps(workspace))
        self.assertEqual([r["role"] for r in workspace["access"]["members"]], ["OWNER"])
        client.request("POST", "/api/identity/logout", {})
        self.assertEqual(client.request("GET", "/api/bootstrap")["identity"]["status"], "SIGNED_OUT")

    @unittest.skipUnless(os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1", "Requires Chromium")
    def test_browser_journey_shows_code_and_requires_exact_account_confirmation(self):
        from playwright.sync_api import expect, sync_playwright

        with (
            sync_playwright() as runtime,
            patch("mission_control.device_signin.request", side_effect=[CODE, TOKEN, CODE, TOKEN]),
            patch("mission_control.device_signin.github_read", return_value=identity.OWNER),
            patch("webbrowser.open", return_value=True) as opener,
        ):
            browser = runtime.chromium.launch()
            for width in (1440, 390):
                self.now = 0
                with browser.new_context(viewport={"width": width, "height": 880}) as context:
                    page = context.new_page()
                    page.goto(self.fixture.origin)
                    expect(page.locator("#app-select")).to_have_value("sample-one")
                    page.locator('#navigation > [data-view="activity"]').click()
                    authority = page.get_by_role("region", name="Automation authority")
                    expect(authority.get_by_role("button", name="Open automation controls")).to_be_disabled()
                    authority.get_by_role("button", name="Sign in with GitHub", exact=True).press("Enter")
                    page.get_by_role("button", name="Start GitHub sign-in").click()
                    expect(page.get_by_text(CODE["user_code"], exact=True)).to_be_visible()
                    expect(page.locator("#modal input[type=password]")).to_have_count(0)
                    page.get_by_role("button", name="Open GitHub in browser").click()
                    self.now = 5
                    page.get_by_role("button", name="Check GitHub sign-in").click()
                    expect(page.get_by_text("GitHub verified fixture-owner", exact=False)).to_be_visible()
                    page.get_by_role("button", name="Confirm this account").click()
                    expect(page.get_by_role("button", name="Sign out of review session")).to_be_visible()
                    expect(authority.get_by_role("button", name="Open automation controls")).to_be_enabled()
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
                    evidence = os.environ.get("WMM_OWNER_BROWSER_EVIDENCE")
                    if evidence:
                        from pathlib import Path

                        destination = Path(evidence)
                        destination.mkdir(parents=True, exist_ok=True)
                        (destination / f"owner-setup-{width}.html").write_text(page.content(), encoding="utf-8")
            self.assertEqual(opener.call_count, 2)
