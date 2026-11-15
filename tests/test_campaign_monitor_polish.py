"""Synthetic SQLite regression coverage for monitor fairness and evidence repair."""

import unittest

from mission_control import campaign_monitor as core
from mission_control.db import connection
from tests import test_campaign_monitor as fixtures


class MonitorPolishTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CampaignMonitorTests("test_tick_atomic_unique_pending_and_twenty_limit")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store

    def test_pending_due_monitors_do_not_starve_new_work_and_limit_is_twenty(self):
        pending = [self.fixture.activate() for _ in range(21)]
        self.assertEqual(core.tick(self.store), 20)
        self.assertEqual(core.tick(self.store), 1)
        fresh = [self.fixture.activate() for _ in range(21)]
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET due=0 WHERE last_job IS NOT NULL")
        self.assertEqual(core.tick(self.store), 20)
        self.assertEqual(core.tick(self.store), 1)
        self.assertEqual(core.tick(self.store), 0)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='campaign_monitor'").fetchone()[0], 42)
            self.assertEqual(db.execute("SELECT count(*) FROM campaign_monitors WHERE runs=1").fetchone()[0], 42)
        self.assertEqual(len(pending) + len(fresh), 42)

    def test_corrupt_summary_is_repairable_and_does_not_block_healthy_neighbor(self):
        for raw in ("{broken", "[]", "null", "{}"):
            with self.subTest(raw=raw):
                broken = self.fixture.activate()
                healthy = self.fixture.activate()
                with connection(self.store.path) as db:
                    db.execute("UPDATE campaign_monitors SET summary=?,due=0 WHERE id=?", (raw, broken["id"]))
                with self.fixture.owner():
                    history = self.fixture.monitors.history("sample")["monitors"]
                shown = next(value for value in history if value["id"] == broken["id"])
                self.assertEqual(shown["effective_status"], "NEEDS_REPAIR")
                self.assertIsNone(shown["summary"])
                self.assertIsNone(shown["last_observation"])
                self.assertEqual(core.tick(self.store), 1)
                with connection(self.store.path) as db:
                    saved = db.execute(
                        "SELECT status,last_job,summary FROM campaign_monitors WHERE id=?", (broken["id"],)
                    ).fetchone()
                    self.assertEqual(saved["status"], "BLOCKED")
                    self.assertIsNone(saved["last_job"])
                    self.assertEqual(saved["summary"], raw)
                self.assertEqual(self.fixture.status(healthy)["runs"], 1)
                with self.fixture.owner():
                    off = self.fixture.monitors.off("sample", broken["id"], broken["version"])
                self.assertEqual(off["status"], "OFF")
                self.assertIsNone(off["summary"])

    def test_tick_isolates_corrupt_summary_before_history_is_read(self):
        for raw in ("{broken", "[]", "null", "{}"):
            with self.subTest(raw=raw):
                broken = self.fixture.activate()
                healthy = self.fixture.activate()
                with connection(self.store.path) as db:
                    db.execute("UPDATE campaign_monitors SET summary=?,due=0 WHERE id=?", (raw, broken["id"]))
                self.assertEqual(core.tick(self.store), 1)
                with connection(self.store.path) as db:
                    saved = db.execute(
                        "SELECT status,last_job FROM campaign_monitors WHERE id=?", (broken["id"],)
                    ).fetchone()
                self.assertEqual(saved["status"], "BLOCKED")
                self.assertIsNone(saved["last_job"])
                self.assertEqual(self.fixture.status(healthy)["runs"], 1)
