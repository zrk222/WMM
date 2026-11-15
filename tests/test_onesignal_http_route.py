"""Real loopback owner routes with synthetic identity and native-vault fixture."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
from mission_control.common import now
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import Server, owner_domain_post
from mission_control.store import Store
from tests.test_measurement_connectors import FakeVault
from tests.test_onesignal_transport import APP, ORG, KEY

BASE = "/api/apps/sample-one/onesignal/"


class OneSignalRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.sqlite")
        FakeVault.values = {}
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                ("sample-one", "owner", "owner", "OWNER", "ACTIVE", 1, now(), "fixture"),
            )
        for target, kwargs in [
            (
                "mission_control.operator_identity.github_read",
                {"return_value": {"principal": "owner", "login": "owner", "provider": "GITHUB", "verified_at": now()}},
            ),
            ("mission_control.onesignal_setup.Vault", {"new": FakeVault}),
        ]:
            active = patch(target, **kwargs)
            active.start()
            self.addCleanup(active.stop)
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.client = OperatorClient("http://127.0.0.1:" + str(self.server.server_port))
        self.client.bootstrap()
        self.client.request("POST", "/api/identity/login", {"token": "synthetic_owner_identity_token"})

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)

    def test_schema_and_owner_http_key_flow_excludes_secrets_from_snapshot(self):
        self.assertEqual(
            owner_domain_post(["api", "apps", "sample-one", "onesignal", "status"]).__module__,
            "mission_control.onesignal_setup_http",
        )
        self.assertEqual(self.client.request("POST", BASE + "status", {})["state"], "KEY_NOT_CONFIGURED")
        saved = self.client.request("POST", BASE + "save-key", {"kind": "app", "key": KEY, "version": 0})
        self.assertEqual(saved["state"], "KEY_SAVED_UNBOUND")
        self.assertNotIn(KEY, json.dumps(saved))
        self.assertNotIn(KEY, json.dumps(self.store.export("sample-one")))
        self.assertEqual(self.client.request("POST", BASE + "history", {})["effects"], [])

    def test_owner_role_origin_csrf_and_exact_route_are_enforced(self):
        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError) as denied:
            anonymous.request("POST", BASE + "status", {})
        self.assertEqual(denied.exception.status, 403)
        for headers in ({"Origin": "http://foreign.invalid"}, {"X-CSRF-Token": "wrong"}):
            request = Request(
                self.client.origin + BASE + "status",
                data=b"{}",
                method="POST",
                headers={
                    "Origin": self.client.origin,
                    "Content-Type": "application/json",
                    "X-CSRF-Token": self.client.csrf,
                    **headers,
                },
            )
            with self.assertRaises(HTTPError) as denied:
                self.client.opener.open(request, timeout=10)
            self.assertEqual(denied.exception.code, 403)
            denied.exception.close()
        for path, body in [(BASE + "status?extra=1", {}), (BASE + "status", {"actor": "owner"}), (BASE + "send", {})]:
            with self.assertRaises(ClientError):
                self.client.request("POST", path, body)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id='sample-one'")
        with self.assertRaises(ClientError) as denied:
            self.client.request("POST", BASE + "status", {})
        self.assertEqual(denied.exception.status, 403)

    def test_exact_app_key_discover_and_bind_through_http_without_provider_network(self):
        from mission_control.onesignal_setup import OneSignalSetup

        calls = []

        def provider(action, key, app_id=None, fields=None, alive=lambda: None):
            alive()
            calls.append((action, app_id))
            return {"id": APP, "name": "Synthetic", "organization_id": ORG, "apns_p8": "private-p8"}

        def setup(store, vault_factory=None):
            return OneSignalSetup(store, FakeVault, provider)

        with patch("mission_control.onesignal_setup_http.OneSignalSetup", side_effect=setup):
            self.client.request("POST", BASE + "save-key", {"kind": "app", "key": KEY, "version": 0})
            result = self.client.request("POST", BASE + "read", {"selected_id": APP})
            self.assertEqual(result[0]["id"], APP)
            self.assertNotIn("private-p8", json.dumps(result))
            bound = self.client.request(
                "POST",
                BASE + "bind",
                {"provider_app_id": APP, "expected_name": "Synthetic", "expected_org": ORG, "version": 1},
            )
        self.assertEqual(bound["state"], "APP_BOUND")
        self.assertEqual(calls, [("view", APP), ("view", APP)])
