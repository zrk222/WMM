"""Owner-authored rule sets are immutable versions; saving does not evaluate."""

from pathlib import Path
import sqlite3
import tempfile
import unittest

from mission_control.automation_rules import validate
from mission_control.automation_store import current, history, save, version_index
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.store import Store

ROOT = Path(__file__).resolve().parents[1]
OWNER = {"principal": "github:1", "login": "owner"}
APP = "sample-one"


class AutomationStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name) / "state.sqlite", seed=False)
        self.store.save_app(
            APP,
            dict(
                name="Synthetic app",
                release="build-1",
                job="Synthetic job",
                audience="Synthetic audience",
                activation="Synthetic value",
                locale="en-US",
            ),
        )
        Access(self.store).bootstrap(APP, OWNER, {"confirm_owner": True})
        self.document = {
            "schema": "wmm.automation-rules.v1",
            "mode": "PROPOSE_ONLY",
            "timezone": "UTC",
            "rules": [
                {
                    "id": "one",
                    "enabled": True,
                    "priority": 1,
                    "when": {"fact": "app.release", "op": "eq", "value": "build-1"},
                    "then": {
                        "propose": {"action": "review", "tool": "reports.read", "reason": "ready"},
                        "requires": ["OWNER_REVIEW"],
                    },
                }
            ],
        }

    def test_save_is_versioned_and_does_not_evaluate(self):
        first = save(self.store, APP, OWNER, self.document)
        self.assertEqual(first["version"], 1)
        self.assertEqual(current(self.store, APP, OWNER["principal"])["hash"], first["hash"])
        second = save(self.store, APP, OWNER, self.document)
        self.assertEqual(second["version"], 2)
        self.assertEqual([row["version"] for row in history(self.store, APP, OWNER["principal"])], [2, 1])

    def test_loaded_legacy_rows_round_trip_and_remain_immutable(self):
        first = save(self.store, APP, OWNER, self.document)
        self.assertEqual(validate(first["document"]), validate(self.document))
        with connection(self.store.path) as db:
            for command in ("UPDATE automation_rule_sets SET version=2", "DELETE FROM automation_rule_sets"):
                with self.assertRaises(sqlite3.IntegrityError):
                    db.execute(command)
        self.assertEqual(current(self.store, APP, OWNER["principal"]), first)

    def test_index_pages_without_returning_full_rule_documents(self):
        for _ in range(27):
            save(self.store, APP, OWNER, self.document)
        first = version_index(self.store, APP, OWNER["principal"])
        self.assertEqual([row["version"] for row in first["versions"]], list(range(27, 2, -1)))
        self.assertEqual(first["next_before"], 3)
        older = version_index(self.store, APP, OWNER["principal"], first["next_before"])
        self.assertEqual([row["version"] for row in older["versions"]], [2, 1])
        self.assertIsNone(older["next_before"])
        self.assertTrue(all("document" not in row for row in first["versions"] + older["versions"]))

    def test_invalid_document_and_identity_reject(self):
        with self.assertRaises(Invalid):
            save(self.store, APP, OWNER, {"schema": "wrong"})
        with self.assertRaises(PermissionError):
            save(self.store, APP, {}, self.document)
        with self.assertRaises(PermissionError):
            save(self.store, "other-app", OWNER, self.document)

    def test_inactive_role_denies_read_and_write(self):
        save(self.store, APP, OWNER, self.document)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE operator_roles SET status='REVOKED' WHERE app_id=? AND principal=?", (APP, OWNER["principal"])
            )
        for operation in (current, history):
            with self.assertRaises(PermissionError):
                operation(self.store, APP, OWNER["principal"])
        with self.assertRaises(PermissionError):
            save(self.store, APP, OWNER, self.document)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM automation_rule_sets").fetchone()[0], 1)

    def test_stale_session_rolls_back_rule_and_audit(self):
        def replaced():
            raise PermissionError("session changed")

        with self.assertRaises(PermissionError):
            save(self.store, APP, OWNER, self.document, commit_check=replaced)
        self.assertIsNone(current(self.store, APP, OWNER["principal"]))
        with connection(self.store.path) as db:
            self.assertIsNone(
                db.execute(
                    "SELECT 1 FROM audit WHERE app_id=? AND action=?", (APP, "automation.rules.saved")
                ).fetchone()
            )
