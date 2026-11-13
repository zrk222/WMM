"""Exact cohort economics proofs using supplied immutable ledger evidence."""

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from mission_control.common import Invalid, digest, iso_time
from mission_control.ledger import Ledger, cohort_data, event_data, finance, report
from mission_control.measurement_economics import Event, build_economics, validate_contract
from mission_control.store import Store
from tests.test_ledger import cohort, event
from tests.test_subscription_journey import bound

AS_OF = datetime(2026, 10, 11, tzinfo=timezone.utc)


def contract(**changes):
    return dict(
        cost_basis="MEDIA_SPEND",
        revenue_basis="NET_PROCEEDS",
        attribution_status="DECLARED_MATCHED",
        spend_source="Synthetic export receipt",
        currency="USD",
        coverage_through=AS_OF.isoformat(),
        **changes,
    )


def definition(**changes):
    policy = contract()
    policy.update(changes)
    return cohort(economics=policy)


def rows():
    return [
        event("install", "INSTALL"),
        event("purchase", "PURCHASE", amount=2000),
        event("cost", "COST_ACQUISITION", amount=500),
    ]


def economics(data=None, events=None, as_of=AS_OF):
    return build_economics(
        data or definition(), cast(list[Event], rows() if events is None else events), as_of, finance
    )


