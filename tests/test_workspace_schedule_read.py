"""Read-scoped agents see their app's saved cadence without private diagnostics."""

import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from mission_control.apple_metrics_schedule import AppleMetricsSchedules
from mission_control.db import connection
from mission_control.service import Service
from mission_control.store import Store
from mission_control.operator_client import ClientError, OperatorClient
from tests import test_apple_metrics_http_route as route_fixture


class WorkspaceScheduleReadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "workspace.sqlite")
        self.service = Service(self.store)

    def test_missing_schedule_is_unknown_not_an_enabled_default(self):
        value = self.service.workspace("sample-one")
        self.assertIsNone(value["apple_analytics_schedule"])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM apple_metrics_schedules").fetchone()[0], 0)

    def test_saved_cadence_is_app_scoped_read_only_and_redacts_diagnostics(self):
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", dict(app["data"], store_app_id="123"), app["version"])
        self.service.evidence(
            "sample-one",
            dict(
                kind="connection",
                title="Synthetic Apple",
                source="Fixture only",
                data=dict(
                    provider="app_store", store_app_id="123", env_ref="GROWTH_SAMPLE_ONE_SYNTHETIC", account_id="0"
                ),
            ),
        )
        schedules = AppleMetricsSchedules(self.store)
        saved = schedules.save("sample-one", dict(enabled=True, interval_hours=24, report_id="report-1", version=None))
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE apple_metrics_schedules SET last_error=? WHERE app_id=?",
                ("PRIVATE_DIAGNOSTIC_SENTINEL", "sample-one"),
            )
        before = schedules.get("sample-one")
        workspace = self.service.workspace("sample-one")
        visible = workspace["apple_analytics_schedule"]
        self.assertEqual(visible["id"], saved["id"])
        self.assertEqual(visible["interval_hours"], 24)
        self.assertEqual(visible["next_due"], saved["next_due"])
        self.assertTrue(visible["enabled"])
        self.assertIsNone(visible["last_success"])
        self.assertIsNone(visible["last_error"])
        for private in ("connection_hash", "credential_ref", "private_key"):
            self.assertNotIn(private, visible)
        self.assertNotIn("PRIVATE_DIAGNOSTIC_SENTINEL", json.dumps(workspace))
        self.assertIsNone(self.service.workspace("sample-two")["apple_analytics_schedule"])
        self.assertEqual(schedules.get("sample-one"), before, "Inspection must not change saved state")

    def test_read_grant_sees_cadence_without_cross_app_or_owner_authority(self):
        fixture = route_fixture.AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        saved = AppleMetricsSchedules(fixture.store).save(
            "sample-one", dict(enabled=True, interval_hours=48, report_id="report-1", version=None)
        )
        issued = fixture.client.request(
            "POST",
            "/api/apps/sample-one/agent-grants/issue",
            dict(
                agent_id="readonly-schedule-tester",
                manifest_version=fixture.app["version"],
                operations=["workspace.read"],
                max_calls=3,
                expires=(datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            ),
        )
        agent = OperatorClient(fixture.client.origin, issued["token"])
        observed = agent.call(dict(app_id="sample-one", operation="workspace.read", input={}))
        self.assertEqual(observed["apple_analytics_schedule"]["id"], saved["id"])
        self.assertEqual(observed["apple_analytics_schedule"]["next_due"], saved["next_due"])
        with self.assertRaises(ClientError) as denied:
            agent.call(dict(app_id="sample-two", operation="workspace.read", input={}))
        self.assertEqual(denied.exception.status, 403)
        self.assertEqual(AppleMetricsSchedules(fixture.store).get("sample-one"), saved)


if __name__ == "__main__":
    unittest.main()
