"""A downward-only SQL statement budget for the hottest workspace reads."""

import json
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from mission_control import db as database
from mission_control.service import Service
from mission_control.store import Store

ROOT = Path(__file__).resolve().parents[1]
BUDGETS = json.loads((ROOT / "tests/query_budgets.json").read_text(encoding="utf-8"))


def measure_connections(call):
    """Count statements on connections opened directly through ``sqlite3``."""
    statements = []
    original = sqlite3.connect

    def counted(*args, **kwargs):
        connection = original(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    with patch.object(sqlite3, "connect", counted):
        call()
    return len(statements)


def measure(call):
    """Count SQLite statements executed while ``call`` runs."""
    statements = []
    original = database.session

    @contextmanager
    def counted(path):
        with original(path) as handle:
            handle.set_trace_callback(statements.append)
            yield handle

    with patch.object(database, "session", counted):
        call()
    return len(statements)


class QueryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = Service(Store(Path(self.tmp.name) / "state.sqlite"))
        self.service.workspace("sample-one")
        self.service.bootstrap()

    def tearDown(self):
        self.tmp.cleanup()

    def test_workspace_read_stays_within_budget(self):
        measured = measure(lambda: self.service.workspace("sample-one"))
        self.assertLessEqual(
            measured,
            BUDGETS["workspace.read"],
            f"workspace read used {measured} statements; lower the hot loop or raise the budget deliberately",
        )

    def test_five_workspace_reads_stay_within_budget(self):
        measured = measure(lambda: [self.service.workspace("sample-one") for _ in range(5)])
        self.assertLessEqual(
            measured, BUDGETS["workspace.read.five"], f"five workspace reads used {measured} statements"
        )

    def test_bootstrap_stays_within_budget(self):
        measured = measure(self.service.bootstrap)
        self.assertLessEqual(measured, BUDGETS["bootstrap.read"], f"bootstrap used {measured} statements")

    def test_client_dashboard_stays_within_budget(self):
        measured = measure_connections(lambda: self.service.client_dashboard("sample-one"))
        self.assertLessEqual(measured, BUDGETS["client_dashboard.read"], f"client dashboard used {measured} statements")


if __name__ == "__main__":
    unittest.main()
