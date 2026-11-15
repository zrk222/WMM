"""Status-only job history and owner-only scheduled report controls."""

import unittest

from mission_control import campaign_owner_reports as core
from mission_control.common import canonical, digest
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.worker import run_once
from tests import test_campaign_owner_reports as fixtures


class PrivateReportJobBoundaryTests(unittest.TestCase):
    def test_campaign_run_must_use_its_owner_stop_control(self) -> None:
        fixture = fixtures.CampaignOwnerReportsTests(
            "test_finite_plan_hash_activation_tick_restart_and_local_job_idempotency"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        origin = fixture.fixture.client.origin
        ordinary = OperatorClient(origin)
        ordinary.bootstrap()

        created = "2026-01-01T00:00:00+00:00"
        for action in ("campaign_post", "campaign_ad", "campaign_monitor"):
            for status in ("QUEUED", "RUNNING"):
                with self.subTest(action=action, status=status):
                    job_id = f"{action}-{status}"
                    with connection(fixture.store.path) as db:
                        db.execute(
                            """INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key)
                            VALUES(?, 'sample', ?, '{}', ?, ?, ?, ?)""",
                            (job_id, action, status, created, created, job_id),
                        )
                    with self.assertRaises(ClientError) as denied:
                        ordinary.request("POST", f"/api/apps/sample/jobs/{job_id}/cancel", {})
                    self.assertEqual(denied.exception.status, 403)
                    self.assertEqual(denied.exception.code, "ACCESS_DENIED")
                    with connection(fixture.store.path) as db:
                        row = db.execute("SELECT status,updated FROM jobs WHERE id=?", (job_id,)).fetchone()
                    self.assertEqual(tuple(row), (status, created))

    def test_scheduled_report_remains_private_across_worker_and_http_reads(self) -> None:
        fixture = fixtures.CampaignOwnerReportsTests(
            "test_finite_plan_hash_activation_tick_restart_and_local_job_idempotency"
        )
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)

        app = "/api/apps/sample"
        owner = fixture.fixture.client
        anonymous = OperatorClient(owner.origin)
        anonymous.bootstrap()
        plan = fixture.plan()
        self.assertEqual(core.tick(fixture.store), 1)
        with fixture.owner():
            first_id = fixture.reports.status("sample", plan["id"])["last_job"]
        with self.assertRaises(ClientError) as denied:
            anonymous.request("POST", f"{app}/jobs/{first_id}/cancel", {})
        self.assertEqual(denied.exception.status, 403)

        self.assertTrue(run_once(fixture.store))
        report_route = app + "/campaign-owner-reports"
        history = owner.request("POST", report_route + "/history", {})
        assert isinstance(history, dict)
        self.assertEqual(len(history["reports"]), 1)
        saved = history["reports"][0]
        self.assertEqual(saved["plan_id"], plan["id"])
        self.assertEqual(saved["report"]["selection"], fixture.chosen())
        self.assertEqual(owner.request("POST", report_route + "/read", {"report_id": saved["id"]}), saved)
        self.assertEqual(saved["hash"], digest(saved["report"]))

        legacy_result = canonical(saved)
        with connection(fixture.store.path) as db:
            row = db.execute("SELECT status,result,request_key FROM jobs WHERE id=?", (first_id,)).fetchone()
            self.assertEqual(row["status"], "SUCCEEDED")
            self.assertEqual(row["result"], canonical({"status": "PRIVATE_REPORT_SAVED"}))
            self.assertIn(plan["id"], row["request_key"])
            db.execute("UPDATE jobs SET result=? WHERE id=?", (legacy_result, first_id))
            db.execute("UPDATE campaign_report_plans SET due=0 WHERE id=?", (plan["id"],))

        job_history = anonymous.request("GET", app + "/jobs")
        workspace = anonymous.request("GET", app)
        assert isinstance(workspace, dict)
        for rows in (job_history, workspace["jobs"]):
            assert isinstance(rows, list)
            row = next(job for job in rows if job["id"] == first_id)
            self.assertEqual(row["action"], "campaign_owner_report")
            self.assertEqual(row["status"], "SUCCEEDED")
            self.assertEqual(row["data"], {})
            self.assertIsNone(row["result"])
            self.assertEqual(
                set(row), {"id", "app_id", "action", "status", "created", "updated", "attempts", "data", "result"}
            )
        with connection(fixture.store.path) as db:
            self.assertEqual(db.execute("SELECT result FROM jobs WHERE id=?", (first_id,)).fetchone()[0], legacy_result)

        self.assertEqual(core.tick(fixture.store), 1)
        plan_status = owner.request("POST", report_route + "/status", {"plan_id": plan["id"]})
        assert isinstance(plan_status, dict)
        second_id = plan_status["last_job"]
        self.assertNotEqual(second_id, first_id)
        stopped = owner.request(
            "POST", report_route + "/off", {"plan_id": plan["id"], "version": plan_status["version"]}
        )
        assert isinstance(stopped, dict)
        self.assertEqual(stopped["status"], "OFF")
        cancelled_history = anonymous.request("GET", app + "/jobs")
        assert isinstance(cancelled_history, list)
        second = next(job for job in cancelled_history if job["id"] == second_id)
        self.assertEqual(second["status"], "CANCELLED")
        self.assertEqual(owner.request("POST", report_route + "/read", {"report_id": saved["id"]}), saved)
