"""Real gzip → segment → checked SQLite partition → owner outcome projection."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mission_control.apple_analytics import PURCHASES, SUBSCRIPTION_STATE
from mission_control.apple_analytics_parser import parse_instance
from mission_control.apple_commerce_outcomes import commerce_outcomes
from mission_control.apple_metrics_store import _reconcile
from mission_control.apple_subscription_state import validate_observation
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.store import Store
from tests.test_apple_analytics_parser import segment


class CommerceOutcomeTests(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.store = Store(Path(folder.name) / "data.sqlite")
        self.expected = SimpleNamespace(store_app_id="123", connection_id="real-route-fixture", connection_version=1)
        self.reports = [
            dict(id=key, name=family, coverage="COMPLETE")
            for key, family in [("purchases", PURCHASES), ("subscriptions", SUBSCRIPTION_STATE)]
        ]
        self.result = dict(
            app_id="sample-one",
            start="2026-01-01",
            end="2026-01-02",
            rows=[dict(date="2026-01-01"), dict(date="2026-01-02")],
        )

    def save(self, family: str, date: str, processing: str, data: str) -> dict:
        header = (
            "State Metric,State Metric Grouping,Counts,Subscription Name"
            if family == SUBSCRIPTION_STATE
            else "Purchase Type,Purchases,Proceeds in USD,Private field"
        )
        lines = [
            "Date,App Apple Identifier," + header,
            *(date + ",123," + line + ",private-canary" for line in data.splitlines()),
        ]
        instance = parse_instance("123", processing, [segment("\n".join(lines) + "\n")], True, family)
        self.assertNotIn("private-canary", json.dumps(instance))
        report = next(r for r in self.reports if r["name"] == family)
        key = dict(
            app_id=self.result["app_id"],
            store_app_id="123",
            connection_id=self.expected.connection_id,
            connection_version=1,
            report_id=report["id"],
            report_family=family,
            granularity="DAILY",
            event_date=date,
        )
        with connection(self.store.path, write=True) as db:
            _reconcile(db, key, instance)
        return instance

    def output(self) -> dict[str, dict]:
        with connection(self.store.path) as db:
            return {r["label"]: r for r in commerce_outcomes(db, self.result, self.expected, self.reports)}

    def test_completeness_decimals_refunds_and_end_date_paid_snapshot(self) -> None:
        self.save(SUBSCRIPTION_STATE, "2026-01-01", "2026-01-04", "Full price,Paid plans,81")
        self.assertIsNone(self.output()["Active paid subscriptions"]["value"])
        self.save(
            SUBSCRIPTION_STATE,
            "2026-01-02",
            "2026-01-04",
            "Full price,Paid plans,3\nPaid offers,Subscription offers,2\nFree trials,Subscription offers,9\nGrace period,Billing issue,7",
        )
        interim = self.output()
        self.assertEqual(interim["Provisional paid subscription count"]["value"], "5")
        self.assertIsNone(interim["Active paid subscriptions"]["value"])
        self.save(
            SUBSCRIPTION_STATE,
            "2026-01-02",
            "2026-01-05",
            "Full price,Paid plans,3\nPaid offers,Subscription offers,2\nPreserved price,Paid plans,4\nContingent price,Paid plans,1\nFree trials,Subscription offers,8",
        )
        self.assertEqual(self.output()["Active paid subscriptions"]["value"], "10")
        self.save(
            PURCHASES,
            "2026-01-01",
            "2026-01-03",
            "App purchase,1,9007199254740993.123456789123456789\nIn-App Purchases,-1,-1.1",
        )
        prefix = self.output()
        self.assertIsNone(prefix["Apple estimated proceeds"]["value"])
        self.assertEqual(
            prefix["Apple estimated proceeds · 2026-01-01"]["value"], "9007199254740992.023456789123456789 USD"
        )
        self.save(PURCHASES, "2026-01-02", "2026-01-04", "App purchase,0,0.000000000000000001")
        money = self.output()["Apple estimated proceeds"]
        self.assertEqual(money["value"], "9007199254740992.023456789123456790 USD")
        self.assertEqual(len(money["source_sha256"]), 64)

    def test_unknown_group_or_missing_paid_row_stays_unknown_but_a_reported_zero_survives(self) -> None:
        bad = self.save(
            SUBSCRIPTION_STATE,
            "2026-01-02",
            "2026-01-05",
            "Paid offers,Paid plans,9\nNew opaque state,Unknown private grouping,8\nFull price,Paid plans,2",
        )
        self.assertIsNone(self.output()["Active paid subscriptions"]["value"])
        self.assertNotIn("private grouping", json.dumps(bad))
        with self.assertRaises(Invalid):
            validate_observation(dict(bad["rows"][0], type="active_paid"))
        self.save(SUBSCRIPTION_STATE, "2026-01-02", "2026-01-06", "Free trials,Subscription offers,11")
        self.assertIsNone(self.output()["Active paid subscriptions"]["value"])
        self.save(SUBSCRIPTION_STATE, "2026-01-02", "2026-01-07", "Full price,Paid plans,0")
        self.assertEqual(self.output()["Active paid subscriptions"]["value"], "0")

    def test_subscription_counts_and_identity_reject_invalid_input(self) -> None:
        for value in ("-1", "1.5", "", "1e5"):
            with self.subTest(value=value), self.assertRaises(Invalid):
                self.save(SUBSCRIPTION_STATE, "2026-01-02", "2026-01-05", "Full price,Paid plans," + value)
        with self.assertRaises(Invalid):
            parse_instance(
                "123",
                "2026-01-05",
                [
                    segment(
                        "Date,App Apple Identifier,State Metric,State Metric Grouping,Counts\n2026-01-02,321,Full price,Paid plans,1\n"
                    )
                ],
                True,
                SUBSCRIPTION_STATE,
            )
