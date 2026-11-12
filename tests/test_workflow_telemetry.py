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
from mission_control.workflow_telemetry import emit, monitor, worker_observation
from tests import test_agent_grants as http_fixture


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite", seed=False)
        for name in ("sample-one", "sample-two"):
            self.store.save_app(name, dict(name="Synthetic telemetry", release="1", locale="en-US"))

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
        self.assertEqual(monitor(Store(self.store.path, seed=False), "sample-one")["runs"][0], run)

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

    def test_monitor_times_only_retained_current_attempt_events(self):
        job = enqueue(self.store, "sample-one", "pipeline", {}, "timed-attempt")
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET created=?,status='SUCCEEDED',attempts=1 WHERE id=?",
                ("2026-11-11T14:00:00+00:00", job["id"]),
            )
            for attempt, code, at in (
                (1, "STARTED", "2026-11-11T14:00:03+00:00"),
                (1, "SUCCEEDED", "2026-11-11T14:00:08+00:00"),
            ):
                db.execute(
                    "INSERT INTO workflow_events(app_id,job_id,attempt,code,observed_at) VALUES(?,?,?,?,?)",
                    ("sample-one", job["id"], attempt, code, at),
                )
        self.assertEqual(
            monitor(self.store, "sample-one")["runs"][0]["timing"], {"initial_queue_ms": 3000, "attempt_ms": 5000}
        )
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET attempts=2,status='RUNNING' WHERE id=?", (job["id"],))
        self.assertEqual(monitor(self.store, "sample-one")["runs"][0]["timing"], {})
        with connection(self.store.path) as db:
            for code, at in (
                ("STARTED", "2026-11-11T14:01:00+00:00"),
                ("RETRY_WAIT", "2026-11-11T14:01:01.500+00:00"),
            ):
                db.execute(
                    "INSERT INTO workflow_events(app_id,job_id,attempt,code,observed_at) VALUES(?,?,?,?,?)",
                    ("sample-one", job["id"], 2, code, at),
                )
        self.assertEqual(monitor(self.store, "sample-one")["runs"][0]["timing"], {"attempt_ms": 1500})
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE workflow_events SET observed_at='2026-11-11T13:59:59+00:00' "
                "WHERE job_id=? AND code='RETRY_WAIT'",
                (job["id"],),
            )
        self.assertEqual(monitor(self.store, "sample-one")["runs"][0]["timing"], {})

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

    def test_waiting_outcome_is_allowlisted_private_and_stable(self):
        job = enqueue(self.store, "sample-one", "pipeline", {"secret": "PRIVATE_INPUT"}, "waiting")
        enqueue(self.store, "sample-two", "pipeline", {}, "foreign")
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET action='sync',status='SUCCEEDED',result=? WHERE id=?",
                (
                    json.dumps({"status": "WAITING_FOR_REPORTS", "error": "PRIVATE_ERROR", "token": "PRIVATE_TOKEN"}),
                    job["id"],
                ),
            )
        run = monitor(self.store, "sample-one")["runs"][0]
        self.assertEqual(run["outcome_code"], "WAITING_FOR_REPORTS")
        self.assertEqual(run["status"], "SUCCEEDED")
        self.assertNotIn("result", run)
        self.assertNotIn("PRIVATE_", json.dumps(run))
        self.assertEqual(monitor(Store(self.store.path, seed=False), "sample-one")["runs"][0], run)
        foreign = monitor(self.store, "sample-two")["runs"]
        self.assertEqual(len(foreign), 1)
        self.assertNotIn("outcome_code", foreign[0])
        self.assertNotEqual(foreign[0]["id"], job["id"])

    def test_outcome_ignores_untrusted_results_and_wrong_job_state(self):
        job = enqueue(self.store, "sample-one", "pipeline", {}, "untrusted")
        cases = [
            ("sync", "SUCCEEDED", None),
            ("sync", "SUCCEEDED", "{PRIVATE_MALFORMED"),
            ("sync", "SUCCEEDED", "[" * 2000 + "0" + "]" * 2000),
            ("sync", "SUCCEEDED", json.dumps([{"status": "WAITING_FOR_REPORTS"}])),
            ("sync", "SUCCEEDED", json.dumps("WAITING_FOR_REPORTS")),
            ("sync", "SUCCEEDED", json.dumps({"status": "PRIVATE_UNKNOWN", "error": "PRIVATE_ERROR"})),
            ("pipeline", "SUCCEEDED", json.dumps({"status": "WAITING_FOR_REPORTS"})),
            ("sync", "RUNNING", json.dumps({"status": "WAITING_FOR_REPORTS"})),
            ("sync", "FAILED", json.dumps({"status": "WAITING_FOR_REPORTS"})),
        ]
        for action, status, result in cases:
            with self.subTest(action=action, status=status, result=result):
                with connection(self.store.path) as db:
                    db.execute(
                        "UPDATE jobs SET action=?,status=?,result=? WHERE id=?", (action, status, result, job["id"])
                    )
                run = monitor(self.store, "sample-one")["runs"][0]
                self.assertEqual(run["status"], status)
                self.assertNotIn("outcome_code", run)
                self.assertNotIn("result", run)
                self.assertNotIn("PRIVATE_", json.dumps(run))


