"""Pre-registration drafts compose app facts without creating authority."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mission_control.common import digest
from mission_control.evidence_gate import measurement_plan
from mission_control.insights_contract import shape_posthog, shape_revenuecat
from mission_control.pre_registration import draft
from mission_control.service import Service
from mission_control.store import Store


def app(website="https://example.test/app"):
    return dict(id="sample-one", data=dict(name="Synthetic app", release="1.2.3", website=website))


NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)


def snapshot(*providers, age=timedelta(), status="CONNECTED"):
    sources, reports = [], []
    for provider in providers:
        config = dict(provider=provider, project_id="123" if provider == "posthog" else "projabc")
        sources.append(dict(id=provider, provider=provider, data=config, version=2, status=status))
        if provider == "posthog":
            scope = "PROJECT_ID_CHECKED"
            rows = shape_posthog({"results": [["activation_completed", 7]]})
        else:
            scope = "PROJECT_PATH_CHECKED_PROJECT_WIDE_METRICS"
            rows = shape_revenuecat(
                {
                    "object": "overview_metrics",
                    "metrics": [
                        {"id": "mrr", "value": 42, "name": "MRR", "unit": "USD", "period": "monthly"},
                    ],
                }
            )
        report = dict(
            config,
            observed_at=(NOW - age).isoformat(),
            scope=scope,
            rows=rows,
            source_version=2,
            configuration_hash=digest(config),
        )
        reports.append(
            dict(app_id="sample-one", source_id=provider, provider=provider, hash=digest(report), data=report)
        )
    return dict(sources=sources, reports=reports)


class PreRegistrationTests(unittest.TestCase):
    def test_ready_draft_tags_the_link_and_validates_its_plan(self):
        result = draft(app(), snapshot("posthog", "revenuecat"), goal="paid conversion", observed=NOW)
        self.assertEqual(result["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(result["missing"], [])
        self.assertFalse(result["outcome_tracking_verified"])
        self.assertIn("consented test", result["tracking_next_step"])
        plan = result["measurement_plan"]
        self.assertEqual(plan["primary_metric"], "paid_conversion")
        self.assertIn("utm_campaign=" + plan["campaign_tag"], result["tagged_link"])
        self.assertEqual(measurement_plan(plan)["campaign_tag"], plan["campaign_tag"])
        self.assertEqual(result["experiment_draft"]["primary_metric"], "paid_conversion")

    def test_missing_link_or_source_keeps_the_draft_blocked(self):
        no_link = draft(app(website=""), snapshot("posthog", "revenuecat"), goal="paid conversion", observed=NOW)
        self.assertEqual(no_link["status"], "DRAFT")
        self.assertIsNone(no_link["measurement_plan"])
        self.assertTrue(any("HTTPS landing link" in item for item in no_link["missing"]))
        no_outcome = draft(app(), snapshot("posthog"), goal="paid conversion", observed=NOW)
        self.assertEqual(no_outcome["status"], "DRAFT")
        self.assertTrue(any("RevenueCat" in item for item in no_outcome["missing"]))

    def test_draft_does_not_copy_private_query_or_goal_into_link(self):
        result = draft(
            app("https://example.test/app?invite=private#private"),
            snapshot("posthog"),
            goal="Private goal",
            observed=NOW,
        )
        self.assertEqual(result["status"], "DRAFT")
        for private in ("invite", "#", "private"):
            self.assertNotIn(private, result["tagged_link"])
        self.assertIsNone(draft(app("https://[bad"), snapshot())["measurement_plan"])

    def test_missing_stale_replaced_or_other_app_reports_do_not_count(self):
        for issue in ("missing", "stale", "replaced", "other app", "disconnected", "empty", "future"):
            with self.subTest(issue=issue):
                insights = snapshot(
                    "posthog",
                    "revenuecat",
                    age={"stale": timedelta(days=8), "future": -timedelta(seconds=1)}.get(issue, timedelta()),
                )
                source, report = insights["sources"][-1], insights["reports"][-1]
                if issue == "missing":
                    insights["reports"].pop()
                if issue == "replaced":
                    source["version"] += 1
                if issue == "other app":
                    report["app_id"] = "sample-two"
                if issue == "disconnected":
                    source["status"] = "PERMISSION_REQUIRED"
                if issue == "empty":
                    report["data"]["rows"] = []
                    report["hash"] = digest(report["data"])
                result = draft(app(), insights, goal="paid conversion", observed=NOW)
                self.assertEqual(result["status"], "DRAFT")
                self.assertNotIn("revenuecat", result["providers"])
                self.assertTrue(any("RevenueCat" in item for item in result["missing"]))

    def test_workspace_passes_existing_insights_snapshot_without_another_read(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Store(Path(folder) / "state.sqlite"))
            insights = service.workspace("sample-one")["insights"]
            reports = snapshot("posthog", "revenuecat")
            for report in reports["reports"]:
                report["data"]["observed_at"] = datetime.now(timezone.utc).isoformat()
                report["hash"] = digest(report["data"])
            with patch("mission_control.insights.Insights.list", return_value={**insights, **reports}) as listing:
                result = service.workspace("sample-one")["pre_registration"]
            listing.assert_called_once_with("sample-one")
            self.assertEqual(result["providers"], ["posthog", "revenuecat"])
            self.assertFalse(result["outcome_tracking_verified"])
            self.assertIn("verify a consented test from the tagged link", result["limits"])
            self.assertFalse(result["authority_issued"])
            self.assertFalse(result["external_writes"])


if __name__ == "__main__":
    unittest.main()
