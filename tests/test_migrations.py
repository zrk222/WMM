"""The ordered migration ledger, its immutability and FK-index coverage."""

import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from mission_control import migrations
from mission_control.db import connection, initialize


class MigrationLedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state.sqlite"
        initialize(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ledger_records_contiguous_versions_and_declared_checksums(self):
        entries = migrations.discovered()
        self.assertEqual([version for version, _, _ in entries], list(range(1, len(entries) + 1)))
        with connection(self.path) as db:
            ledger = migrations.applied(db)
            self.assertEqual([row["version"] for row in ledger], [0, *range(1, len(entries) + 1)])
            self.assertEqual(ledger[0]["name"], "baseline")
            for (version, name, path), row in zip(entries, ledger[1:], strict=True):
                self.assertEqual((row["version"], row["name"]), (version, name))
                self.assertEqual(row["checksum"], sha256(path.read_bytes()).hexdigest())
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], entries[-1][0])

    def test_reinitializing_is_idempotent_and_schema_digest_is_stable(self):
        with connection(self.path) as db:
            before = migrations.schema_digest(db)
        initialize(self.path)
        with connection(self.path) as db:
            self.assertEqual(migrations.apply(db), [], "No migration should replay")
            self.assertEqual(migrations.schema_digest(db), before)

    def test_editing_an_applied_migration_fails_closed(self):
        with connection(self.path) as db:
            db.execute("UPDATE schema_migrations SET checksum=? WHERE version=1", ("0" * 64,))
        with self.assertRaises(migrations.SchemaMigrationError), connection(self.path) as db:
            migrations.apply(db)

    def test_app_scoped_history_reads_use_the_new_indexes(self):
        checks = [
            ("SELECT * FROM audit WHERE app_id=? ORDER BY id DESC LIMIT 100", ("sample-one",), "audit_app"),
            ("SELECT * FROM workflow_events WHERE job_id=?", ("job",), "workflow_events_job"),
            ("SELECT * FROM provider_action_events WHERE action_id=?", ("action",), "provider_action_events_action"),
            ("SELECT * FROM approvals WHERE app_id=?", ("sample-one",), "approvals_app"),
        ]
        with connection(self.path) as db:
            for sql, args, index in checks:
                details = [row["detail"] for row in db.execute("EXPLAIN QUERY PLAN " + sql, args)]
                self.assertTrue(any(index in line for line in details), (sql, details))

    def test_every_foreign_key_child_has_a_leading_index(self):
        with connection(self.path) as db:
            tables = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
                )
            ]
            missing = []
            for table in tables:
                indexes = [
                    [column[2] for column in db.execute(f"PRAGMA index_info('{index[1]}')")]
                    for index in db.execute(f"PRAGMA index_list('{table}')")
                ]
                foreign = {}
                for key in db.execute(f"PRAGMA foreign_key_list('{table}')"):
                    foreign.setdefault(key[0], []).append(key)
                for rows in foreign.values():
                    columns = [row[3] for row in sorted(rows, key=lambda row: row[1])]
                    if not any(index[: len(columns)] == columns for index in indexes):
                        missing.append((table, columns))
        self.assertEqual(missing, [], f"Unindexed foreign keys: {missing}")


if __name__ == "__main__":
    unittest.main()
