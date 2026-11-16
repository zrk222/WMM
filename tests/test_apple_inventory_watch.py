"""Owner and worker regressions for availability checks before Apple files exist."""

import time
import unittest
from unittest.mock import patch

from mission_control.apple_metrics_http import view
from mission_control.apple_metrics_schedule import AppleMetricsSchedules
from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.worker import jobs, persist_job_result, run_once
from tests import test_apple_metrics_http as http_fixture
from tests import test_apple_metrics_schedule as worker_fixture

APP, STORE_APP = worker_fixture.APP, worker_fixture.STORE_APP
WATCH = {"enabled": True, "version": None, "interval_hours": 24, "mode": "inventory"}


def waiting_inventory() -> dict[str, object]:
    """Model a complete provider inventory that contains no measurements."""
    return {
        "operation": "analytics_reports",
        "status": "WAITING_FOR_REPORTS",
        "coverage": "COMPLETE",
        "metric_observations": None,
        "reports": [dict(worker_fixture.INVENTORY["reports"][0], instances=[])],
    }


class AppleInventoryWatchTests(unittest.TestCase):
    def setUp(self) -> None:
        fixture = worker_fixture.AppleMetricsScheduleTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.store = fixture.store
        self.schedules = fixture.schedules

    def test_restart_retains_current_metadata_without_numeric_success(self) -> None:
        self.schedules.save(APP, WATCH)
        restarted = AppleMetricsSchedules(Store(self.store.path))
        self.assertEqual(restarted.tick(), 1)
        pending = jobs(self.store, APP)[0]
        self.assertEqual(pending["data"]["options"], {"operation": "analytics_reports"})
        with patch("mission_control.provider_reports.read_analytics", return_value=waiting_inventory()) as read:
            self.assertTrue(run_once(self.store))
        self.assertEqual(read.call_args.args[1], STORE_APP)
        current = view(self.store, APP)
        inventory, schedule = current["inventory"], current["schedule"]
        assert isinstance(inventory, dict) and isinstance(schedule, dict)
        self.assertEqual(inventory["job_id"], pending["id"])
        self.assertEqual(inventory["status"], "WAITING_FOR_REPORTS")
        self.assertEqual(schedule["last_job_status"], "SUCCEEDED")
        self.assertIsNone(schedule["last_success"])
        self.assertIsNone(schedule["report_id"])
        self.assertEqual(schedule["mode"], "inventory")
        self.assertEqual(schedule["failures"], 0)
        self.assertIsNone(view(self.store, "sample-two")["inventory"])
        self.assertEqual(restarted.tick(), 0)
        self.assertEqual(len(jobs(self.store, APP)), 1)

    def test_expired_lease_and_pause_prevent_stale_persistence(self) -> None:
        setting = self.schedules.save(APP, WATCH)
        assert setting is not None
        self.assertEqual(self.schedules.tick(), 1)
        job = jobs(self.store, APP)[0]
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=1 WHERE id=?", (job["id"],))
        job["attempts"] = 1
        result = waiting_inventory() | {
            "provider": "app_store",
            "app_id": APP,
            "store_app_id": STORE_APP,
            "request": {"operation": "analytics_reports"},
            "external_writes": False,
            "source_hash": digest({"fixture": "inventory"}),
            "observed_at": "2026-11-16T20:00:00Z",
        }
        persist_job_result(self.store, job, result, "SUCCEEDED", 0)
        self.assertEqual(jobs(self.store, APP)[0]["status"], "RUNNING")
        self.schedules.save(APP, {"enabled": False, "version": setting["version"]})
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=? WHERE id=?", (time.time() + 100, job["id"]))
        persist_job_result(self.store, job, result, "SUCCEEDED", 0)
        self.assertEqual(jobs(self.store, APP)[0]["status"], "BLOCKED")
        current = self.schedules.get(APP)
        assert current is not None
        self.assertEqual(current["status"], "PAUSED")
        self.assertIsNone(view(self.store, APP)["inventory"])


class AppleInventoryWatchRouteTests(unittest.TestCase):
    def test_owner_can_opt_in_without_report_identity(self) -> None:
        fixture = http_fixture.AppleMetricsHttpTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        body = WATCH | {"manifest_version": fixture.app["version"]}
        for invalid in (body | {"report_id": "report-1"}, body | {"mode": "downloads"}, body | {"interval_hours": 23}):
            with self.subTest(invalid=invalid), self.assertRaises(Invalid):
                fixture.dispatch("schedule", invalid)
        self.assertEqual(fixture.count("apple_metrics_schedules"), 0)
        scheduled = fixture.dispatch("schedule", body)
        assert isinstance(scheduled, dict)
        self.assertEqual(scheduled["mode"], "inventory")
        self.assertIsNone(scheduled["report_id"])
        self.assertIsNone(view(fixture.store, APP)["inventory"])
