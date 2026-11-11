from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch

from mission_control import db


class WorkspaceSchemaMigrationsTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "workspace.sqlite3"

    def ledger(self):
        with db.session(self.path) as conn:
            return [tuple(row) for row in conn.execute("SELECT version,name FROM workspace_schema_migrations")]

    def test_fresh_and_reopen_run_migration_once(self):
        db.initialize(self.path)
        self.assertEqual(self.ledger(), [(1, "normalize_legacy_workspace")])
        with patch.object(db, "_WORKSPACE_MIGRATIONS", ((1, "normalize_legacy_workspace", self.fail),)):
            db.initialize(self.path)
        self.assertEqual(self.ledger(), [(1, "normalize_legacy_workspace")])

    def test_legacy_upgrade_preserves_authority_receipt_and_guards(self):
        db.initialize(self.path)
        with closing(sqlite3.connect(self.path)) as conn, conn:
            conn.execute("DROP TABLE workspace_schema_migrations")
            conn.execute("DROP TABLE automation_execution_authority")
            conn.execute("""CREATE TABLE automation_execution_authority(
                execution_id TEXT PRIMARY KEY REFERENCES automation_executions(id),
                permission_expires_at TEXT NOT NULL,policy_revision INTEGER NOT NULL,
                policy_hash TEXT NOT NULL,grant_revision INTEGER NOT NULL,grant_hash TEXT NOT NULL,
                record_hash TEXT NOT NULL)""")
            conn.execute("ALTER TABLE authority_expiry_consents DROP COLUMN stable_hash")
            conn.execute("ALTER TABLE creative_batch_variants DROP COLUMN native_packet_hash")
            conn.execute("ALTER TABLE creative_batch_variants DROP COLUMN native_state")
            # Stand-in parent rows are inserted without fixture foreign key enforcement.
            conn.execute("INSERT INTO automation_executions VALUES (?,?,?,?,?,?,?,0,NULL,?,?)",
                         ("execution", "policy", 1, "grant", "op", "input", "DISPATCHED", "now", "now"))
            receipt = (17, "execution", "later", 1, "policy-proof", 1, "grant-proof", "record-proof")
            conn.execute("INSERT INTO automation_execution_authority(rowid,execution_id,permission_expires_at,"
                         "policy_revision,policy_hash,grant_revision,grant_hash,record_hash) "
                         "VALUES (?,?,?,?,?,?,?,?)", receipt)
        db.initialize(self.path)
        self.assertEqual(self.ledger(), [(1, "normalize_legacy_workspace")])
        with db.session(self.path) as conn:
            self.assertEqual(tuple(conn.execute("SELECT rowid,* FROM automation_execution_authority").fetchone()), receipt)
            self.assertIsNone(conn.execute("PRAGMA foreign_key_list(automation_execution_authority)").fetchone())
            self.assertIsNone(conn.execute("PRAGMA foreign_key_check(automation_execution_authority)").fetchone())
            self.assertEqual(conn.execute("SELECT id FROM automation_executions").fetchone()[0], "execution")
            for statement in (
                "UPDATE automation_execution_authority SET grant_revision=2",
                "DELETE FROM automation_execution_authority",
                "INSERT OR REPLACE INTO automation_execution_authority SELECT * FROM automation_execution_authority",
                "INSERT OR REPLACE INTO automation_execution_authority(rowid,execution_id,permission_expires_at,"
                "policy_revision,policy_hash,grant_revision,grant_hash,record_hash) "
                "SELECT rowid,'other',permission_expires_at,policy_revision,policy_hash,grant_revision,"
                "grant_hash,record_hash FROM automation_execution_authority",
            ):
                with self.subTest(statement=statement), self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    conn.execute(statement)
            expiry_columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(authority_expiry_consents)")}
            creative_columns = {row["name"]: row for row in conn.execute("PRAGMA table_info(creative_batch_variants)")}
            self.assertEqual(expiry_columns["stable_hash"]["dflt_value"], "''")
            self.assertEqual(creative_columns["native_state"]["dflt_value"], "'PREPARED'")
            self.assertEqual(creative_columns["native_packet_hash"]["notnull"], 0)

    def test_failure_rolls_back_bootstrap_and_ledger_and_retry_succeeds(self):
        def fail_after_repair(conn):
            db._normalize_legacy_workspace(conn)
            raise RuntimeError("injected after repair")

        with patch.object(db, "_WORKSPACE_MIGRATIONS", ((1, "normalize_legacy_workspace", fail_after_repair),)):
            with self.assertRaisesRegex(RuntimeError, "injected after repair"):
                db.initialize(self.path)
        with db.session(self.path) as conn:
            self.assertEqual(conn.execute("SELECT name FROM sqlite_master").fetchall(), [])
        db.initialize(self.path)
        self.assertEqual(self.ledger(), [(1, "normalize_legacy_workspace")])

    def test_future_and_wrong_name_are_rejected_before_bootstrap(self):
        for version, name in ((2, "future"), (1, "different")):
            with self.subTest(version=version, name=name):
                with closing(sqlite3.connect(self.path)) as conn, conn:
                    conn.execute("CREATE TABLE IF NOT EXISTS workspace_schema_migrations(version INTEGER PRIMARY KEY,"
                                 "name TEXT NOT NULL)")
                    conn.execute("DELETE FROM workspace_schema_migrations")
                    conn.execute("INSERT INTO workspace_schema_migrations VALUES (?,?)", (version, name))
                with self.assertRaisesRegex(RuntimeError, "Unsupported workspace schema version"):
                    db.initialize(self.path)
                with db.session(self.path) as conn:
                    self.assertEqual(conn.execute("SELECT name FROM sqlite_master").fetchone()[0],
                                     "workspace_schema_migrations")
                    self.assertEqual(conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0], 1)
                    self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "delete")
                self.assertEqual(self.ledger(), [(version, name)])

    def test_concurrent_first_start_records_one_receipt(self):
        barrier = Barrier(2)

        def initialize():
            barrier.wait(timeout=5)
            db.initialize(self.path)

        with ThreadPoolExecutor(max_workers=2) as executor:
            starters = [executor.submit(initialize) for _ in range(2)]
            for starter in starters:
                starter.result(timeout=20)
        self.assertEqual(self.ledger(), [(1, "normalize_legacy_workspace")])
