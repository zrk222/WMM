"""Opt-in local notices stay quiet by default and never repeat across restarts."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest

from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.notices import collect, configure, deliver, dismiss, enabled, pending, status, sync
from mission_control.store import Store

APP = "sample-one"


class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "state.sqlite"
        self.store = Store(self.path, seed=False)
        self.store.save_app(APP, dict(name="Synthetic app", release="build-1", job="Synthetic job",
                                     audience="Synthetic audience", activation="Synthetic value", locale="en-US"))
        from mission_control.campaign_monitor import initialize as initialize_monitors
        initialize_monitors(self.store)

    def insert_fixtures(self):
        stamp = now()
        soon = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with connection(self.store.path) as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       ("job-failed", APP, "pipeline", "{}", "FAILED", 1, 0,
                        canonical(dict(secret="PRIVATE_RESULT")), stamp, stamp, "job-request"))
            db.execute("INSERT INTO agent_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("grant-soon", APP, "agent", "owner", 1, 1, "a" * 64, '["workspace.read"]',
                        "b" * 64, soon, 5, 0, "ACTIVE", 1, stamp, stamp))
            db.execute("INSERT INTO campaign_monitors VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       ("monitor-1", APP, "owner", "{}", digest({}), "BLOCKED", 1, 0, 0, 0, 0, None, stamp, stamp))
            db.execute("INSERT INTO apple_metrics_schedules VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (APP, "connection", "conn-1", 1, "c" * 64, 1, "report", 24, 1, 1, 0, None, None, None, 0,
                        "BLOCKED", None, "Synthetic failure", stamp))

    def test_default_is_quiet_and_opt_in_is_explicit(self):
        self.assertFalse(enabled(self.store, APP))
        self.assertEqual(sync(self.store, APP), [])
        with self.assertRaises(Invalid):
            configure(self.store, APP, "yes")
        self.assertTrue(configure(self.store, APP, True))
        self.assertFalse(configure(self.store, APP, False))

    def test_notices_are_deduplicated_ordered_and_payload_free(self):
        configure(self.store, APP, True)
        self.insert_fixtures()
        first = sync(self.store, APP)
        self.assertEqual(len(first), 4)
        self.assertEqual({item["kind"] for item in first}, {"JOB", "AGENT_GRANT", "CAMPAIGN_MONITOR", "APPLE_SCHEDULE"})
        self.assertNotIn("PRIVATE_RESULT", canonical(collect(self.store, APP)))
        self.assertEqual([item["id"] for item in sync(self.store, APP)], [item["id"] for item in first])
        second = Store(self.path, seed=False)
        self.assertEqual([item["id"] for item in sync(second, APP)], [item["id"] for item in first])

    def test_delivery_dismissal_and_failure_never_repeat(self):
        configure(self.store, APP, True)
        self.insert_fixtures()
        sync(self.store, APP)
        seen = []
        delivered = deliver(self.store, APP, lambda item: seen.append(item["id"]))
        self.assertEqual(len(delivered), 4)
        self.assertTrue(all(item["outcome"] == "DELIVERED" for item in delivered))
        self.assertEqual(pending(self.store, APP), [])
        Store(self.path, seed=False)
        self.assertEqual(sync(Store(self.path, seed=False), APP), [])
        self.assertEqual(status(self.store, APP)["delivered"], 4)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='INTERRUPTED',updated=? WHERE id='job-failed'", (now(),))
        fresh = sync(self.store, APP)
        self.assertEqual(len(fresh), 1)
        dismiss(self.store, APP, fresh[0]["id"])
        self.assertEqual(pending(self.store, APP), [])
        self.assertEqual(status(self.store, APP)["dismissed"], 1)
        with connection(self.store.path) as db:
            db.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       ("job-blocked", APP, "sync", "{}", "BLOCKED", 1, 0, "{}", now(), now(), "blocked-request"))
        failed = sync(self.store, APP)
        self.assertEqual(len(failed), 1)

        def broken(item):
            raise RuntimeError("permission denied")

        self.assertEqual(deliver(self.store, APP, broken)[0]["outcome"], "DELIVERY_FAILED")
        self.assertEqual(pending(self.store, APP), [])
        self.assertEqual(status(self.store, APP)["failed"], 1)

    def test_cli_is_quiet_until_opted_in_and_delivers_once(self):
        from mission_control.notices import main
        base = ["--database", str(self.path), "--app", APP]
        self.assertEqual(main(base + ["--once"]), 0)
        self.assertEqual(pending(self.store, APP), [])
        self.insert_fixtures()
        self.assertEqual(main(base + ["--enable"]), 0)
        self.assertEqual(main(base + ["--once"]), 0)
        self.assertEqual(pending(self.store, APP), [])
        self.assertEqual(main(base + ["--once"]), 0)
        self.assertEqual(status(self.store, APP)["delivered"], 4)

    def test_unknown_app_and_notice_are_rejected(self):
        with self.assertRaises(KeyError):
            enabled(self.store, "sample-two")
        configure(self.store, APP, True)
        with self.assertRaises(Invalid):
            dismiss(self.store, APP, "missing")


if __name__ == "__main__":
    unittest.main()
