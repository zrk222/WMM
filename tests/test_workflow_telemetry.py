"""Actual SQLite/worker observations and selected-app HTTP projection."""

from pathlib import Path
import json
import tempfile
import unittest
from urllib.request import urlopen
from urllib.error import HTTPError
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.store import Store
from mission_control.worker import enqueue, claim, run_once
from mission_control.workflow_telemetry import emit, monitor
from tests import test_agent_grants as http_fixture


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite", seed=False)
        for name in ("sample-one", "sample-two"):
            self.store.save_app(
                name, dict(name="Synthetic telemetry", release="1", locale="en-US")
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_actual_pipeline_emits_ordered_stage_events_and_blocked_counts(self):
        enqueue(self.store, "sample-one", "pipeline", dict(stage=0), "telemetry-run")
        self.assertTrue(run_once(self.store))
        run = monitor(self.store, "sample-one")["runs"][0]
        self.assertEqual(run["status"], "SUCCEEDED")
        self.assertEqual(run["processed_stages"], 12)
        self.assertGreater(run["blocked_stages"], 0)
        self.assertEqual(run["events"][0]["code"], "STARTED")
        self.assertEqual(run["events"][-1]["code"], "SUCCEEDED")
        self.assertEqual(
            [row["stage"] for row in run["events"] if row["code"] == "STAGE_STARTED"],
            list(range(1, 13)),
        )
        self.assertEqual(len(run["events"]), 26)
        self.assertEqual(
            monitor(Store(self.store.path, seed=False), "sample-one")["runs"][0], run
        )

    def test_emit_rejects_cancelled_replaced_foreign_and_invalid_events(self):
        enqueue(self.store, "sample-one", "pipeline", dict(stage=1), "attempt-test")
        job = claim(self.store)
        for changes in (dict(attempts=2), dict(app_id="sample-two")):
            with self.assertRaises(Invalid):
                emit(self.store, dict(job, **changes), "STARTED")
        for code, stage in [
            ("private-raw-error", None),
            ("STAGE_STARTED", True),
            ("STAGE_STARTED", 13),
        ]:
            with self.assertRaises(Invalid):
                emit(self.store, job, code, stage)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='CANCELLED'")
        with self.assertRaises(Invalid):
            emit(self.store, job, "STAGE_STARTED", 1)
        self.assertEqual(monitor(self.store, "sample-one")["runs"][0]["events"], [])

    def test_monitor_excludes_payloads_and_old_attempt_counts(self):
        enqueue(
            self.store,
            "sample-one",
            "pipeline",
            dict(stage=1, secret="PRIVATE_PAYLOAD"),
            "private-test",
        )
        enqueue(self.store, "sample-two", "pipeline", dict(stage=1), "foreign-job")
        job = claim(self.store)
        emit(self.store, job, "STAGE_BLOCKED", 1)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET attempts=2,result=? WHERE id=?",
                (json.dumps(dict(error="PRIVATE_ERROR")), job["id"]),
            )
        value = monitor(self.store, "sample-one")
        self.assertEqual(len(value["runs"]), 1)
        self.assertEqual(value["runs"][0]["processed_stages"], 0)
        self.assertIsNone(value["runs"][0]["latest"])
        self.assertNotIn("PRIVATE_", json.dumps(value))
        self.assertEqual(monitor(self.store, "sample-two")["runs"][0]["events"], [])


class TelemetryHTTPTests(unittest.TestCase):
    setUp = http_fixture.GrantTests.setUp
    tearDown = http_fixture.GrantTests.tearDown

    def test_actual_http_route_module_and_query_rejection(self):
        base = self.origin + "/api/apps/sample-one/workflow-telemetry"
        with urlopen(base) as response:
            self.assertEqual(json.load(response)["runs"], [])
        with self.assertRaises(HTTPError):
            urlopen(base + "?app=sample-two")
        with urlopen(self.origin + "/workflow-telemetry.js") as response:
            self.assertIn(b"WMMTelemetry", response.read())
        with urlopen(self.origin) as response:
            self.assertIn(b"/workflow-telemetry.js", response.read())
