"""Actual loopback owner routes with synthetic identity and provider responses."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from mission_control.common import now
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import Server, owner_domain_post
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once

APP = "sample-one"
BASE = "/api/apps/sample-one/apple-analytics/"


class AppleMetricsRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.sqlite")
        app = self.store.app(APP)
        self.app = self.store.save_app(APP, dict(app["data"], store_app_id="123"), app["version"])
        self.record = Service(self.store).evidence(
            APP,
            dict(
                kind="connection",
                title="Synthetic Apple",
                source="Fixture only",
                data={
                    "provider": "app_store",
                    "store_app_id": "123",
                    "env_ref": "GROWTH_SAMPLE_ONE_SYNTHETIC",
                    "account_id": "0",
                },
            ),
        )
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                (APP, "owner", "owner", "OWNER", "ACTIVE", 1, now(), "fixture"),
            )
        identity = patch(
            "mission_control.operator_identity.github_read",
            return_value={"principal": "owner", "login": "owner", "provider": "GITHUB", "verified_at": now()},
        )
        identity.start()
        self.addCleanup(identity.stop)
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

    def inventory_body(self):
        return dict(
            manifest_version=self.app["version"],
            connection_id=self.record["id"],
            connection_version=self.record["version"],
        )

    def reject(self, client, path, body, status):
        with self.assertRaises(ClientError) as denied:
            client.request("POST", path, body)
        self.assertEqual(denied.exception.status, status)

    def test_owner_can_queue_observe_and_pause_without_provider_calls(self):
        self.assertEqual(
            owner_domain_post(["api", "apps", APP, "apple-analytics", "view"]).__module__,
            "mission_control.apple_metrics_http",
        )
        before = self.client.request("POST", BASE + "view", {})
        self.assertIsNone(before["inventory"])
        self.assertEqual(before["reports"], [])
        job = self.client.request("POST", BASE + "inventory", self.inventory_body())
        result = dict(
            provider="app_store",
            operation="analytics_reports",
            app_id=APP,
            store_app_id="123",
            status="WAITING_FOR_REPORTS",
            coverage="COMPLETE",
            observed_at=now(),
            reports=[dict(id="report-1", name="App Downloads Standard", coverage="COMPLETE", instances=[])],
            sensitive="synthetic-private",
        )
        with patch("mission_control.worker.read_report", return_value=result) as provider:
            self.assertTrue(run_once(self.store))
        provider.assert_called_once()
        after = self.client.request("POST", BASE + "view", {})
        self.assertEqual(after["inventory"]["job_id"], job["job_id"])
        self.assertEqual(after["reports"][0]["instance_count"], 0)
        self.assertNotIn("synthetic-private", json.dumps(after))
        self.assertNotIn("GROWTH_SAMPLE_ONE_SYNTHETIC", json.dumps(after))
        schedule = self.client.request(
            "POST",
            BASE + "schedule",
            dict(
                manifest_version=self.app["version"],
                enabled=True,
                interval_hours=24,
                report_id="report-1",
                version=None,
            ),
        )
        self.assertTrue(schedule["enabled"])
        paused = self.client.request(
            "POST",
            BASE + "schedule",
            dict(manifest_version=self.app["version"], enabled=False, version=schedule["version"]),
        )
        self.assertFalse(paused["enabled"])

    def test_anonymous_bearer_csrf_origin_and_query_are_denied(self):
        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        self.reject(anonymous, BASE + "view", {}, 403)
        for client, headers, status in (
            (anonymous, {"Authorization": "Bearer synthetic_agent_token", "X-CSRF-Token": anonymous.csrf}, 403),
            (self.client, {"X-CSRF-Token": "wrong"}, 403),
            (self.client, {"X-CSRF-Token": self.client.csrf, "Origin": "http://foreign.invalid"}, 403),
        ):
            request = Request(
                client.origin + BASE + "view",
                data=b"{}",
                method="POST",
                headers={"Origin": client.origin, "Content-Type": "application/json", **headers},
            )
            with self.assertRaises(HTTPError) as denied:
                client.opener.open(request, timeout=10)
            self.assertEqual(denied.exception.code, status)
            denied.exception.close()
        self.reject(self.client, BASE + "view?extra=1", {}, 400)
        self.reject(self.client, BASE + "view", {"actor": "owner"}, 400)

    def test_app_role_connection_and_manifest_are_fenced(self):
        self.reject(self.client, "/api/apps/sample-two/apple-analytics/view", {}, 403)
        self.reject(self.client, BASE + "inventory", dict(self.inventory_body(), manifest_version=999), 400)
        self.reject(self.client, BASE + "inventory", dict(self.inventory_body(), connection_id="foreign"), 400)
        self.reject(self.client, BASE + "inventory", dict(self.inventory_body(), connection_version=999), 400)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", (APP,))
        self.reject(self.client, BASE + "view", {}, 403)
        self.reject(self.client, BASE + "inventory", self.inventory_body(), 403)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