class TelemetryHTTPTests(unittest.TestCase):
    setUp = http_fixture.GrantTests.setUp
    tearDown = http_fixture.GrantTests.tearDown

    def test_actual_http_route_module_and_query_rejection(self):
        base = self.origin + "/api/apps/sample-one/workflow-telemetry"
        with urlopen(base) as response:
            initial = json.load(response)
        self.assertEqual(initial["runs"], [])
        self.assertEqual(initial["worker"], {"status": "STARTING", "last_success": None, "runtime_mode": "SERVER"})
        worker = self.server.runner.supervision
        worker.attempt("queue", lambda: 1 / 0)
        worker.finish()
        with urlopen(base) as response:
            self.assertEqual(
                json.load(response)["worker"], {"status": "RECOVERING", "last_success": None, "runtime_mode": "SERVER"}
            )
        worker.stopped()
        with urlopen(base) as response:
            self.assertEqual(
                json.load(response)["worker"], {"status": "STOPPED", "last_success": None, "runtime_mode": "SERVER"}
            )
        self.assertEqual(
            worker_observation(
                {
                    "status": "PRIVATE_STATUS",
                    "last_success": "PRIVATE_DATE",
                    "last_error": "PRIVATE_ERROR",
                    "runtime_mode": "PRIVATE_MODE",
                }
            ),
            {"status": "UNKNOWN", "last_success": None, "runtime_mode": "UNKNOWN"},
        )
        self.assertEqual(
            worker_observation({"status": "RUNNING", "last_success": "2026-11-06T00:00:00Z"}),
            {"status": "RUNNING", "last_success": "2026-11-06T00:00:00+00:00", "runtime_mode": "UNKNOWN"},
        )
        job = enqueue(self.store, "sample-one", "sync", {}, "http-waiting")
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='SUCCEEDED',result=? WHERE id=?",
                (json.dumps({"status": "WAITING_FOR_REPORTS", "token": "PRIVATE_HTTP_TOKEN"}), job["id"]),
            )
        with urlopen(base) as response:
            body = response.read().decode()
            self.assertEqual(json.loads(body)["runs"][0]["outcome_code"], "WAITING_FOR_REPORTS")
            self.assertNotIn("PRIVATE_HTTP_TOKEN", body)
            self.assertNotIn('"result"', body)
        with self.assertRaises(HTTPError):
            urlopen(base + "?app=sample-two")
        with urlopen(self.origin + "/workflow-telemetry.js") as response:
            self.assertIn(b"WMMTelemetry", response.read())
        with urlopen(self.origin) as response:
            self.assertIn(b"/workflow-telemetry.js", response.read())
