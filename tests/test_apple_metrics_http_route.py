"""Actual loopback owner routes with synthetic identity and provider responses."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from mission_control.apple_analytics import CAMPAIGN_DOWNLOADS
from mission_control.common import now
from mission_control.db import connection
from mission_control.growth_review_store import GrowthReviews
from mission_control.insights import Insights
from mission_control.openseo_read import save_reading
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.search_store_review import search_store_review
from mission_control.server import Server, owner_domain_post
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once
from tests.test_measurement_connectors import FakeVault
from tests.test_openseo_read import provider_reply, setup

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

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        value = self.client.request("POST", path, body)
        assert isinstance(value, dict), value
        return value

    def test_owner_can_queue_observe_and_pause_without_provider_calls(self):
        route = owner_domain_post(["api", "apps", APP, "apple-analytics", "view"])
        assert route is not None
        self.assertEqual(route.__module__, "mission_control.apple_metrics_http")
        before = self.post(BASE + "view", {})
        self.assertIsNone(before["inventory"])
        self.assertEqual(before["reports"], [])
        job = self.post(BASE + "inventory", self.inventory_body())
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
        after = self.post(BASE + "view", {})
        self.assertEqual(after["inventory"]["job_id"], job["job_id"])
        self.assertEqual(after["reports"][0]["instance_count"], 0)
        self.assertNotIn("synthetic-private", json.dumps(after))
        self.assertNotIn("GROWTH_SAMPLE_ONE_SYNTHETIC", json.dumps(after))
        schedule = self.post(
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
        paused = self.post(
            BASE + "schedule",
            dict(manifest_version=self.app["version"], enabled=False, version=schedule["version"]),
        )
        self.assertFalse(paused["enabled"])

    def test_search_review_uses_current_verified_web_evidence_and_retains_apple_window(self) -> None:
        app = self.store.app(APP)
        self.app = self.store.save_app(
            APP,
            dict(app["data"], website="https://sample.example", release="build-1", locale="en-US"),
            app["version"],
        )
        body = dict(manifest_version=self.app["version"], start="2026-01-01", end="2026-01-05")
        path = BASE + "search-review"
        anon = OperatorClient(self.client.origin)
        anon.bootstrap()
        self.reject(anon, path, body, 403)
        self.reject(self.client, path, dict(body, raw_metrics=[]), 400)
        self.reject(self.client, path, dict(body, manifest_version=self.app["version"] + 1), 400)
        with patch("mission_control.worker.read_report") as apple:
            empty = self.post(path, body)
        apple.assert_not_called()
        self.assertEqual(empty["rows"], self.post(BASE + "performance", body)["rows"])
        self.assertEqual(len(empty["rows"]), 5)
        review = empty["search_review"]
        self.assertEqual(review["web_facts"], [])
        self.assertEqual([action["id"] for action in review["actions"]], ["apple-baseline", "web-baseline"])
        self.assertIn("0/5 days", review["insight"])

        FakeVault.values, FakeVault.fail_delete = {}, 0
        with patch("mission_control.insights.Vault", FakeVault):
            owner = Insights(self.store)
            with patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply):
                source_id = owner.setup(APP, setup())["source_id"]
            report = owner.list(APP)["reports"][0]
            GrowthReviews(self.store).save(
                APP,
                dict(
                    id="operator-search-review",
                    manifest_version=self.app["version"],
                    kind="WEB_SEO_EVIDENCE",
                    data=report["data"]["web_evidence"],
                ),
            )
            self.assertEqual(self.post(path, body)["search_review"]["web_facts"], [])
            evidence = save_reading(
                self.store,
                APP,
                source_id,
                dict(id="native-search-review", manifest_version=self.app["version"], report_id=report["id"]),
            )
            with patch("mission_control.openseo_transport.call_tool") as web:
                combined = self.post(path, body)
            web.assert_not_called()
            self.assertEqual(combined["rows"], empty["rows"])
            self.assertFalse(combined["external_writes"])
            self.assertNotIn(setup()["api_key"], json.dumps(combined))
            review = combined["search_review"]
            self.assertEqual(review["web_evidence_sha256"], evidence["hash"])
            self.assertIn("Google organic clicks 4", review["web_facts"])
            self.assertIn("Google organic impressions 100", review["web_facts"])
            self.assertIn("Google organic click-through rate 4.0%", review["web_facts"])
            self.assertIn("https://sample.example/guide", review["actions"][2]["task"])
            self.assertEqual(review["actions"][2]["depends_on"], ["web-baseline"])
            mature_rows = [
                dict(
                    day,
                    discovery=dict(status="APPLE_REPORTED", counts=dict(impressions="0")),
                    downloads=dict(status="APPLE_REPORTED", counts=dict(first_time_downloads="0")),
                )
                for day in combined["rows"]
            ]
            with connection(self.store.path) as db:
                db.execute("BEGIN")
                planned = search_store_review(db, dict(combined, rows=mature_rows), True)
            self.assertEqual(planned["actions"][-1]["id"], "measure-tag")
            self.assertEqual(planned["actions"][-1]["depends_on"], ["test-brief", "store-link-check"])
            owner.disconnect(APP, source_id, dict(version=1, confirm_disconnect=True))
            disconnected = self.post(path, body)["search_review"]
            self.assertIsNone(disconnected["web_evidence_sha256"])
            self.assertEqual(disconnected["web_facts"], [])
            self.assertEqual([action["id"] for action in disconnected["actions"]], ["apple-baseline", "web-baseline"])

    def campaign_inventory(self, processing_dates: list[tuple[str, str, str]]) -> str:
        result = dict(
            provider="app_store",
            operation="analytics_reports",
            app_id=APP,
            store_app_id="123",
            status="METRIC_DOWNLOAD_REQUIRED",
            coverage="COMPLETE",
            observed_at=now(),
            reports=[
                dict(
                    id="detailed-1",
                    name=CAMPAIGN_DOWNLOADS,
                    coverage="COMPLETE",
                    instances=[
                        dict(id=id_, processing_date=day, granularity=grain) for id_, day, grain in processing_dates
                    ],
                )
            ],
        )
        job = self.post(BASE + "inventory", self.inventory_body())
        # Commit the exact synthetic inventory without draining other jobs.
        with connection(self.store.path, write=True) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED',result=? WHERE id=?", (json.dumps(result), job["job_id"]))
        snapshot = self.post(BASE + "view", {})
        self.assertEqual(snapshot["inventory"]["job_id"], job["job_id"])
        return job["job_id"]

    def test_campaign_file_window_reuses_saved_jobs_and_retries_only_after_refresh(self) -> None:
        files = [
            ("day-3", "2026-10-03", "DAILY"),
            ("week-2", "2026-10-02", "WEEKLY"),
            ("day-1", "2026-10-01", "DAILY"),
            ("day-2", "2026-10-02", "DAILY"),
        ]
        inventory_id = self.campaign_inventory(files)
        path = BASE + "campaign-collect-window"
        body = dict(
            inventory_id=inventory_id,
            manifest_version=self.app["version"],
            report_id="detailed-1",
            link="https://apps.apple.com/ca/app/example/id123?pt=456&ct=synthetic-campaign&mt=8",
            start="2026-10-01",
            end="2026-10-02",
        )
        anon = OperatorClient(self.client.origin)
        anon.bootstrap()
        self.reject(anon, path, body, 403)
        self.reject(self.client, path, dict(body, link=str(body["link"]).replace("id123", "id999")), 400)
        self.reject(self.client, path, dict(body, end="2026-11-01"), 400)
        self.reject(self.client, path, dict(body, start="2026-09-01", end="2026-09-02"), 400)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)

        with patch("mission_control.worker.read_report") as provider:
            result = self.post(path, body)
            self.assertEqual(self.post(path, body), result)
        provider.assert_not_called()
        first, second = result["jobs"]
        self.assertEqual([first["processing_date"], second["processing_date"]], ["2026-10-01", "2026-10-02"])
        self.assertFalse(result["external_writes"])
        with connection(self.store.path, write=True) as db:
            for job, instance, status in ((first, "day-1", "SUCCEEDED"), (second, "day-2", "BLOCKED")):
                row = db.execute("SELECT data FROM jobs WHERE id=?", (job["job_id"],)).fetchone()
                data = json.loads(row["data"])
                self.assertEqual(data["options"]["report_family"], CAMPAIGN_DOWNLOADS)
                self.assertEqual(data["options"]["instance_id"], instance)
                self.assertNotIn("synthetic-campaign", row["data"])
                db.execute("UPDATE jobs SET status=? WHERE id=?", (status, job["job_id"]))
        replay = self.post(path, body)["jobs"]
        self.assertEqual(replay[1]["status"], "BLOCKED")
        self.assertEqual(replay[1]["job_id"], second["job_id"])
        refreshed = self.campaign_inventory(files)
        self.reject(self.client, path, body, 400)
        retried = self.post(path, dict(body, inventory_id=refreshed))["jobs"]
        self.assertEqual(retried[0]["job_id"], first["job_id"])
        self.assertNotEqual(retried[1]["job_id"], second["job_id"])
        self.assertEqual(retried[1]["status"], "QUEUED")

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
