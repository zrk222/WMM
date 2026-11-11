"""Prove shared workspace reads keep scope, fresh data and guard boundaries."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mission_control import db
from mission_control.store import Store
from mission_control.worker import jobs


class WorkspaceReadScopeTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "workspace.sqlite3", seed=False)
        for app_id in ("sample-one", "sample-two"):
            self.store.save_app(
                app_id, {"name": app_id, "release": "1", "locale": "en-US"}
            )

    def test_share_one_handle_but_keep_separate_guard_calls(self):
        with patch(
            "mission_control.db.sqlite3.connect", wraps=db.sqlite3.connect
        ) as connect:
            with patch(
                "mission_control.automation_execution.guard_connection"
            ) as guard:
                with self.store.read_scope("sample-one") as conn:
                    self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)
                self.assertEqual(connect.call_count, 1)
                self.assertEqual(
                    [
                        call.kwargs.get("committing", False)
                        for call in guard.call_args_list
                    ],
                    [False, True, False, True],
                )
                self.assertTrue(
                    all(call.args[1] is conn for call in guard.call_args_list)
                )

    def test_domain_read_sees_independent_commit_after_app_check(self):
        with self.store.read_scope("sample-one") as reader:
            self.assertFalse(reader.in_transaction)
            with db.connection(self.store.path) as writer:
                writer.execute(
                    "INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",
                    (
                        "sample-one",
                        "synthetic.concurrent",
                        "{}",
                        "2026-11-11T00:00:00+00:00",
                    ),
                )
            self.assertEqual(
                reader.execute(
                    "SELECT action FROM audit WHERE app_id=? ORDER BY id DESC LIMIT 1",
                    ("sample-one",),
                ).fetchone()[0],
                "synthetic.concurrent",
            )
        self.assertNotIn(
            "synthetic.concurrent",
            [row["action"] for row in self.store.history("sample-two")],
        )

    def test_missing_app_and_second_guard_failure_still_deny_reads(self):
        for method in (
            self.store.records,
            self.store.history,
            lambda app_id: jobs(self.store, app_id),
        ):
            with (
                self.subTest(method=method),
                self.assertRaisesRegex(KeyError, "App workspace not found"),
            ):
                method("missing")
        with patch(
            "mission_control.automation_execution.guard_connection",
            side_effect=[None, None, PermissionError("revoked")],
        ):
            with self.assertRaisesRegex(PermissionError, "revoked"):
                with self.store.read_scope("sample-one"):
                    self.fail("Guard must reject the domain read before it runs")


if __name__ == "__main__":
    unittest.main()
