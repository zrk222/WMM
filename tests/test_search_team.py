"""Two genuine app-scoped agents operate distinct steps through the loopback gateway."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from mission_control.db import connection
from mission_control.insights import Insights
from mission_control.openseo_read import save_reading
from mission_control.operator_client import ClientError, OperatorClient
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
