"""Prove linear event selection preserves complete, app-isolated reports."""

import tempfile
import unittest
from pathlib import Path
from typing import cast
from unittest.mock import patch

from mission_control.common import Invalid, iso_time
from mission_control.ledger import Ledger, report
from mission_control.service import Service
from mission_control.store import Store
from tests.test_ledger import cohort, event


class CountingEvents(list):
    """Count source iterations without relying on machine-dependent timings."""

    def __init__(self, records):
        super().__init__(records)
        self.visits = 0

    def __iter__(self):
        for record in super().__iter__():
            self.visits += 1
            yield record


class LedgerGroupingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name) / "state.sqlite")
        self.service = Service(self.store)
        self.ledger = Ledger(self.store.path)

    def test_full_reports_equal_reference_across_cohorts_and_apps(self):
        for app_id in ("sample-one", "sample-two"):
            for cohort_id in ("control", "variant", "empty"):
                self.service.cohort(app_id, cohort(cohort_id=cohort_id))
            for cohort_id in ("control", "variant"):
                rows = [
                    event("install", "INSTALL"),
                    event("purchase", "PURCHASE", amount=2000 if app_id == "sample-one" else 9000),
                    event("cost", "COST_ACQUISITION", amount=300),
                    event("delivery", "COST_DELIVERY", amount=100),
                    event("refund", "REFUND", "2026-10-03", 500, "purchase"),
                    event("reversal", "REFUND_REVERSED", "2026-10-05", 500, "refund"),
                ]
                for row in rows:
                    row["provider"] = cohort_id
                self.service.events(app_id, {"cohort_id": cohort_id, "events": rows})
        for app_id in ("sample-one", "sample-two"):
            snapshot = self.ledger.export(app_id)
            for cutoff in ("2026-10-02", "2026-10-04", "2026-10-11"):
                as_of = cutoff + "T00:00:00+00:00"
                expected = [
                    report(
                        definition,
                        [r["data"] for r in snapshot["events"] if r["cohort_id"] == definition["cohort_id"]],
                        iso_time(as_of),
                    )
                    for definition in snapshot["cohorts"]
                ]
                self.assertEqual(self.ledger.reports(app_id, as_of), expected)
        first = self.ledger.reports("sample-one", "2026-10-11T00:00:00+00:00")
        second = self.ledger.reports("sample-two", "2026-10-11T00:00:00+00:00")
        self.assertEqual(next(r for r in first if r["cohort"]["cohort_id"] == "control")["net_proceeds_minor"], 2000)
        self.assertEqual(next(r for r in second if r["cohort"]["cohort_id"] == "control")["net_proceeds_minor"], 9000)

    def test_selects_events_once_and_preserves_order_and_empty_cohorts(self):
        definitions = [{"cohort_id": str(i)} for i in range(40)]
        events = CountingEvents({"cohort_id": str(i % 39), "data": {"source_order": i}} for i in range(1000))
        snapshot = {"cohorts": definitions, "events": events}
        with (
            patch.object(self.ledger, "export", return_value=snapshot),
            patch("mission_control.ledger.report", side_effect=lambda definition, rows, cutoff: rows),
        ):
            actual = cast(list[list[dict[str, int]]], self.ledger.reports("sample-one", "2026-10-11T00:00:00+00:00"))
        self.assertEqual(events.visits, 1000)
        self.assertEqual(actual[-1], [])
        self.assertEqual([row["source_order"] for row in actual[0]], list(range(0, 1000, 39)))

    def test_invalid_cutoff_rejected_before_reading_snapshot(self):
        with patch.object(self.ledger, "export") as export:
            with self.assertRaises(Invalid):
                self.ledger.reports("sample-one", "2999-01-01T00:00:00+00:00")
            export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
