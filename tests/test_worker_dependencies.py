"""Owner-admitted prerequisites use the same atomic shared worker queue."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Any
from unittest.mock import patch

from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.server import Server
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import claim, enqueue, jobs, persist_job_result

APP = "sample-one"
OTHER = "sample-two"


class Owner:
    def local(self, session: str, principal: str, generation: str | None = None) -> dict[str, str]:
        assert (session, principal) == ("local-session", "owner")
        assert generation in (None, "generation")
        return {"session_generation": "generation"}


class WorkerDependenciesTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "wmm.sqlite")
        self.service = Service(self.store)
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)",
                (APP, "owner", "owner", "OWNER", "ACTIVE", 1, now(), "fixture"),
            )

    def owner_queue(self, key: str, dependencies: list[str]) -> dict[str, Any]:
        body = dict(action="pipeline", data=dict(stage=2), request_key=key, depends_on_jobs=dependencies)
        envelope = dict(app_id=APP, operation="job.dependencies.admit", input=body)
        with (
            bound_owner(self.store, envelope, Owner(), "local-session", dict(principal="owner")),
            protected(self.store, envelope),
        ):
            return self.service.queue(APP, body)

    def test_independent_job_can_run_while_dependent_waits_and_claims_once_after_restart(self) -> None:
        first = enqueue(self.store, APP, "pipeline", dict(stage=1), "first")
        dependent = self.owner_queue("dependent", [first["id"]])
        independent = enqueue(self.store, APP, "pipeline", dict(stage=3), "independent")
        self.assertEqual(dependent["dependency_status"], "WAITING_FOR_DEPENDENCIES")
        self.assertNotIn("dependency_status", independent)
        first_lease = claim(self.store)
        assert first_lease is not None
        self.assertEqual(first_lease["id"], first["id"])
        independent_lease = claim(self.store)
        assert independent_lease is not None
        self.assertEqual(independent_lease["id"], independent["id"])
        self.assertIsNone(claim(self.store))

        evidence = {"source": "verified prerequisite"}
        persist_job_result(self.store, first_lease, evidence, "SUCCEEDED", 0)
        restarted = Store(self.store.path)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _number: claim(restarted), (1, 2)))
        ready = [item for item in claims if item is not None]
        self.assertEqual([item["id"] for item in ready], [dependent["id"]])
        with connection(self.store.path) as db:
            saved = db.execute(
                "SELECT claimed_receipts,claimed_receipts_sha256 FROM worker_job_dependencies WHERE job_id=?",
                (dependent["id"],),
            ).fetchone()
        assert saved is not None
        receipts = [{"job_id": first["id"], "status": "SUCCEEDED", "result_hash": digest(evidence)}]
        self.assertEqual(saved["claimed_receipts"], canonical(receipts))
        self.assertEqual(saved["claimed_receipts_sha256"], digest(receipts))

    def test_scope_and_replay_keep_predecessors_immutable(self) -> None:
        a = enqueue(self.store, APP, "pipeline", {}, "first")
        b = enqueue(self.store, APP, "pipeline", {}, "second")
        foreign = enqueue(self.store, OTHER, "pipeline", {}, "foreign")
        initial = self.owner_queue("workflow", [a["id"], b["id"]])
        self.assertEqual(self.owner_queue("workflow", [b["id"], a["id"]])["id"], initial["id"])
        for key, dependencies in (
            ("workflow", [a["id"]]),
            ("workflow", [initial["id"]]),
            ("foreign", [foreign["id"]]),
            ("duplicate", [a["id"], a["id"]]),
            ("old-job", [a["id"]]),
        ):
            if key == "old-job":
                enqueue(self.store, APP, "pipeline", dict(stage=2), key)
            with self.subTest(key=key), self.assertRaises(Invalid):
                self.owner_queue(key, dependencies)
        with self.assertRaises(PermissionError):
            enqueue(self.store, APP, "pipeline", {}, "unowned", depends_on_jobs=[a["id"]])
        self.assertEqual(
            {job["request_key"] for job in jobs(self.store, APP)}, {"first", "second", "workflow", "old-job"}
        )

    def test_failed_uncertain_or_changed_prerequisite_is_blocked_without_one_attempt(self) -> None:
        cases = [
            ("FAILED", {"error": "Failed read"}, "FAILED"),
            ("SUCCEEDED", {"status": "RECONCILE_REQUIRED"}, "UNVERIFIED_RESULT"),
            ("SUCCEEDED", {"external_execution": "UNKNOWN"}, "UNVERIFIED_RESULT"),
            ("SUCCEEDED", None, "MISSING_RESULT"),
            ("SUCCEEDED", {"observed": True}, "CHANGED"),
        ]
        expected = {}
        for index, (status, result, receipt_status) in enumerate(cases):
            first = enqueue(self.store, APP, "pipeline", {}, f"parent-{index}")
            child = self.owner_queue(f"child-{index}", [first["id"]])
            expected[child["id"]] = receipt_status
            with connection(self.store.path) as db:
                db.execute("UPDATE jobs SET status=?,result=? WHERE id=?", (status, canonical(result), first["id"]))
                if receipt_status == "CHANGED":
                    db.execute("UPDATE jobs SET data=? WHERE id=?", (canonical({"stage": 1}), first["id"]))
        independent = enqueue(self.store, APP, "pipeline", {}, "independent")
        leased = claim(self.store)
        assert leased is not None
        self.assertEqual(leased["id"], independent["id"])
        for child in (job for job in jobs(self.store, APP) if job["id"] in expected):
            self.assertEqual(child["status"], "BLOCKED")
            self.assertEqual(child["attempts"], 0)
            self.assertEqual(child["dependency_receipts"][0]["status"], expected[child["id"]])
            self.assertIn("reconcile uncertain effects", child["result"]["next_action"])

    def test_owner_version_change_blocks_waiting_job(self) -> None:
        first = enqueue(self.store, APP, "pipeline", {}, "first")
        dependent = self.owner_queue("dependent", [first["id"]])
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET version=2 WHERE app_id=? AND principal='owner'", (APP,))
            db.execute(
                "UPDATE jobs SET status='SUCCEEDED',result=? WHERE id=?",
                (canonical({"source": "verified"}), first["id"]),
            )
        self.assertIsNone(claim(self.store))
        row = next(job for job in jobs(self.store, APP) if job["id"] == dependent["id"])
        self.assertEqual(row["status"], "BLOCKED")
        self.assertEqual(row["dependency_receipts"][-1]["status"], "OWNER_SCOPE_CHANGED")

    def test_expired_lease_cannot_resume_under_a_changed_result_receipt(self) -> None:
        first = enqueue(self.store, APP, "pipeline", {}, "first")
        dependent = self.owner_queue("dependent", [first["id"]])
        first_lease = claim(self.store)
        assert first_lease is not None
        persist_job_result(self.store, first_lease, dict(source="first"), "SUCCEEDED", 0)
        leased = claim(self.store)
        assert leased is not None
        self.assertEqual(leased["id"], dependent["id"])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=0 WHERE id=?", (dependent["id"],))
            db.execute("UPDATE jobs SET result=? WHERE id=?", (canonical(dict(source="changed")), first["id"]))
        self.assertIsNone(claim(self.store))
        saved = next(job for job in jobs(self.store, APP) if job["id"] == dependent["id"])
        self.assertEqual(saved["attempts"], 1)
        self.assertEqual(saved["status"], "BLOCKED")
        self.assertEqual(saved["dependency_receipts"][-1]["status"], "CLAIMED_RECEIPTS_CHANGED")

    def test_job_endpoint_admits_prerequisites_only_for_the_current_owner(self) -> None:
        server = Server(("127.0.0.1", 0), self.store)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        path = f"/api/apps/{APP}/jobs"
        owner = OperatorClient(f"http://127.0.0.1:{server.server_port}")
        owner.bootstrap()
        first = owner.request("POST", path, dict(action="pipeline", data={}, request_key="legacy"))
        assert isinstance(first, dict)
        self.assertNotIn("dependency_status", first)
        body = dict(action="pipeline", data={}, request_key="owner", depends_on_jobs=[first["id"]])
        with self.assertRaises(ClientError) as anonymous:
            owner.request("POST", path, body)
        self.assertEqual(anonymous.exception.status, 403)
        identity = dict(principal="owner", login="owner", provider="GITHUB", verified_at=now())
        with patch("mission_control.operator_identity.github_read", return_value=identity):
            owner.request("POST", "/api/identity/login", {"token": "synthetic_owner_identity_token"})
            admitted = owner.request("POST", path, body)
            assert isinstance(admitted, dict)
            self.assertEqual(admitted["depends_on_jobs"], [first["id"]])
            self.assertEqual(admitted["dependency_status"], "WAITING_FOR_DEPENDENCIES")
            denied = dict(body, depends_on_jobs=[])
            with self.assertRaises(ClientError) as replay:
                owner.request("POST", path, denied)
            self.assertEqual(replay.exception.status, 400)
