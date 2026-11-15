"""Measure core read statement counts; --update never raises a stored budget."""

import json
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mission_control import db as database  # noqa: E402
from mission_control.service import Service  # noqa: E402
from mission_control.store import Store  # noqa: E402

BUDGETS = ROOT / "tests/query_budgets.json"


def measure_connections(call):
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


def current():
    with tempfile.TemporaryDirectory() as folder:
        service = Service(Store(Path(folder) / "state.sqlite"))
        service.workspace("sample-one")
        service.bootstrap()
        return {
            "workspace.read": measure(lambda: service.workspace("sample-one")),
            "workspace.read.five": measure(lambda: [service.workspace("sample-one") for _ in range(5)]),
            "bootstrap.read": measure(service.bootstrap),
            "client_dashboard.read": measure_connections(lambda: service.client_dashboard("sample-one")),
        }


def main(argv):
    stored = json.loads(BUDGETS.read_text(encoding="utf-8"))
    observed = current()
    rows = []
    for name in sorted(observed):
        budget = stored.get(name)
        rows.append(
            dict(
                name=name,
                observed=observed[name],
                budget=budget,
                status="OVER_BUDGET" if budget is not None and observed[name] > budget else "WITHIN",
            )
        )
    print("QUERY_BUDGET " + json.dumps(dict(schema="wmm.query-budget.v1", budgets=rows), sort_keys=True))
    if "--update" in argv:
        lowered = {name: min(observed[name], stored[name]) if name in stored else observed[name] for name in observed}
        BUDGETS.write_text(json.dumps(lowered, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print("QUERY_BUDGET_UPDATED " + json.dumps(lowered, sort_keys=True))
        return 0
    return 1 if any(row["status"] == "OVER_BUDGET" for row in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
