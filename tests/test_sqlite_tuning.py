"""Per-connection tuning is bounded and never weakens synchronous durability."""

import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mission_control.db import connection, session, transaction


class SQLiteTuningTests(unittest.TestCase):
    def test_zero_timeout_write_rejects_held_writer_without_waiting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite"
            with connection(path, write=True):
                started = time.monotonic()
                with self.assertRaises(sqlite3.OperationalError), connection(path, write=True, busy_timeout_ms=0):
                    self.fail("Contending nonblocking writer must not enter")
                self.assertLess(time.monotonic() - started, 1)
            for value in (-1, 60001, True, "0"):
                with self.subTest(value=value), self.assertRaises(ValueError), connection(path, busy_timeout_ms=value):
                    self.fail("Invalid timeout must not enter")

    def test_writers_serialize_read_modify_write_without_blocking_wal_reads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite"
            with connection(path) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE values_test(value INTEGER)")
                db.execute("INSERT INTO values_test VALUES(0)")
            first_ready = threading.Event()
            release_first = threading.Event()
            second_started = threading.Event()
            errors = []

            def writer(first):
                try:
                    with session(path) as db:

                        def trace(statement):
                            if not first and statement == "BEGIN IMMEDIATE":
                                second_started.set()

                        db.set_trace_callback(trace)
                        with transaction(path, db, write=True):
                            value = db.execute("SELECT value FROM values_test").fetchone()[0]
                            if first:
                                first_ready.set()
                                if not release_first.wait(5):
                                    raise TimeoutError("First writer was not released")
                            db.execute("UPDATE values_test SET value=?", (value + 1,))
                except Exception as error:  # noqa: BLE001 -- retain worker-thread errors for assertion in the owner thread.
                    errors.append(error)

            first = threading.Thread(target=writer, args=(True,))
            second = threading.Thread(target=writer, args=(False,))
            first.start()
            try:
                self.assertTrue(first_ready.wait(5))
                second.start()
                self.assertTrue(second_started.wait(5))
                with connection(path) as db:
                    self.assertEqual(db.execute("SELECT value FROM values_test").fetchone()[0], 0)
                    self.assertFalse(db.in_transaction)
            finally:
                release_first.set()
                first.join(5)
                if second.ident is not None:
                    second.join(5)
            self.assertFalse(first.is_alive())
            self.assertFalse(second.is_alive())
            self.assertEqual(errors, [])
            with connection(path) as db:
                self.assertEqual(db.execute("SELECT value FROM values_test").fetchone()[0], 2)

    def test_write_scope_begins_before_guards_and_commits(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite"
            observations = []
            with (
                patch(
                    "mission_control.automation_execution.guard_connection",
                    side_effect=lambda p, db, **kw: observations.append(db.in_transaction),
                ),
                connection(path, write=True) as db,
            ):
                db.execute("CREATE TABLE values_test(value INTEGER)")
                db.execute("INSERT INTO values_test VALUES(1)")
            self.assertEqual(observations, [True, True])
            with connection(path) as db:
                self.assertFalse(db.in_transaction)
                self.assertEqual(db.execute("SELECT value FROM values_test").fetchone()[0], 1)
                self.assertFalse(db.in_transaction)

    def test_guard_failure_rolls_back_write_scope(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite"
            with connection(path) as db:
                db.execute("CREATE TABLE values_test(value INTEGER)")
            for phase in ("entry", "commit"):

                def guard(p, db, committing=False, phase=phase):
                    if committing == (phase == "commit"):
                        raise PermissionError(phase)

                with (
                    self.subTest(phase=phase),
                    patch("mission_control.automation_execution.guard_connection", side_effect=guard),
                    self.assertRaises(PermissionError),
                    connection(path, write=True) as db,
                ):
                    db.execute("INSERT INTO values_test VALUES(1)")
                with connection(path) as db:
                    self.assertEqual(db.execute("SELECT count(*) FROM values_test").fetchone()[0], 0)

    def test_nested_write_rejection_preserves_callers_transaction(self):
        with tempfile.TemporaryDirectory() as folder, session(Path(folder) / "state.sqlite") as db:
            db.execute("CREATE TABLE values_test(value INTEGER)")
            db.execute("BEGIN")
            db.execute("INSERT INTO values_test VALUES(1)")
            with self.assertRaises(ValueError), transaction(Path(folder) / "state.sqlite", db, write=True):
                self.fail("Nested write scope must not yield")
            self.assertTrue(db.in_transaction)
            self.assertEqual(db.execute("SELECT count(*) FROM values_test").fetchone()[0], 1)
            db.rollback()

    def test_session_applies_bounded_cache_and_keeps_full_synchronous(self):
        with tempfile.TemporaryDirectory() as folder, connection(Path(folder) / "state.sqlite") as db:
            self.assertEqual(db.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(db.execute("PRAGMA cache_size").fetchone()[0], -16000)
            self.assertEqual(db.execute("PRAGMA temp_store").fetchone()[0], 2)
            self.assertGreater(db.execute("PRAGMA mmap_size").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA synchronous").fetchone()[0], 2)


if __name__ == "__main__":
    unittest.main()
