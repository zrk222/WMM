"""Real private HTTP boundary, exact JSON, callback consumption and account scope."""

import http.cookiejar
import json
import socket
import tempfile
import time
import unittest
from contextlib import contextmanager
from typing import cast
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.desktop import DesktopRuntime
from mission_control.server import Server
from mission_control.social_flows import Flows
from mission_control.social_profiles import Identity
from mission_control.social_setup import Setup
from mission_control.social_tokens import parse
from tests import test_http as fixtures
from tests.test_measurement_connectors import FakeVault
from tests.test_social_providers import token
from tests.test_social_setup import body


@contextmanager
def desktop_fixture(directory: str):
    runtime = DesktopRuntime(directory)
    try:
        browser = fixtures.HTTPTests()
        browser.server = runtime.server
        browser.base = runtime.start()
        browser.client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        browser.bootstrap = browser.request("/api/bootstrap")[1]
        yield browser
    finally:
        runtime.close()


class SocialHTTPTests(unittest.TestCase):
    server: Server
    base: str
    setUp = fixtures.HTTPTests.setUp
    tearDown = fixtures.HTTPTests.tearDown

    def request(self, path, body=None, headers=None, raw=None):
        # The shared setup initializes the exact request fixture without inheriting its tests.
        return fixtures.HTTPTests.request(
            cast(fixtures.HTTPTests, self), path, body, {"Content-Type": "application/json", **(headers or {})}, raw
        )

    def test_callback_navigation_preserves_existing_session_and_fresh_bootstrap(self):
        sessions = dict(self.server.sessions)
        routes = (
            "/social/callback/facebook?state=synthetic&code=synthetic",
            "/social/callback/instagram?state=synthetic&error=denied",
            "/social/callback/tiktok?state=synthetic&code=synthetic",
            "/social/callback/linkedin?state=synthetic&code=synthetic",
            "/?state=synthetic&code=synthetic",
            "/index.html?state=drive_synthetic&error=denied",
        )
        with patch("mission_control.social_callbacks.exchange_code") as exchange:
            for route in routes:
                with self.subTest(route=route):
                    with build_opener().open(self.base + route) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIsNone(response.headers.get("Set-Cookie"))
                        self.assertIn(b"<html", response.read().lower())
                    self.assertEqual(self.server.sessions, sessions)
            exchange.assert_not_called()
        self.assertEqual(self.request("/social/callback/facebook", headers={"Host": "wrong.example"})[0], 403)
        self.assertEqual(self.server.sessions, sessions)
        FakeVault.values = {}
        base = "/api/apps/sample-one/social-access/save"
        with patch("mission_control.social_secrets.Vault", FakeVault):
            self.assertEqual(self.request(base, body(), {"X-CSRF-Token": "wrong"})[0], 403)
            self.assertEqual(self.request(base, body(), {"Origin": "https://wrong.example"})[0], 403)
            self.assertEqual(self.request(base, body(), {"Host": "wrong.example"})[0], 403)
            self.assertEqual(self.request(base, body())[0], 200)
        fresh = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with fresh.open(self.base + "/social/callback/facebook?state=synthetic&code=synthetic") as response:
            self.assertIsNone(response.headers.get("Set-Cookie"))
        self.assertEqual(self.server.sessions, sessions)
        with fresh.open(self.base + "/api/bootstrap") as response:
            self.assertIn("SameSite=Strict", response.headers["Set-Cookie"])
            bootstrap = json.load(response)
        self.assertTrue(bootstrap["csrf"])
        self.assertEqual(len(self.server.sessions), len(sessions) + 1)
        request = Request(
            self.base + "/api/identity/logout",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json", "X-CSRF-Token": bootstrap["csrf"], "Origin": self.base},
        )
        with fresh.open(request) as response:
            self.assertEqual(response.status, 200)

    def test_strict_setup_scope_unknown_authority_and_static_callbacks(self):
        FakeVault.values = {}
        base = "/api/apps/sample-one/social-access"
        with patch("mission_control.social_secrets.Vault", FakeVault):
            self.assertEqual(self.request(base + "/save", body(), {"X-CSRF-Token": "bad"})[0], 403)
            for path, data in (
                (base + "/save?bad=1", body()),
                (base + "/save", {**body(), "command": "bad"}),
                (base + "/publish", {}),
            ):
                self.assertEqual(self.request(path, data)[0], 400)
            self.assertEqual(self.request(base + "/save", body(), {"Content-Type": "text/plain"})[0], 400)
            duplicate = json.dumps(body())[:-1] + ',"provider":"linkedin"}'
            self.assertEqual(self.request(base + "/save", raw=duplicate.encode())[0], 400)
            self.assertEqual(self.request(base + "/save", body())[0], 200)
            workspace = self.request("/api/apps/sample-one")[1]
            self.assertNotIn("synthetic-client-secret", json.dumps(workspace))
            self.assertNotIn("secret_ref", json.dumps(workspace["social_access"]))
            self.assertEqual(self.request("/api/apps/sample-two")[1]["social_access"]["setup"]["configurations"], [])
        for route in ("/social-access.mjs", "/social-callback.js", "/social/callback/tiktok"):
            self.assertEqual(self.request(route)[0], 200)
        self.assertEqual(self.request("/social/callback/unknown")[0], 404)

    def test_official_callback_requires_csrf_and_is_consumed_once(self):
        FakeVault.values = {}
        base = "/api/apps/sample-one/social-access"
        with patch("mission_control.social_secrets.Vault", FakeVault):
            self.assertEqual(self.request(base + "/save", {**body("tiktok"), "redirect_uri": ""})[0], 200)
            started = self.request(base + "/start", dict(provider="tiktok", version=1))[1]
            query = parse_qs(urlsplit(started["authorization_url"]).query)
            self.assertEqual(
                query["redirect_uri"][0], f"http://127.0.0.1:{self.server.server_port}/social/callback/tiktok"
            )
            request = dict(provider="tiktok", state=query["state"][0], code="synthetic-code", error="")
            self.assertEqual(self.request("/api/social/callback", request, {"X-CSRF-Token": "wrong"})[0], 403)
            found = Identity(
                "synthetic-user",
                "Synthetic account",
                [dict(id="synthetic-user", name="Synthetic account", kind="PROFILE", tasks=[])],
                ["user.info.basic"],
            )
            with (
                patch(
                    "mission_control.social_callbacks.exchange_code", return_value=parse("tiktok", token(), time.time())
                ),
                patch("mission_control.social_callbacks.verify", return_value=found),
            ):
                code, result, _ = self.request("/api/social/callback", request)
            self.assertEqual(code, 200)
            self.assertEqual(result["status"], "AWAITING_DESTINATION")
            self.assertEqual(self.request("/api/social/callback", request)[0], 400)
            self.assertNotIn("synthetic-access", json.dumps(result))
            self.assertNotIn("state_hash", json.dumps(result))
            flow = started["flow_id"]
            self.assertEqual(self.request("/api/apps/sample-two/social-access/flows/" + flow)[0], 400)
            self.assertEqual(self.request(base + "/flows/" + flow + "?bad=1")[0], 400)
            saved = self.request(
                base + "/confirm", dict(flow_id=flow, destination_id="synthetic-user", connection_id="", version=0)
            )[1]
            self.assertEqual(saved["status"], "CONNECTED_READ_TESTED")
            self.assertEqual(
                self.request("/api/apps/sample-two/social-access/" + saved["id"] + "/disconnect", {"version": 1})[0],
                400,
            )
            self.assertEqual(self.request(base + "/" + saved["id"] + "/disconnect", {"version": 1})[0], 200)

    def test_desktop_fallback_refuses_relay_before_creating_a_flow(self):
        FakeVault.values = {}
        self.server.runtime_mode = "DESKTOP"
        self.assertNotEqual(self.server.server_port, 8765)
        base = "/api/apps/sample-one/social-access"
        with patch("mission_control.social_secrets.Vault", FakeVault):
            self.assertEqual(self.request(base + "/save", body())[0], 200)
            keys_before = set(FakeVault.values)
            with patch("mission_control.social_flows.fresh_state") as mint:
                code, result, _ = self.request(base + "/start", {"provider": "facebook", "version": 1})
                mint.assert_not_called()
            self.assertEqual(code, 400)
            self.assertIn("Free that port, then reopen WMM", result["error"])
            self.assertNotIn("authorization_url", result)
            self.assertEqual(set(FakeVault.values), keys_before)
            with connection(self.server.service.store.path) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM social_flows").fetchone()[0], 0)
            self.assertEqual(self.request(base + "/save", {**body("tiktok"), "redirect_uri": ""})[0], 200)
            code, direct, _ = self.request(base + "/start", {"provider": "tiktok", "version": 1})
            self.assertEqual(code, 200)
            self.assertEqual(
                parse_qs(urlsplit(direct["authorization_url"]).query)["redirect_uri"],
                [f"{self.base}/social/callback/tiktok"],
            )
            self.server.runtime_mode = "SERVER"
            self.assertEqual(self.request(base + "/start", {"provider": "facebook", "version": 1})[0], 200)

    def test_moved_direct_callback_requires_the_current_port_before_minting_state(self):
        FakeVault.values = {}
        store = self.server.service.store
        port = self.server.server_port
        self.assertNotEqual(port, 8765)
        payload = {**body("tiktok"), "redirect_uri": ""}
        with patch("mission_control.social_secrets.Vault", FakeVault):
            for saved_port, current_port in ((8765, port), (port, 8765)):
                app = "sample-one" if saved_port == 8765 else "sample-two"
                Setup(store, saved_port).save(app, payload)
                flow = Flows(store, current_port, require_relay_port=True)
                with patch("mission_control.social_flows.fresh_state") as mint, self.assertRaises(Invalid) as error:
                    flow.start(app, "tiktok", 1)
                mint.assert_not_called()
                self.assertIn(f"http://127.0.0.1:{current_port}/social/callback/tiktok", str(error.exception))
                Setup(store, current_port).save(app, {**payload, "version": 1})
                started = flow.start(app, "tiktok", 2)
                authorization_url = started["authorization_url"]
                assert isinstance(authorization_url, str)
                uri = parse_qs(urlsplit(authorization_url).query)["redirect_uri"]
                self.assertEqual(uri, [f"http://127.0.0.1:{current_port}/social/callback/tiktok"])

    def test_fallback_setup_survives_restart_and_retries_without_resaving(self):
        FakeVault.values = {}
        base = "/api/apps/sample-one/social-access"
        headers = {"Content-Type": "application/json"}
        command = {"provider": "facebook", "version": 1}
        with tempfile.TemporaryDirectory() as folder, patch("mission_control.social_secrets.Vault", FakeVault):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
                blocker.bind(("127.0.0.1", 8765))
                blocker.listen(1)
                with desktop_fixture(folder) as browser:
                    self.assertNotEqual(browser.server.server_port, 8765)
                    self.assertEqual(browser.request(base + "/save", body(), headers)[0], 200)
                    self.assertEqual(browser.request(base + "/start", command, headers)[0], 400)
            with desktop_fixture(folder) as browser:
                self.assertEqual(browser.server.server_port, 8765)
                view = browser.request("/api/apps/sample-two")[1]
                self.assertEqual(view["social_access"]["setup"]["configurations"], [])
                code, started, _ = browser.request(base + "/start", command, headers)
                self.assertEqual(code, 200)
                self.assertEqual(started["status"], "PENDING")
                self.assertEqual(browser.request(base + "/cancel", {"flow_id": started["flow_id"]}, headers)[0], 200)


if __name__ == "__main__":
    unittest.main()
