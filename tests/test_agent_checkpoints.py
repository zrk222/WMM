"""Synthetic trusted-adapter lifecycle tests; these do not prove real human presence."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.agent_checkpoints import Checkpoints, hashed, packet_data, read_row, persist
from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store


class AgentCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "source.sqlite")
        self.observed = datetime.fromisoformat("2026-10-23T12:00:00+00:00")
        self.work = Checkpoints(self.store, lambda: self.observed)
        self.owner = dict(principal="github:1", login="owner")
        self.maker = dict(principal="github:2", login="maker")
        self.checker = dict(principal="github:3", login="checker")
        self.access = Access(self.store)
        self.access.bootstrap("sample-one", self.owner, {"confirm_owner": True})
        for user, role in ((self.maker, "MAKER"), (self.checker, "CHECKER")):
            self.access.save("sample-one", self.owner, user, dict(login=user["login"], role=role, status="ACTIVE", version=None))
        self.body = dict(id="run-one", agent_id="agent-one", operation="PREPARE_DRAFT", input_hash=digest({"synthetic": True}),
                         manifest_version=self.store.app("sample-one")["version"], expires=(self.observed + timedelta(hours=1)).isoformat())

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self):
        return self.work.prepare("sample-one", self.maker["principal"], self.body)

    def approve(self):
        row = self.prepare()
        return self.work.approve("sample-one", "run-one", self.checker["principal"], row["revision"], row["hash"])

    def claim(self):
        row = self.approve()
        return self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])

    def test_checkpoint_packet_immutable_replay_and_scope(self):
        row = self.prepare()
        self.assertEqual(row, self.prepare())
        with self.assertRaises(Invalid):
            self.work.prepare("sample-one", self.maker["principal"], dict(self.body, input_hash="a" * 64))
        with self.assertRaises((Invalid, PermissionError)):
            self.work.prepare("sample-two", self.maker["principal"], self.body)
        with self.assertRaises(Invalid):
            self.work.inspect("sample-two", "run-one")
        self.assertEqual(row["state"], "WAITING_REVIEW")
        self.assertEqual(row["hash"], digest(row["packet"]))

    def test_distinct_checker_hash_role_and_revision(self):
        row = self.prepare()
        cases = ((self.maker["principal"], row["revision"], row["hash"]),
                 (self.checker["principal"], None, row["hash"]),
                 (self.checker["principal"], True, row["hash"]),
                 (self.checker["principal"], row["revision"], "b" * 64))
        for actor, revision, hashed_value in cases:
            with self.assertRaises((Invalid, PermissionError)):
                self.work.approve("sample-one", "run-one", actor, revision, hashed_value)
        self.assertEqual(self.work.inspect("sample-one", "run-one")["state"], "WAITING_REVIEW")
        self.assertEqual(self.work.approve("sample-one", "run-one", self.checker["principal"], row["revision"], row["hash"])["state"], "APPROVED")

    def test_owner_cannot_self_approve_even_with_both_capabilities(self):
        row = self.work.prepare("sample-one", self.owner["principal"], self.body)
        with self.assertRaises(Invalid):
            self.work.approve("sample-one", "run-one", self.owner["principal"], row["revision"], row["hash"])

    def test_single_claim_concurrent_and_wrong_agent(self):
        row = self.approve()
        with self.assertRaises(Invalid):
            self.work.claim("sample-one", "run-one", "agent-other", row["revision"], row["hash"])
        def attempt(_):
            try:
                self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
                return True
            except Invalid:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, range(2))), [False, True])

    def test_durable_recovery_and_unknown_reconciliation(self):
        row = self.claim()
        restarted = Checkpoints(Store(self.store.path), lambda: self.observed)
        view = restarted.inspect("sample-one", "run-one")
        self.assertTrue(view["reconciliation_required"])
        self.assertFalse(view["claim_available"])
        with self.assertRaises(Invalid):
            restarted.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
        row = restarted.finish("sample-one", "run-one", "agent-one", row["revision"], "UNKNOWN", "c" * 64)
        with self.assertRaises((Invalid, PermissionError)):
            restarted.reconcile("sample-one", "run-one", self.maker["principal"], row["revision"], "SUCCEEDED", "d" * 64)
        row = restarted.reconcile("sample-one", "run-one", self.checker["principal"], row["revision"], "SUCCEEDED", "d" * 64)
        self.assertEqual(row["state"], "SUCCEEDED")
        self.assertFalse(restarted.inspect("sample-one", "run-one")["claim_available"])

    def test_stale_authority_expiry_and_manifest(self):
        row = self.approve()
        self.observed += timedelta(hours=1)
        with self.assertRaises(Invalid):
            self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
        self.observed -= timedelta(hours=1)
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", app["data"], app["version"])
        with self.assertRaises(Invalid):
            self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])

    def test_stale_authority_role_revocation_and_reactivation(self):
        row = self.approve()
        for status, version in (("REVOKED", 1), ("ACTIVE", 2)):
            self.access.save("sample-one", self.owner, self.checker, dict(login="checker", role="CHECKER", status=status, version=version))
            with self.assertRaises((Invalid, PermissionError)):
                self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
        self.assertFalse(self.work.inspect("sample-one", "run-one")["claim_available"])

    def test_cancel_before_claim_and_after_claim_never_assumes_stop(self):
        row = self.approve()
        row = self.work.cancel("sample-one", "run-one", self.maker["principal"], row["revision"])
        self.assertEqual(row["state"], "CANCELLED")
        with self.assertRaises(Invalid):
            self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
        self.body["id"] = "run-two"
        row = self.work.prepare("sample-one", self.maker["principal"], self.body)
        row = self.work.approve("sample-one", "run-two", self.checker["principal"], row["revision"], row["hash"])
        row = self.work.claim("sample-one", "run-two", "agent-one", row["revision"], row["hash"])
        row = self.work.cancel("sample-one", "run-two", self.owner["principal"], row["revision"])
        self.assertEqual(row["state"], "CANCEL_REQUESTED")
        with self.assertRaises(Invalid):
            self.work.finish("sample-one", "run-two", "agent-one", row["revision"], "SUCCEEDED", "c" * 64)
        self.assertTrue(self.work.inspect("sample-one", "run-two")["reconciliation_required"])

    def test_checkpoint_history_receipts_and_no_automatic_retry(self):
        row = self.claim()
        self.observed += timedelta(days=1)
        row = self.work.finish("sample-one", "run-one", "agent-one", row["revision"], "FAILED", "c" * 64)
        previous = None
        for event in row["history"]:
            data = {key: value for key, value in event.items() if key != "hash"}
            self.assertEqual(event["hash"], digest(data))
            self.assertEqual(event["previous_hash"], previous)
            previous = event["hash"]
        with self.assertRaises(Invalid):
            self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
        self.assertEqual(Checkpoints(Store(self.store.path)).inspect("sample-one", "run-one")["history"], row["history"])

    def test_validation_excludes_effects_credentials_and_malformed_fields(self):
        for change in (dict(operation="PUBLISH"), dict(operation="SPEND"), dict(token="secret"),
                       dict(input_hash="BAD"), dict(manifest_version=True), dict(expires=self.observed.isoformat()),
                       dict(expires=(self.observed + timedelta(days=2)).isoformat())):
            with self.assertRaises(Invalid):
                self.work.prepare("sample-one", self.maker["principal"], dict(self.body, **change))
        with self.assertRaises(Invalid):
            hashed(True)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM agent_checkpoints").fetchone()[0], 0)

    def test_no_network_or_provider_dispatch(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            row = self.claim()
            row = self.work.finish("sample-one", "run-one", "agent-one", row["revision"], "SUCCEEDED", "e" * 64)
        self.assertEqual(row["state"], "SUCCEEDED")

    def test_snapshot_never_exports_checkpoint_authority(self):
        self.approve()
        snapshot = self.store.export("sample-one")
        self.assertNotIn("agent_checkpoints", snapshot["payload"])
        self.assertNotIn(self.body["input_hash"], str(snapshot))

    def test_maker_revocation_denies_claim_and_failed_mutation_preserves_history(self):
        row = self.approve()
        self.access.save("sample-one", self.owner, self.maker, dict(login="maker", role="MAKER", status="REVOKED", version=1))
        with self.assertRaises(PermissionError):
            self.work.claim("sample-one", "run-one", "agent-one", row["revision"], row["hash"])
        self.assertEqual(self.work.inspect("sample-one", "run-one")["history"], row["history"])

    def test_packet_data_read_row_and_persist_transaction_rollback(self):
        row = self.prepare()
        with self.assertRaises(RuntimeError):
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                self.assertEqual(packet_data(db, "sample-one", self.maker["principal"], self.body, self.observed), row["packet"])
                stored = read_row(db, "sample-one", "run-one", row["revision"])
                persist(db, stored, "CANCELLED", self.owner["principal"], self.observed)
                raise RuntimeError("Synthetic crash before commit")
        self.assertEqual(self.work.inspect("sample-one", "run-one")["history"], row["history"])
