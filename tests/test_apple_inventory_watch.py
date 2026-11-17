"""Owner and worker regressions for availability checks before Apple files exist."""

import time
import unittest
from collections.abc import Mapping
from datetime import datetime, timezone
from unittest.mock import patch

from mission_control import migrations
from mission_control.apple_analytics import CAMPAIGN_DOWNLOADS
from mission_control.apple_metrics_http import view
from mission_control.apple_metrics_schedule import AppleMetricsSchedules, check_scheduled_db
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.ios_reports import read
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import jobs, persist_job_result, run_once
from tests import test_apple_metrics_http as http_fixture
from tests import test_apple_metrics_schedule as worker_fixture

APP, STORE_APP = worker_fixture.APP, worker_fixture.STORE_APP
WATCH = {"enabled": True, "version": None, "interval_hours": 24, "mode": "inventory"}


def utc_stamp(value: float) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def waiting_inventory() -> dict[str, object]:
    """Model a complete provider inventory that contains no measurements."""
    return {
        "operation": "analytics_reports",
        "status": "WAITING_FOR_REPORTS",
        "coverage": "COMPLETE",
        "metric_observations": None,
        "reports": [dict(worker_fixture.INVENTORY["reports"][0], instances=[])],
    }


def _observed(report: Mapping[str, object]) -> dict[str, object]:
    rows = report["rows"]
    assert isinstance(rows, list)
    return {row["metric"]: row["observed"] for row in rows}


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
        with patch(
            "mission_control.provider_reports.read_analytics", return_value=waiting_inventory()
        ) as provider_read:
            self.assertTrue(run_once(self.store))
        self.assertEqual(provider_read.call_args.args[1], STORE_APP)
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
        report = _observed(read(self.store, APP))
        self.assertEqual(report["Apple scheduled read"], "WAITING_FOR_REPORTS")
        self.assertIsNotNone(report["Apple next due"])
        self.assertIsNone(report["Apple numeric outcome"])

    def test_deferred_first_watch_starts_once_at_the_exact_time_after_restart(self) -> None:
        current = int(time.time())
        due = current + 1800
        stamp = datetime.fromtimestamp(due, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        with patch("mission_control.apple_metrics_schedule.time.time", return_value=current):
            saved = self.schedules.save(APP, WATCH | {"first_read_at": stamp})
            assert saved is not None
            self.assertEqual(saved["next_due"], due)
            self.assertEqual(self.schedules.tick(), 0)
        restarted = AppleMetricsSchedules(Store(self.store.path))
        with patch("mission_control.apple_metrics_schedule.time.time", return_value=due - 1):
            self.assertEqual(restarted.tick(), 0)
        self.assertEqual(jobs(self.store, APP), [])
        with patch("mission_control.apple_metrics_schedule.time.time", return_value=due):
            self.assertEqual(restarted.tick(), 1)
            self.assertEqual(restarted.tick(), 0)
        queued = jobs(self.store, APP)
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["data"]["options"], {"operation": "analytics_reports"})
        updated = restarted.get(APP)
        assert updated is not None
        self.assertEqual(updated["next_due"], due + 86400)
        self.assertEqual(jobs(self.store, "sample-two"), [])

    def test_bad_first_check_preserves_the_current_watch(self) -> None:
        saved = self.schedules.save(APP, WATCH)
        assert saved is not None
        config = WATCH | {"version": saved["version"]}
        for bad in (
            None,
            "not a time",
            "2026-11-17T09:47:00",
            "2026-11-17T09:47:00-05:00",
            "2026-11-17T14:47:00.000001Z",
            "2000-01-01T00:00:00Z",
            "2099-01-01T00:00:00Z",
        ):
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                self.schedules.save(APP, config | {"first_read_at": bad})
            self.assertEqual(self.schedules.get(APP), saved)
        with self.assertRaises(Invalid):
            self.schedules.save(APP, {"enabled": False, "version": saved["version"], "first_read_at": None})
        self.assertEqual(jobs(self.store, APP), [])

    def test_deadline_persists_and_cancels_a_queued_job_on_restart(self) -> None:
        current = int(time.time())
        due, stop = current + 1800, current + 3600
        clock = "mission_control.apple_metrics_schedule.time.time"
        with patch(clock, return_value=current):
            saved = self.schedules.save(APP, WATCH | {"first_read_at": utc_stamp(due), "stop_at": utc_stamp(stop)})
        assert saved is not None
        self.assertEqual(saved["stop_at"], stop)
        with patch(clock, return_value=due):
            self.assertEqual(self.schedules.tick(), 1)
        queued = jobs(self.store, APP)[0]
        restarted = AppleMetricsSchedules(Store(self.store.path))
        with patch(clock, return_value=stop), connection(self.store.path) as db:
            with self.assertRaisesRegex(Invalid, "window ended"):
                check_scheduled_db(db, queued)
            self.assertEqual(restarted.get(APP)["status"], "EXPIRED")
            self.assertEqual(restarted.tick(), 0)
        self.assertEqual(jobs(self.store, APP)[0]["status"], "CANCELLED")
        self.assertEqual(len(jobs(self.store, APP)), 1)
        rows = _observed(read(self.store, APP))
        self.assertEqual(rows["Apple schedule"], "EXPIRED")
        self.assertIsNone(rows["Apple next due"])

    def test_deadline_rejects_late_claim_before_provider_access(self) -> None:
        current = int(time.time())
        stop = current + 2
        clock = "mission_control.apple_metrics_schedule.time.time"
        with patch(clock, return_value=current):
            self.schedules.save(APP, WATCH | {"stop_at": utc_stamp(stop)})
            self.assertEqual(self.schedules.tick(), 1)
        with (
            patch(clock, return_value=stop),
            patch("mission_control.provider_reports.read_analytics") as provider,
        ):
            self.assertTrue(run_once(self.store))
        provider.assert_not_called()
        self.assertEqual(jobs(self.store, APP)[0]["status"], "BLOCKED")
        with patch(clock, return_value=stop):
            self.assertEqual(self.schedules.tick(), 0)

    def test_invalid_deadline_does_not_replace_an_open_schedule(self) -> None:
        current = int(time.time())
        due = current + 600
        with patch("mission_control.apple_metrics_schedule.time.time", return_value=current):
            saved = self.schedules.save(APP, WATCH)
            assert saved is not None
            self.assertIsNone(saved["stop_at"])
            config = WATCH | {"version": saved["version"], "first_read_at": utc_stamp(due)}
            for invalid in (None, "no", utc_stamp(due), utc_stamp(current + 7 * 86400 + 1)):
                with self.subTest(invalid=invalid), self.assertRaises(Invalid):
                    self.schedules.save(APP, config | {"stop_at": invalid})
                self.assertEqual(self.schedules.get(APP), saved)

    def test_inflight_read_does_not_replace_inventory_after_deadline(self) -> None:
        started = int(time.time())
        stop = started + 2
        current = [started]

        def respond(*_args, **_kwargs):
            current[0] = stop
            return waiting_inventory()

        with (
            patch("mission_control.apple_metrics_schedule.time.time", side_effect=lambda: current[0]),
            patch("mission_control.provider_reports.read_analytics", side_effect=respond) as provider,
        ):
            self.schedules.save(APP, WATCH | {"stop_at": utc_stamp(stop)})
            self.assertEqual(self.schedules.tick(), 1)
            self.assertTrue(run_once(self.store))
        provider.assert_called_once()
        self.assertEqual(jobs(self.store, APP)[0]["status"], "BLOCKED")
        self.assertIsNone(view(self.store, APP)["inventory"])

    def test_forward_migration_keeps_existing_schedule(self) -> None:
        saved = self.schedules.save(APP, WATCH)
        assert saved is not None
        with connection(self.store.path) as db:
            # Recreate the previous schema shape around the actual schedule row.
            db.execute("ALTER TABLE apple_metrics_schedules DROP COLUMN stop_at")
            db.execute("DELETE FROM schema_migrations WHERE version=4")
        Store(self.store.path)
        self.assertEqual(self.schedules.get(APP), saved)
        with connection(self.store.path) as db:
            self.assertEqual(migrations.applied(db)[-1]["name"], "apple_watch_deadline")

    def test_listed_daily_detailed_file_is_actionable_but_not_a_count(self) -> None:
        self.schedules.save(APP, WATCH)
        self.assertEqual(self.schedules.tick(), 1)
        detail = {
            "id": "private-report-key",
            "name": CAMPAIGN_DOWNLOADS,
            "coverage": "COMPLETE",
            "instances": [{"id": "private-file-key", "granularity": "DAILY", "processing_date": "2026-11-17"}],
        }
        response = waiting_inventory() | {"status": "METRIC_DOWNLOAD_REQUIRED", "reports": [detail]}
        with patch("mission_control.provider_reports.read_analytics", return_value=response):
            self.assertTrue(run_once(self.store))
        saved = jobs(self.store, APP)[0]
        report = read(self.store, APP)
        rows = _observed(report)
        self.assertEqual(rows["Apple scheduled read"], "APPLE_CAMPAIGN_FILE_AVAILABLE")
        self.assertIsNone(rows["Apple numeric outcome"])
        notices = Service(self.store).workspace(APP)["workflow"]["exceptions"]
        self.assertEqual(len(notices), 1)
        self.assertEqual(notices[0]["state"], "APPLE_CAMPAIGN_FILE_AVAILABLE")
        self.assertEqual(notices[0]["repair_route"], "apple-analytics")
        self.assertEqual(Service(self.store).workspace(APP)["workflow"]["exceptions"], notices)
        self.assertNotIn("private-report-key", canonical(notices + [report]))
        self.assertNotIn("private-file-key", canonical(notices + [report]))

        for replace, expected in (
            ({"app_id": "sample-two"}, "UNCONFIRMED"),
            ({"observed_at": "2099-01-01T00:00:00Z"}, "UNCONFIRMED"),
            ({"reports": [detail | {"coverage": "PARTIAL"}]}, "UNCONFIRMED"),
            ({"reports": [detail | {"name": "App Downloads Standard"}]}, "APPLE_REPORT_FILES_LISTED"),
            ({"status": "REPORT_SETUP_REQUIRED", "reports": []}, "APPLE_REPORT_SETUP_REQUIRED"),
        ):
            with self.subTest(expected=expected), connection(self.store.path) as db:
                db.execute("UPDATE jobs SET result=? WHERE id=?", (canonical(saved["result"] | replace), saved["id"]))
            rows = _observed(read(self.store, APP))
            self.assertEqual(rows["Apple scheduled read"], expected)
            self.assertIsNone(rows["Apple numeric outcome"])
            pending = Service(self.store).workspace(APP)["workflow"]["exceptions"]
            self.assertNotIn("APPLE_CAMPAIGN_FILE_AVAILABLE", {item["state"] for item in pending})

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
        due = (datetime.now(timezone.utc).timestamp() // 60 + 30) * 60
        stamp = datetime.fromtimestamp(due, timezone.utc).isoformat().replace("+00:00", "Z")
        scheduled = fixture.dispatch("schedule", body | {"first_read_at": stamp})
        assert isinstance(scheduled, dict)
        self.assertEqual(scheduled["mode"], "inventory")
        self.assertIsNone(scheduled["report_id"])
        self.assertEqual(scheduled["next_due"], due)
        boundary = utc_stamp(due + 86400)
        updated = fixture.dispatch(
            "schedule", body | {"version": scheduled["version"], "first_read_at": stamp, "stop_at": boundary}
        )
        self.assertEqual(updated["stop_at"], due + 86400)
        self.assertIsNone(view(fixture.store, APP)["inventory"])
