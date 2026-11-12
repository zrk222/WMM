import hashlib
import math
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from mission_control.hosted_read_control import Control, Unassigned, Unauthenticated


class Clock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


class ReadControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "control.sqlite"
        self.clock = Clock()
        self.control = Control(self.path, self.clock)
        self.control.register_client("tenant", "client")

    def member(self, subject="alice", role="VIEWER", client="client"):
        self.control.set_member("issuer", subject, "tenant", client, role)

    def finish(self, admission):
        return self.control.finish(admission, "app", hashlib.sha256(b"response").hexdigest(), "request-1")

    def test_all_roles_and_durable_session(self):
        for role in ("OWNER", "OPERATOR", "REVIEWER", "VIEWER"):
            with self.subTest(role=role):
                self.member(role, role)
                token = self.control.issue_session("issuer", role)
                reopened = Control(self.path, self.clock)
                admission = reopened.admit(token, "tenant", "client")
                self.assertEqual(admission.role, role)
                receipt_id = reopened.finish(admission, "app", "a" * 64, "request-1")
                receipt = reopened.receipts()[-1]
                self.assertEqual(
                    (receipt["id"], receipt["outcome"], receipt["projection_hash"]), (receipt_id, "ALLOWED", "a" * 64)
                )
                self.assertEqual(
                    (receipt["session_generation"], receipt["client_epoch"], receipt["member_epoch"]),
                    (admission.generation, admission.client_epoch, admission.member_epoch),
                )

    def test_subject_client_isolation_and_snapshots(self):
        self.control.register_client("tenant", "other")
        self.member()
        self.member("bob", client="other")
        alice = self.control.issue_session("issuer", "alice")
        bob = self.control.issue_session("issuer", "bob")
        for token, client in ((alice, "other"), (bob, "client")):
            with self.assertRaises(Unassigned):
                self.control.admit(token, "tenant", client)
        with self.assertRaises(Unassigned):
            self.control.admit(alice, "another", "client")
        self.member("alice", client="other")
        with self.assertRaises(Unassigned):
            self.control.admit(alice, "tenant", "other")
        self.control.admit(self.control.issue_session("issuer", "alice"), "tenant", "other")

    def test_membership_and_client_epoch_changes_never_resurrect(self):
        self.member()
        old = self.control.issue_session("issuer", "alice")
        self.control.set_member("issuer", "alice", "tenant", "client", "OWNER")
        with self.assertRaises(Unassigned):
            self.control.admit(old, "tenant", "client")
        newer = self.control.issue_session("issuer", "alice")
        self.control.set_member("issuer", "alice", "tenant", "client", "OWNER", "REVOKED")
        self.control.set_member("issuer", "alice", "tenant", "client", "OWNER")
        with self.assertRaises(Unassigned):
            self.control.admit(newer, "tenant", "client")
        current = self.control.issue_session("issuer", "alice")
        self.control.set_client("tenant", "client", "REVOKED")
        self.control.set_client("tenant", "client", "ACTIVE")
        with self.assertRaises(Unassigned):
            self.control.admit(current, "tenant", "client")

    def test_logout_idle_absolute_expiry_and_exact_boundary(self):
        self.member()
        token = self.control.issue_session("issuer", "alice")
        self.control.revoke_session(token)
        with self.assertRaises(Unauthenticated):
            Control(self.path, self.clock).admit(token, "tenant", "client")
        idle = self.control.issue_session("issuer", "alice")
        self.clock.value += 900
        with self.assertRaises(Unauthenticated):
            self.control.admit(idle, "tenant", "client")
        token = self.control.issue_session("issuer", "alice", max_age=1000)
        self.clock.value += 899
        self.finish(self.control.admit(token, "tenant", "client"))
        self.clock.value += 101
        with self.assertRaises(Unauthenticated):
            self.control.admit(token, "tenant", "client")

    def test_committed_revocation_before_finish_denies(self):
        self.member()
        token = self.control.issue_session("issuer", "alice")
        admission = self.control.admit(token, "tenant", "client")
        completed = threading.Event()

        def revoke():
            Control(self.path, self.clock).revoke_session(token)
            completed.set()

        thread = threading.Thread(target=revoke)
        thread.start()
        self.assertTrue(completed.wait(5))
        thread.join()
        with self.assertRaises(Unauthenticated):
            self.finish(admission)
        self.assertEqual(self.control.receipts(), [])

    def test_receipt_failure_rolls_back_idle_refresh(self):
        self.member()
        token = self.control.issue_session("issuer", "alice")
        admission = self.control.admit(token, "tenant", "client")
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT, 'failed'); END")
            db.commit()
        self.clock.value += 899
        with self.assertRaises(sqlite3.IntegrityError):
            self.finish(admission)
        self.clock.value += 1
        with self.assertRaises(Unauthenticated):
            self.control.admit(token, "tenant", "client")
        self.assertEqual(self.control.receipts(), [])

    def test_hash_only_and_denied_metadata(self):
        self.member()
        token = self.control.issue_session("issuer", "alice")
        self.finish(self.control.admit(token, "tenant", "client"))
        self.control.denied(token, "tenant", "client", "app", "arbitrary secret", "request-2")
        self.assertEqual(self.control.receipts()[-1]["reason"], "INVALID_REQUEST")
        self.assertIsNone(self.control.receipts()[-1]["session_generation"])
        with closing(sqlite3.connect(self.path)) as db:
            stored = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertEqual(stored, hashlib.sha256(token.encode()).digest())
        for path in Path(self.temp.name).iterdir():
            self.assertNotIn(token.encode(), path.read_bytes())
        self.assertNotIn(token, str(self.control.receipts()))
        if os.name != "nt":
            self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_missing_or_replaced_database_never_created(self):
        self.path.unlink()
        with self.assertRaises(sqlite3.Error):
            self.control.receipts()
        self.assertFalse(self.path.exists())
        self.path.write_bytes(b"replacement")
        with self.assertRaises(sqlite3.Error):
            self.control.receipts()

    def test_invalid_session_time_and_roles_fail_closed(self):
        self.member()
        for token in (None, "wmmr_bad", "x" * 48):
            with self.assertRaises(Unauthenticated):
                self.control.admit(token, "tenant", "client")
        for age in (0, -1, 28801, math.inf, math.nan, True):
            with self.assertRaises(ValueError):
                self.control.issue_session("issuer", "alice", age)
        with self.assertRaises(ValueError):
            self.member("bob", "ADMIN")
        self.clock.value = math.nan
        with self.assertRaises(ValueError):
            self.control.issue_session("issuer", "alice")

    def test_https_issuer_and_printable_subject(self):
        issuer, subject = "https://id.example/realm", "user@example.com/id"
        self.control.set_member(issuer, subject, "tenant", "client", "REVIEWER")
        admission = self.control.admit(self.control.issue_session(issuer, subject), "tenant", "client")
        self.assertEqual((admission.issuer, admission.subject), (issuer, subject))
        self.finish(admission)
        self.assertEqual(self.control.receipts()[-1]["issuer"], issuer)
        for invalid in ("bad\nissuer", "wmmr_secret", "a" * 201):
            with self.assertRaises(ValueError):
                self.control.set_member(invalid, subject, "tenant", "client", "VIEWER")

    def test_existing_receipts_migrate_without_losing_rows(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("DROP TABLE receipts")
            db.execute("""CREATE TABLE receipts (
                id TEXT PRIMARY KEY, outcome TEXT NOT NULL, reason TEXT NOT NULL,
                tenant_id TEXT NOT NULL, client_id TEXT NOT NULL, app_id TEXT NOT NULL,
                projection_hash TEXT NOT NULL, correlation TEXT NOT NULL,
                issuer TEXT NOT NULL, subject TEXT NOT NULL, role TEXT NOT NULL,
                created_at REAL NOT NULL)""")
            db.execute("INSERT INTO receipts VALUES ('old','DENIED','NOT_FOUND','t','c','a','','r','','','',1)")
            db.commit()
        reopened = Control(self.path, self.clock)
        old = reopened.receipts()[0]
        self.assertEqual((old["id"], old["reason"]), ("old", "NOT_FOUND"))
        self.assertIsNone(old["client_epoch"])
        self.member()
        self.finish(reopened.admit(reopened.issue_session("issuer", "alice"), "tenant", "client"))
        self.assertEqual(len(Control(self.path, self.clock).receipts()), 2)


if __name__ == "__main__":
    unittest.main()
