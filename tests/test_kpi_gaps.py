"""KPI gaps stay explicit in metrics, reports and the workspace."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mission_control.ios_reports import projection
from mission_control.metrics import summarize
from mission_control.service import Service
from mission_control.store import Store

GAPS = ("CAC", "ROAS_D7", "ROAS_D30", "PAYBACK")


class KPIGapTests(unittest.TestCase):
    def test_summary_and_projection_mark_gaps_missing(self):
        summary = summarize([], "sample-one", [])
        gaps = {gap["metric"]: gap for gap in summary["kpi_gaps"]}
        for name in GAPS:
            self.assertEqual(gaps[name]["status"], "MISSING")
            self.assertTrue(gaps[name]["reason"])
        result = projection(dict(id="sample-one", data={"name": "Synthetic"}), [], [], datetime.now(timezone.utc))
        payload = json.loads(json.dumps(result, default=str))
        rows = {row["metric"]: row for row in payload["rows"]}
        for name in GAPS:
            self.assertEqual(rows["KPI gap: " + name]["observed"], "MISSING")

    def test_workspace_exposes_the_same_gaps(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Store(Path(folder) / "state.sqlite"))
            gaps = {gap["metric"]: gap for gap in service.workspace("sample-one")["metrics"]["kpi_gaps"]}
            for name in GAPS:
                self.assertEqual(gaps[name]["status"], "MISSING")

    def test_machine_matrix_keeps_the_same_gaps(self):
        matrix = json.loads(
            (Path(__file__).resolve().parents[1] / "specs/kpi-report-coverage.json").read_text(encoding="utf-8")
        )
        rows = {row["id"]: row for row in matrix["requirements"]}
        self.assertEqual(rows["PAYBACK"]["current_coverage"], "MISSING")
        for name in ("CAC", "ROAS_D7", "ROAS_D30"):
            self.assertEqual(rows[name]["current_coverage"], "PARTIAL_SUPPLIED_SCOPED_ECONOMICS")
            self.assertEqual(rows[name]["gap"], "MISSING")
            self.assertIn("live", rows[name]["gap_reason"])
            self.assertEqual(rows[name]["required_status"], "REQUIRED_NOT_COMPLETE")
