"""Two genuine app-scoped agents operate distinct steps through the loopback gateway."""

import gzip
import hashlib
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from mission_control.apple_analytics import DISCOVERY, DOWNLOADS
from mission_control.common import now
from mission_control.db import connection
from mission_control.insights import Insights
from mission_control.openseo_read import save_reading
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import Server
from mission_control.store import Store
from mission_control.worker import run_once
from tests import test_apple_metrics_http_route as fixtures
from tests.test_measurement_connectors import FakeVault
from tests.test_openseo_read import provider_reply, setup


class TeamExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = fixtures.AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
        self.addCleanup(self.route.doCleanups)
        self.route.setUp()
        store = self.route.store
        app = store.app(fixtures.APP)
        app = store.save_app(
            fixtures.APP,
            dict(app["data"], website="https://sample.example", release="build-1", locale="en-US"),
            app["version"],
        )
        self.body = dict(start="2026-01-01", end="2026-01-05", manifest_version=app["version"])
        FakeVault.values, FakeVault.fail_delete = {}, 0
        with patch("mission_control.insights.Vault", FakeVault):
            owner = Insights(store)
            with patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply):
                sid = owner.setup(fixtures.APP, setup())["source_id"]
            report = owner.list(fixtures.APP)["reports"][0]
            save_reading(
                store,
                fixtures.APP,
                sid,
                dict(id="native-search-review", manifest_version=app["version"], report_id=report["id"]),
            )
        self.apple = self.issue("dot-agent")
        self.web = self.issue("duet-agent")
        self.review_hash = self.route.post(fixtures.BASE + "search-review", self.body)["search_review"]["review_hash"]

    def issue(self, name: str, operations: list[str] | None = None) -> dict[str, Any]:
        return self.route.post(
            "/api/apps/sample-one/agent-grants/issue",
            dict(
                agent_id=name,
                expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                max_calls=30,
                manifest_version=self.body["manifest_version"],
                operations=operations or ["search.plan.execute"],
            ),
        )

    def assign(self, action: str, grant: dict) -> dict[str, Any]:
        return self.route.post(
            fixtures.BASE + "search-review-assign",
            dict(self.body, review_hash=self.review_hash, action_id=action, grant_id=grant["grant"]["id"]),
        )

    def call(self, grant: dict, action: str | None = None) -> dict[str, Any]:
        client = OperatorClient(self.route.client.origin, grant_token=grant["token"])
        result = client.call(
            dict(
                app_id=fixtures.APP,
                operation="search.plan.execute",
                input=dict(action_id=action, review_hash=self.review_hash) if action else {},
            )
        )
        assert isinstance(result, dict)
        return result

    def test_named_team_dependencies_exact_retry_and_blocked_external_verification(self) -> None:
        self.assign("apple-baseline", self.apple)
        self.assign("web-baseline", self.web)
        self.assign("store-link-check", self.apple)
        self.assertEqual({r["action_id"] for r in self.call(self.web)["assignments"]}, {"web-baseline"})
        with self.assertRaises(ClientError) as other:
            self.call(self.apple, "web-baseline")
        self.assertEqual(other.exception.status, 403)
        with self.assertRaises(ClientError) as rejected:
            self.call(self.apple, "store-link-check")
        self.assertEqual(rejected.exception.status, 400)
        with ThreadPoolExecutor(max_workers=2) as workers:
            outputs = list(workers.map(lambda _: self.call(self.web, "web-baseline"), range(2)))
        self.assertEqual(outputs[0], outputs[1])
        web = outputs[0]["assignment"]
        self.assertEqual(web["status"], "COMPLETED")
        self.assertEqual(web["deliverable"]["details"]["click_through_rate"], 0.04)
        apple = self.call(self.apple, "apple-baseline")["assignment"]
        self.assertEqual(apple["status"], "NEEDS_EXTERNAL_VERIFICATION")
        self.assertIsNone(apple["deliverable"]["details"]["first_time_downloads"]["mature_observed_total"])
        link = self.call(self.apple, "store-link-check")["assignment"]
        self.assertEqual(link["status"], "NEEDS_EXTERNAL_VERIFICATION")
        self.assertEqual(len(link["receipt_sha256"]), 64)
        self.assertEqual(self.call(self.apple, "store-link-check")["assignment"], link)
        self.assertEqual(
            self.route.post(fixtures.BASE + "search-review", self.body)["search_review"]["assignments"]["web-baseline"],
            web,
        )
        with self.assertRaises(ClientError) as rejected:
            self.assign("web-baseline", self.apple)
        self.assertEqual(rejected.exception.status, 400)
        with connection(self.route.store.path) as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM search_team_assignments WHERE result IS NOT NULL").fetchone()[0], 3
            )

        with connection(self.route.store.path, write=True) as db:
            db.execute("UPDATE records SET version=version+1 WHERE id=?", (self.route.record["id"],))
        refreshed = self.route.post(fixtures.BASE + "search-review", self.body)["search_review"]
        self.assertEqual(refreshed["earlier_plans"][0]["assignments"]["web-baseline"], web)

    def test_reassignment_revocation_and_changed_sources(self) -> None:
        other_scope = self.issue("other", ["growth.read"])
        with self.assertRaises(ClientError) as rejected:
            self.assign("web-baseline", other_scope)
        self.assertEqual(rejected.exception.status, 400)
        self.assign("web-baseline", self.web)
        self.assign("web-baseline", self.apple)
        with self.assertRaises(ClientError) as denied:
            self.call(self.web, "web-baseline")
        self.assertEqual(denied.exception.status, 403)
        with connection(self.route.store.path, write=True) as db:
            db.execute("UPDATE records SET version=version+1 WHERE id=?", (self.route.record["id"],))
        with self.assertRaises(ClientError) as rejected:
            self.call(self.apple, "web-baseline")
        self.assertEqual(rejected.exception.status, 400)
        with connection(self.route.store.path, write=True) as db:
            db.execute(
                "UPDATE agent_grants SET status='REVOKED',version=version+1 WHERE id=?", (self.apple["grant"]["id"],)
            )
        with self.assertRaises(ClientError) as revoked:
            self.call(self.apple)
        self.assertEqual(revoked.exception.status, 403)
        with connection(self.route.store.path) as db:
            self.assertEqual(
                db.execute("SELECT status,result FROM search_team_assignments").fetchone()[:], ("ASSIGNED", None)
            )

    def test_reopened_datastore_returns_original_result(self) -> None:
        self.assign("web-baseline", self.web)
        result = self.call(self.web, "web-baseline")
        self.route.stop_server()
        restarted = Server(("127.0.0.1", 0), Store(self.route.store.path, seed=False))
        thread = threading.Thread(target=restarted.serve_forever)
        thread.start()
        try:
            agent = OperatorClient("http://127.0.0.1:" + str(restarted.server_port), grant_token=self.web["token"])
            request = dict(
                app_id=fixtures.APP,
                operation="search.plan.execute",
                input=dict(action_id="web-baseline", review_hash=self.review_hash),
            )
            with patch("mission_control.search_team_analysis.produce", side_effect=AssertionError("unexpected replay")):
                self.assertEqual(agent.call(request), result)
        finally:
            restarted.shutdown()
            restarted.server_close()
            thread.join()

    def test_team_completes_combined_brief_after_both_evidenced_baselines(self) -> None:
        # A missing source cannot authorize the downstream experiment brief.
        with self.assertRaises(ClientError) as missing:
            self.assign("test-brief", self.web)
        self.assertEqual(missing.exception.status, 400)
        self.body["end"] = self.body["start"]
        self.route.app = self.route.store.app(fixtures.APP)
        job = self.route.post(fixtures.BASE + "inventory", self.route.inventory_body())
        reports = [
            dict(
                id=key,
                name=family,
                coverage="COMPLETE",
                instances=[dict(id=key + "-day", granularity="DAILY", processing_date=date)],
            )
            for key, family, date in (("discovery", DISCOVERY, "2026-01-04"), ("downloads", DOWNLOADS, "2026-01-03"))
        ]
        inventory = dict(
            provider="app_store",
            operation="analytics_reports",
            app_id=fixtures.APP,
            store_app_id="123",
            status="METRIC_DOWNLOAD_REQUIRED",
            coverage="COMPLETE",
            observed_at=now(),
            reports=reports,
        )
        with patch("mission_control.worker.read_report", return_value=inventory):
            self.assertTrue(run_once(self.route.store))
        queued = self.route.post(fixtures.BASE + "performance-collect", dict(self.body, inventory_id=job["job_id"]))
        self.assertEqual(len(queued["jobs"]), 2)

        def segments(_reader: Any, _store: str, report: str, instance: str) -> list[dict]:
            files = {
                "discovery": b"Date\tApp Apple Identifier\tEvent\tCounts\tUnique Counts\n2026-01-01\t123\tImpression\t80\t50\n",
                "downloads": b"Date\tApp Apple Identifier\tDownload Type\tCounts\n2026-01-01\t123\tFirst-time download\t7\n",
            }
            raw = gzip.compress(files[report], mtime=0)
            return [
                dict(id=instance, data=raw, size=len(raw), checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest())
            ]

        with (
            patch("mission_control.provider_reports.credential", return_value="fixture"),
            patch("mission_control.provider_reports.read_analytics", return_value=inventory),
            patch("mission_control.provider_reports.read_instance_segments", side_effect=segments),
        ):
            self.assertTrue(run_once(self.route.store))
            self.assertTrue(run_once(self.route.store))
        review = self.route.post(fixtures.BASE + "search-review", self.body)["search_review"]
        self.review_hash = review["review_hash"]
        coordinator = self.issue("grok-bot")
        self.assign("test-brief", coordinator)
        self.assign("apple-baseline", self.apple)
        self.assign("web-baseline", self.web)
        web = self.call(self.web, "web-baseline")["assignment"]
        with self.assertRaises(ClientError) as waiting:
            self.call(coordinator, "test-brief")
        self.assertEqual(waiting.exception.status, 400)
        apple = self.call(self.apple, "apple-baseline")["assignment"]
        brief = self.call(coordinator, "test-brief")["assignment"]
        self.assertEqual(brief["status"], "COMPLETED")
        details = brief["deliverable"]["details"]
        self.assertEqual(details["page_url"], "https://sample.example/guide")
        self.assertEqual(details["apple_app_wide_counts"]["first_time_downloads"], 7)
        self.assertEqual(details["google_counts"]["clicks"], 4)
        self.assertEqual(
            details["baseline_receipts"],
            {"apple-baseline": apple["receipt_sha256"], "web-baseline": web["receipt_sha256"]},
        )
        self.assertIn("suppress", details["stop_rules"])
        self.assertEqual(self.call(coordinator, "test-brief")["assignment"], brief)
        self.assign("measure-tag", coordinator)
        with self.assertRaises(ClientError) as external:
            self.call(coordinator, "measure-tag")
        self.assertEqual(external.exception.status, 400)
