"""Private Apple and separate supplied-cohort metrics from a real owner route."""

import json
import unittest
from typing import Any

from mission_control.campaign_owner_reports import initialize
from mission_control.common import canonical, digest, iso_time
from mission_control.db import connection
from mission_control.ledger import Ledger
from mission_control.search_store_outcomes import _cohort_rows, _downloads
from tests import test_apple_metrics_http_route as route_fixtures
from tests.test_ledger import cohort, event
from tests.test_subscription_journey import bound


class OutcomeCoverageTests(unittest.TestCase):
    def test_imported_counts_do_not_promote_gross_revenue_or_unmatched_payments_to_proceeds(self) -> None:
        contract = dict(
            cost_basis="MEDIA_SPEND",
            revenue_basis="GROSS_REVENUE",
            attribution_status="DECLARED_MATCHED",
            spend_source="spent",
            currency="USD",
            coverage_through="2026-10-01T00:00:00+00:00",
        )
        definition: dict[str, Any] = cohort(economics=contract)
        cutoff = iso_time(definition["matures_at"])
        events = [event("install", "INSTALL"), bound("purchase", "PURCHASE", amount=900)]
        observed = _cohort_rows(definition, events, cutoff)
        self.assertIsNone(observed[0]["value"])
        self.assertEqual(observed[1]["value"], "1")
        definition["economics"]["revenue_basis"] = "NET_PROCEEDS"
        events.append(event("orphan", "PURCHASE", amount=99, subject="other"))
        self.assertIsNone(_cohort_rows(definition, events, cutoff)[0]["value"])
        self.assertIsNone(_cohort_rows(definition, events[:1], cutoff)[0]["value"])
        definition["observability"] = "PARTIAL"
        self.assertIsNone(_cohort_rows(definition, events[:2], cutoff)[1]["value"])

    def test_total_requires_mature_nonmissing_components_including_an_explicit_zero(self) -> None:
        day: dict[str, Any] = dict(
            date="2026-09-01",
            downloads=dict(
                status="APPLE_REPORTED",
                source_sha256="a" * 64,
                counts=dict(first_time_downloads="9007199254740993", redownloads="0"),
            ),
        )
        self.assertEqual(_downloads(dict(rows=[day]))["value"], "9007199254740993")
        self.assertEqual(len(_downloads(dict(rows=[day]))["source_sha256"]), 64)
        day["downloads"]["counts"]["redownloads"] = None
        self.assertIsNone(_downloads(dict(rows=[day]))["value"])
        day["downloads"]["counts"]["redownloads"] = "1"
        day["downloads"]["status"] = "PROVISIONAL"
        self.assertIsNone(_downloads(dict(rows=[day]))["value"])

    def test_matched_owner_report_and_supplied_cohort_do_not_become_app_wide_results(self) -> None:
        route = route_fixtures.AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
        route.setUp()
        self.addCleanup(route.doCleanups)
        app = route_fixtures.APP
        ledger = Ledger(route.store.path)
        contract = dict(
            cost_basis="MEDIA_SPEND",
            revenue_basis="NET_PROCEEDS",
            attribution_status="DECLARED_MATCHED",
            spend_source="synthetic campaign export",
            currency="USD",
            coverage_through="2026-10-01T00:00:00+00:00",
        )
        definition: dict[str, Any] = cohort(economics=contract)
        ledger.define(app, definition)
        ledger.define(app, dict(definition, cohort_id="other-platform", platform="Android"))
        ledger.define("sample-two", dict(definition, cohort_id="other-app"))
        ledger.ingest(
            app,
            dict(
                cohort_id=definition["cohort_id"],
                events=[event("install", "INSTALL"), bound("pay", "PURCHASE", amount=810)],
            ),
        )
        initialize(route.store)
        with connection(route.store.path, write=True) as db:
            current = json.loads(db.execute("SELECT data FROM apps WHERE id=?", (app,)).fetchone()[0])
            for owner, count in [("owner", 2), ("another-owner", 73)]:
                data = dict(
                    app_id=app,
                    owner=owner,
                    source=dict(app_hash=digest(current)),
                    selection=dict(
                        scope_id="scope-a",
                        measurement_window=dict(starts_at=definition["starts_at"], ends_at=definition["ends_at"]),
                    ),
                    apple_downloads=dict(
                        territory="US",
                        status="REPORTED",
                        delivery={"status": "EXACT_TAGGED_POST_READBACK"},
                        first_time_downloads=count,
                    ),
                )
                db.execute(
                    "INSERT INTO campaign_owner_reports VALUES(?,?,?,?,?,?,?,?,?)",
                    (owner, app, owner, None, "capture", canonical(data), digest(data), "comparison", "2026-10-01"),
                )
        body: dict[str, Any] = dict(manifest_version=route.app["version"], start="2026-09-01", end="2026-09-07")
        for action in ("performance", "search-review"):
            result = route.post(route_fixtures.BASE + action, body)["outcome_coverage"]
            metrics = {m["label"]: m for m in result["metrics"]}
            self.assertIsNone(metrics["Campaign-attributed first-time downloads"]["value"])
            self.assertNotIn("campaign_report_id", metrics["Campaign-attributed first-time downloads"])
            for label in [
                "App Store conversion rate",
                "Apple estimated proceeds",
                "Active paid subscriptions",
                "Total downloads",
            ]:
                self.assertIsNone(metrics[label]["value"])
                self.assertTrue(metrics[label]["repair"])
            private = {m["label"]: m for m in result["cohorts"]}
            self.assertEqual(private["Imported subscription purchasers"]["value"], "1")
            self.assertEqual(private["Imported cohort net proceeds"]["value"], "810 USD minor units")
            self.assertEqual(len(private["Imported cohort net proceeds"]["source_sha256"]), 64)
            self.assertNotIn("opaque-1", json.dumps(result))
            self.assertNotIn("other-platform", json.dumps(result))
            self.assertNotIn("another-owner", json.dumps(result))
        shifted = route.post(route_fixtures.BASE + "search-review", dict(body, start="2026-09-02"))["outcome_coverage"]
        self.assertEqual(shifted["cohorts"], [])
        self.assertFalse(any(row["value"] for row in shifted["metrics"]))
