"""Required metrics cannot silently disappear or lose their repair contract."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class KpiDataGapTests(unittest.TestCase):
    def test_documented_coverage_matches_the_machine_register(self) -> None:
        matrix = json.loads((ROOT / "specs/kpi-report-coverage.json").read_text(encoding="utf-8"))
        machine = {
            metric["id"]: (
                metric["current_coverage"] + f"; LIVE_GAP={metric['gap']}"
                if metric.get("gap") and metric["current_coverage"].startswith("PARTIAL_SUPPLIED")
                else metric["current_coverage"]
            )
            for metric in matrix["requirements"]
        }
        report = (ROOT / "docs/WMM-KPI-COVERAGE.md").read_text(encoding="utf-8")
        table = report.split("## Required metrics\n", 1)[1].split("\n## Explicit gaps", 1)[0]
        rows = re.findall(r"^\| ([A-Z][A-Z0-9_]+) \| ([^|]+?) \|", table, re.MULTILINE)
        self.assertEqual(len(rows), len(machine))
        self.assertEqual(dict(rows), machine)

    def test_every_registered_metric_has_specific_inputs_action_and_evidence(self) -> None:
        matrix = json.loads((ROOT / "specs/kpi-report-coverage.json").read_text(encoding="utf-8"))
        metrics = matrix["requirements"]
        self.assertEqual(len(metrics), 42)
        self.assertEqual(len({metric["id"] for metric in metrics}), len(metrics))
        for metric in metrics:
            with self.subTest(metric=metric["id"]):
                gap = metric["data_gap"]
                self.assertGreater(len(gap["required_inputs"]), 25)
                self.assertGreater(len(gap["next_action"]), 40)
                self.assertEqual(len(gap["closure_evidence"]), 3)
                self.assertIn("UNAVAILABLE", metric["state_vocabulary"])
                self.assertIn("OBSERVED_ZERO", metric["state_vocabulary"])
                self.assertEqual(metric["required_status"], "REQUIRED_NOT_COMPLETE")
        self.assertEqual(len({metric["data_gap"]["next_action"] for metric in metrics}), len(metrics))

    def test_economics_does_not_promote_supplied_evidence_to_live_completion(self) -> None:
        matrix = json.loads((ROOT / "specs/kpi-report-coverage.json").read_text(encoding="utf-8"))
        metrics = {metric["id"]: metric for metric in matrix["requirements"]}
        for name in ("CAC", "ROAS_D7", "ROAS_D30"):
            self.assertEqual(metrics[name]["current_coverage"], "PARTIAL_SUPPLIED_SCOPED_ECONOMICS")
        for name in ("RETENTION_D1", "RETENTION_D7", "RETENTION_D30"):
            self.assertIn("mature", metrics[name]["data_gap"]["next_action"])
        self.assertIn("tracking", metrics["EXPERIMENT_OUTCOME"]["data_gap"]["next_action"])


if __name__ == "__main__":
    unittest.main()
