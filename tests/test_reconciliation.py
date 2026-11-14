"""Cross-source reconciliation keeps exact deltas and never averages."""

import unittest

from mission_control.reconciliation import matrix, row, summary


class ReconciliationTests(unittest.TestCase):
    def test_conflict_match_and_incompatible_groups_are_distinct(self):
        conflict = matrix(
            [
                row("a", "paid", "week", 10, "customers", definition="ledger"),
                row("b", "paid", "week", 12, "customers", definition="ledger"),
            ]
        )
        group = conflict["groups"][0]
        self.assertEqual(group["status"], "CONFLICT")
        self.assertEqual(group["deltas"][0]["difference"], 2)
        self.assertIsNone(group.get("average"))
        match = matrix(
            [
                row("a", "paid", "week", 10, "customers", definition="ledger"),
                row("b", "paid", "week", 10, "customers", definition="ledger"),
            ]
        )
        self.assertEqual(match["groups"][0]["status"], "MATCH")
        incompatible = matrix([row("a", "paid", "week", 10, "customers"), row("b", "paid", "week", 0.1, "rate")])
        self.assertEqual(incompatible["groups"][0]["status"], "INCOMPATIBLE")

    def test_single_source_and_no_data_are_explicit(self):
        single = matrix([row("a", "installs", "c1", 4, "count")])
        self.assertEqual(single["groups"][0]["status"], "SINGLE_SOURCE")
        self.assertEqual(matrix([row("a", "installs", "c1", None, "count")])["groups"][0]["status"], "NO_DATA")

    def test_workspace_summary_projects_ledger_and_provider_rows(self):
        workspace = dict(
            ledger=[
                dict(
                    cohort=dict(cohort_id="c1", currency="USD"),
                    status="SUPPLIED_RECONCILED",
                    installs=10,
                    paid=2,
                    net_proceeds_minor=1000,
                    paid_cac_minor=500,
                    source_hash="a" * 64,
                )
            ],
            insights=dict(
                reports=[
                    dict(
                        provider="posthog",
                        source_id="source",
                        hash="b" * 64,
                        data=dict(rows=[dict(id="signup_completed", value=10, unit="events", period="last_7_days")]),
                    )
                ]
            ),
            storekit=dict(report=dict(status="NO_DATA", transactions=[])),
        )
        result = summary(workspace)
        metrics = {group["metric"] for group in result["groups"]}
        self.assertIn("paid", metrics)
        self.assertIn("signup_completed", metrics)
        self.assertNotIn("storekit_transactions", metrics)


if __name__ == "__main__":
    unittest.main()