class EconomicsTests(unittest.TestCase):
    def metric(self, value, name="net_proceeds_roas_d7"):
        return value["metrics"][name]

    def codes(self, value, name="net_proceeds_roas_d7"):
        return {item["code"] for item in self.metric(value, name)["unavailable_data"]}

    def test_optional_declaration_preserves_old_cohort_and_paid_cac_semantics(self):
        old = cohort_data(cohort())
        self.assertNotIn("economics", old)
        value = report(old, rows(), AS_OF)
        self.assertIsNone(value["paid_cac_minor"])  # Existing COST_DELIVERY completeness stays required.
        self.assertIn("ECONOMICS_DECLARATION_MISSING", self.codes(value["economics"]))
        self.assertEqual(cast(dict[str, str], cohort_data(definition())["economics"])["currency"], "USD")

    def test_unchanged_evidence_keeps_semantic_report_hash_when_clock_advances(self):
        # Experiment assessments intentionally exclude only the outer as_of field.
        # Nested economics must not reintroduce a clock-only hash difference.
        first = report(cohort(), rows(), AS_OF)
        later = report(cohort(), rows(), iso_time("2026-10-12T00:00:00Z"))
        first.pop("as_of")
        later.pop("as_of")
        self.assertEqual(digest(first), digest(later))
        covered = definition(coverage_through="2026-10-13T00:00:00Z")
        self.assertEqual(economics(covered), economics(covered, as_of=iso_time("2026-10-12T00:00:00Z")))

    def test_scoped_cac_and_net_d7_d30_have_exact_operands(self):
        result = economics()
        self.assertEqual(self.metric(result, "cac_minor")["value"], 500)
        for days in (7, 30):
            value = self.metric(result, f"net_proceeds_roas_d{days}")
            self.assertEqual((value["value"], value["numerator_minor"], value["denominator"]), (4, 2000, 500))
            self.assertEqual(value["status"], "SUPPLIED")
            self.assertEqual(value["sample_counts"]["installs"], 1)
            self.assertEqual(len(value["source_hash"]), 64)
        self.assertIsNone(self.metric(result, "gross_revenue_roas_d7")["value"])

    def test_partial_attribution_observability_and_currency_each_block(self):
        cases = [
            (definition(attribution_status="PARTIAL"), rows(), "ATTRIBUTION_INCOMPLETE"),
            (dict(definition(), observability="PARTIAL"), rows(), "OBSERVABILITY_INCOMPLETE"),
            (definition(currency="EUR"), rows(), "DECLARED_CURRENCY_MISMATCH"),
            (definition(), [*rows(), event("foreign", "PURCHASE", amount=1, currency="EUR")], "FINANCE_UNRECONCILED"),
        ]
        for data, events, code in cases:
            with self.subTest(code=code):
                value = economics(data, events)
                self.assertIsNone(self.metric(value)["value"])
                self.assertIn(code, self.codes(value))
                self.assertTrue(all(item["action"] for item in self.metric(value)["unavailable_data"]))

    def test_absent_spend_wrong_source_and_outside_window_do_not_become_zero(self):
        for cost in (
            None,
            event("cost", "COST_ACQUISITION", amount=500, source="wrong"),
            event("cost", "COST_ACQUISITION", day="2026-09-08", amount=500),
        ):
            events = rows()[:2] + ([] if cost is None else [cost])
            value = economics(events=events)
            self.assertIsNone(self.metric(value)["denominator"])
            self.assertIn("MATCHED_SPEND_MISSING", self.codes(value))
        self.assertIn(
            "SPEND_SOURCE_MISMATCH",
            self.codes(economics(events=rows()[:2] + [event("cost", "COST_ACQUISITION", source="wrong")])),
        )

    def test_explicit_zero_spend_allows_zero_cac_but_not_roas(self):
        value = economics(events=rows()[:2] + [event("cost", "COST_ACQUISITION", amount=0)])
        self.assertEqual(self.metric(value, "cac_minor")["value"], 0)
        self.assertIsNone(self.metric(value)["value"])
        self.assertEqual(self.metric(value)["denominator"], 0)
        self.assertIn("ZERO_SPEND_DENOMINATOR", self.codes(value))

    def test_no_purchases_with_positive_spend_is_zero_roas_not_zero_cac(self):
        value = economics(events=[rows()[0], rows()[2]])
        self.assertEqual(self.metric(value)["value"], 0)
        self.assertIsNone(self.metric(value, "cac_minor")["value"])
        self.assertIn("NO_ACQUIRED_PAYERS", self.codes(value, "cac_minor"))

    def test_total_acquisition_cost_supports_cac_but_not_roas(self):
        value = economics(definition(cost_basis="TOTAL_ACQUISITION_COST"))
        self.assertEqual(self.metric(value, "cac_minor")["value"], 500)
        self.assertIn("ROAS_REQUIRES_MEDIA_SPEND", self.codes(value))

    def test_gross_declared_amounts_are_distinct_from_net_proceeds(self):
        value = economics(definition(revenue_basis="GROSS_REVENUE"))
        self.assertEqual(self.metric(value, "gross_revenue_roas_d7")["value"], 4)
        self.assertIsNone(self.metric(value)["value"])
        self.assertIn("REVENUE_BASIS_UNDECLARED", self.codes(value))

    def test_horizons_are_install_relative_with_exclusive_upper_bounds(self):
        events = [
            rows()[0],
            rows()[2],
            event("before", "PURCHASE", day="2026-09-01", amount=900),
            event("inside7", "PURCHASE", day="2026-09-08", amount=100),
            event("exact7", "PURCHASE", day="2026-09-09", amount=200),
            event("exact30", "PURCHASE", day="2026-10-02", amount=400),
            event("other", "PURCHASE", amount=800, subject="not-acquired"),
        ]
        value = economics(events=events)
        self.assertEqual(self.metric(value)["numerator_minor"], 100)
        self.assertEqual(self.metric(value, "net_proceeds_roas_d30")["numerator_minor"], 300)
        self.assertEqual(self.metric(value, "cac_minor")["denominator"], 1)

    def test_renewal_is_counted_in_horizon_without_creating_another_payer(self):
        events = [
            rows()[0],
            rows()[2],
            bound("purchase", "PURCHASE", day="2026-09-02", amount=2000),
            bound("renewal", "RENEWAL", day="2026-09-05", amount=300, related="purchase"),
            bound("later-renewal", "RENEWAL", day="2026-09-12", amount=400, related="purchase"),
        ]
        value = economics(events=events)
        self.assertEqual(self.metric(value)["numerator_minor"], 2300)
        self.assertEqual(self.metric(value, "net_proceeds_roas_d30")["numerator_minor"], 2700)
        self.assertEqual(self.metric(value, "cac_minor")["denominator"], 1)
        self.assertEqual(economics(events=events + events)["source_hash"], value["source_hash"])

    def test_orphan_renewal_blocks_report_economics_like_subscription_journey(self):
        events = [*rows(), event_data(bound("orphan", "RENEWAL", amount=300, related="missing"))]
        value = report(definition(), events, AS_OF)
        self.assertTrue(value["subscription_journey"]["issues"])
        for metric in value["economics"]["metrics"].values():
            self.assertIsNone(metric["value"])
            self.assertIn("SUBSCRIPTION_LINEAGE_UNRECONCILED", {item["code"] for item in metric["unavailable_data"]})

    def test_renewal_requires_same_subject_binding_and_strictly_earlier_parent(self):
        purchase = event_data(bound("purchase", "PURCHASE", day="2026-09-03", amount=2000))
        cases = [
            bound("renewal", "RENEWAL", day="2026-09-04", amount=300, related="purchase", subject="other"),
            bound(
                "renewal",
                "RENEWAL",
                day="2026-09-04",
                amount=300,
                related="purchase",
                binding={"variant_id": "different"},
            ),
            bound("renewal", "RENEWAL", day="2026-09-03", amount=300, related="purchase"),
            bound("renewal", "RENEWAL", day="2026-09-02", amount=300, related="purchase"),
            bound("renewal", "RENEWAL", day="2026-09-04", amount=300, related="purchase", provider="different"),
        ]
        for renewal in cases:
            with self.subTest(renewal=renewal):
                value = economics(events=[rows()[0], rows()[2], purchase, event_data(renewal)])
                self.assertIsNone(self.metric(value)["value"])
                self.assertIn("SUBSCRIPTION_LINEAGE_UNRECONCILED", self.codes(value))

    def test_unbound_renewal_cannot_bypass_ingestion_validation_in_pure_economics(self):
        value = economics(events=[*rows(), event("renewal", "RENEWAL", amount=300, related="purchase")])
        self.assertIsNone(self.metric(value)["value"])
        self.assertIn("SUBSCRIPTION_EVENT_INVALID", self.codes(value))

    def test_each_acquired_subject_uses_its_own_first_install_cutoff(self):
        events = [
            *rows(),
            event("install2", "INSTALL", day="2026-09-07", subject="opaque-2"),
            event("reinstall", "INSTALL", day="2026-09-08", subject="opaque-2"),
            event("later-purchase", "PURCHASE", day="2026-09-13", amount=100, subject="opaque-2"),
            event("boundary2", "PURCHASE", day="2026-09-14", amount=900, subject="opaque-2"),
        ]
        value = economics(events=events)
        self.assertEqual(self.metric(value)["numerator_minor"], 2100)
        self.assertEqual(self.metric(value)["sample_counts"]["installs"], 2)
        self.assertEqual(self.metric(value, "cac_minor")["value"], 250)

    def test_all_installs_need_end_plus_horizon_maturity_and_coverage(self):
        value = economics(as_of=iso_time("2026-09-10T00:00:00Z"))
        self.assertIn("HORIZON_INCOMPLETE", self.codes(value))
        value = economics(definition(coverage_through="2026-09-14T23:59:59Z"))
        self.assertIn("HORIZON_INCOMPLETE", self.codes(value))
        value = economics(definition(coverage_through="2026-10-08T00:00:00Z"), as_of=iso_time("2026-10-08T00:00:00Z"))
        self.assertEqual(self.metric(value, "net_proceeds_roas_d30")["value"], 4)

    def test_adjustment_coverage_must_reach_as_of_even_after_horizon_matures(self):
        value = economics(definition(coverage_through="2026-10-08T00:00:00Z"))
        self.assertIsNone(self.metric(value)["value"])
        self.assertIn("ADJUSTMENT_COVERAGE_INCOMPLETE", self.codes(value))

    def test_late_refunds_and_reversals_apply_once_as_of_to_selected_purchase(self):
        events = [
            *rows(),
            event("refund", "REFUND", day="2026-09-20", amount=700, related="purchase"),
            event("reverse", "REFUND_REVERSED", day="2026-10-01", amount=200, related="refund"),
        ]
        value = economics(events=events + events)
        self.assertEqual(self.metric(value)["numerator_minor"], 1500)
        self.assertEqual(self.metric(value)["sample_counts"]["purchases"], 1)
        earlier = economics(events=events, as_of=iso_time("2026-09-21T00:00:00Z"))
        self.assertEqual(self.metric(earlier)["numerator_minor"], 1300)
        self.assertNotEqual(value["source_hash"], earlier["source_hash"])

    def test_unmatched_global_adjustment_and_conflicting_duplicates_block(self):
        for bad in (event("unmatched", "REFUND", amount=1, related="missing"), dict(rows()[1], amount_minor=1)):
            value = economics(events=[*rows(), bad])
            self.assertIsNone(self.metric(value)["value"])
        self.assertIn("EVENT_ID_CONFLICT", self.codes(economics(events=[*rows(), dict(rows()[1], amount_minor=1)])))

    def test_declaration_rejects_extra_missing_naive_and_unknown_fields(self):
        for value in (
            {},
            dict(contract(), extra=True),
            dict(contract(), coverage_through="2026-10-11"),
            dict(contract(), currency="usd"),
            dict(contract(), cost_basis="UNKNOWN"),
        ):
            with self.subTest(value=value), self.assertRaises(Invalid):
                validate_contract(value)

    def test_sqlite_app_scope_replay_and_export_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "ledger.sqlite")
            ledger = Ledger(store.path)
            ledger.define("sample-one", definition())
            ledger.define("sample-two", definition())
            ledger.ingest("sample-one", {"cohort_id": "pilot-1", "events": rows()})
            replay = ledger.ingest("sample-one", {"cohort_id": "pilot-1", "events": rows()})
            self.assertEqual(replay["duplicates"], 3)
            first = ledger.reports("sample-one", AS_OF.isoformat())[0]
            other = ledger.reports("sample-two", AS_OF.isoformat())[0]
            self.assertEqual(self.metric(first["economics"])["value"], 4)
            self.assertIsNone(self.metric(other["economics"])["value"])
            self.assertEqual(ledger.export("sample-one")["cohorts"][0]["economics"]["cost_basis"], "MEDIA_SPEND")
            self.assertEqual(Ledger(store.path).reports("sample-one", AS_OF.isoformat())[0], first)
