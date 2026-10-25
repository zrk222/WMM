"""Real isolated SQLite journey imports, financial adjustments and legacy recovery."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.ledger import (Ledger, event_data, event_amount, cohort_data, write_cohort,
    write_events, csv_rows, restore_ledger, validate_snapshot, finance, apply_adjustment,
    eligible_events, funnel_counts, observed_rate)
from mission_control.db import connection
from mission_control.common import iso_time
from mission_control.subscription_journey import (binding_data, validate_event, chain_issues,
    same_charge_scope, group_counts, group_report, journey_report, matches, duration_data,
    stage_times, mature_conversion, payment_timing)
from mission_control.service import Service
from mission_control.store import Store
from tests.test_ledger import cohort, event


def bound(eid, kind, day="2026-09-03", amount=0, **changes):
    binding = dict(version=1, product_id="com.example.monthly", offer_id="STANDARD",
                   storefront="US", variant_id="control", configuration_sha256="a" * 64,
                   trial_days=3, billing_period_days=14)
    binding.update(changes.pop("binding", {}))
    return dict(event(eid, kind, day=day, amount=amount, **changes), subscription=binding)


class SubscriptionJourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "source/state.sqlite")
        self.service = Service(self.store)
        self.service.cohort("sample-one", cohort())
        self.ledger = Ledger(self.store.path)

    def tearDown(self):
        self.tmp.cleanup()

    def ingest(self, rows):
        return self.service.events("sample-one", {"cohort_id": "pilot-1", "events": rows})

    def report(self, stamp="2026-10-11T00:00:00+00:00"):
        return self.ledger.reports("sample-one", stamp)[0]

    def history(self):
        return [event("install", "INSTALL"), bound("onboard", "ONBOARDING_COMPLETE"),
                bound("wall", "PAYWALL_EXPOSURE"), bound("trial", "TRIAL_START"),
                bound("paid", "PURCHASE", day="2026-09-05", amount=1000),
                bound("renew", "RENEWAL", day="2026-09-20", amount=1000, related="paid"),
                event("ad", "COST_ACQUISITION", amount=100), event("delivery", "COST_DELIVERY", amount=100)]

    def test_trial_is_not_paid_and_zero_denominator_stays_unavailable(self):
        self.ingest(self.history()[:4])
        report = self.report()
        group = report["subscription_journey"]["groups"][0]
        self.assertEqual(report["paid"], 0)
        self.assertEqual(group["counts"]["TRIAL_START"], 1)
        self.assertEqual(group["trial_to_paid_rate"], 0)
        self.assertIsNone(group["first_renewal_rate"])
        self.assertFalse(report["subscription_journey"]["entitlement_verified"])

    def test_renewal_money_refund_and_cancel_intent(self):
        self.ingest(self.history() + [bound("cancel", "CANCEL_REQUEST", day="2026-09-21"),
                                   event("refund", "REFUND", day="2026-09-25", amount=300, related="renew")])
        result = self.report()
        self.assertEqual(result["paid"], 1)
        self.assertEqual(result["net_proceeds_minor"], 1700)
        group = result["subscription_journey"]["groups"][0]
        self.assertEqual(group["first_renewal_rate"], 1)
        self.assertEqual(group["counts"]["SUBSCRIPTION_END"], 0)
        self.assertEqual(group["counts"]["CANCEL_REQUEST"], 1)
        self.ingest([event("reversal", "REFUND_REVERSED", day="2026-09-26", amount=100, related="refund")])
        self.assertEqual(self.report()["net_proceeds_minor"], 1800)

    def test_atomic_validation_rejects_private_or_missing_bindings(self):
        bad = [bound("bad", "TRIAL_START", binding={"version": True}),
               bound("bad", "TRIAL_START", binding={"version": 2}),
               bound("bad", "TRIAL_START", binding={"product_id": "person@example.com"}),
               bound("bad", "TRIAL_START", binding={"configuration_sha256": "invalid"}),
               bound("bad", "TRIAL_START", binding={"offer_id": ""}),
               bound("bad", "TRIAL_START", subject="private@example.com"),
               bound("bad", "TRIAL_START", amount=100), bound("bad", "PURCHASE"),
               event("bad", "PAYWALL_EXPOSURE"), bound("bad", "INSTALL")]
        for row in bad:
            with self.subTest(row=row), self.assertRaises(Invalid):
                self.ingest([event("new", "INSTALL"), row])
            self.assertEqual(self.ledger.export("sample-one")["events"], [])

    def test_out_of_order_renewal_stays_inconclusive_until_parent_arrives(self):
        history = self.history()
        self.ingest([history[0], history[5], *history[6:]])
        self.assertIsNone(self.report()["net_proceeds_minor"])
        self.assertIn("Unresolved subscription renewal", self.report()["issues"][0])
        self.ingest(history[1:5])
        self.assertEqual(self.report()["net_proceeds_minor"], 2000)

    def test_scope_collision_maturity_and_deduplication(self):
        rows = self.history()
        self.ingest(rows)
        self.assertEqual(self.ingest(rows)["duplicates"], len(rows))
        with self.assertRaises(Invalid):
            self.ingest([bound("paid", "PURCHASE", amount=1000, binding={"variant_id": "other"})])
        immature = self.report("2026-09-10T00:00:00+00:00")["subscription_journey"]["groups"][0]
        self.assertIsNone(immature["trial_to_paid_rate"])
        with self.assertRaises(Invalid):
            self.service.events("sample-two", {"cohort_id": "pilot-1", "events": rows})
        self.ingest([bound("foreign-renew", "RENEWAL", day="2026-09-21", amount=1000, related="paid", binding={"product_id": "different"})])
        self.assertIsNone(self.report()["net_proceeds_minor"])

    def test_legacy_bytes_and_snapshot_hashes_survive_restart_restore(self):
        legacy = event_data(event("legacy", "PURCHASE", amount=100))
        self.assertNotIn("subscription", legacy)
        self.ingest(self.history() + [legacy])
        original = self.ledger.export("sample-one")
        self.assertEqual(Ledger(self.store.path).export("sample-one"), original)
        target = Store(Path(self.tmp.name) / "restored/state.sqlite", seed=False)
        target.restore(self.store.export("sample-one"))
        self.assertEqual(Ledger(target.path).export("sample-one"), original)
        self.assertEqual(Ledger(target.path).reports("sample-one", "2026-10-11T00:00:00+00:00"), [self.report()])

    def test_incompatible_variants_missing_installs_and_mixed_currency(self):
        self.ingest([event("install", "INSTALL"), bound("trial", "TRIAL_START"),
                     bound("paid-other", "PURCHASE", amount=1000, binding={"variant_id": "other"})])
        groups = self.report()["subscription_journey"]["groups"]
        self.assertEqual(len(groups), 2)
        self.assertTrue(all(g["trial_to_paid_subjects"] == 0 for g in groups))
        self.ingest([bound("no-install", "TRIAL_START", subject="absent")])
        self.assertTrue(self.report()["subscription_journey"]["issues"])
        self.ingest([bound("foreign", "PURCHASE", amount=100, currency="EUR")])
        self.assertIsNone(self.report()["net_proceeds_minor"])

    def test_event_amount_csv_rows_and_cohort_boundaries(self):
        self.assertEqual(event_amount("123", True), 123)
        for value in ("-1", "1.1", "", True):
            with self.assertRaises(Invalid):
                event_amount(value, True)
        with self.assertRaises(Invalid):
            csv_rows("provider,provider\na,b")
        with self.assertRaises(Invalid):
            cohort_data(cohort(matures_at="2026-08-01T00:00:00+00:00"))
        self.assertIsNone(observed_rate(0, 0, True))
        self.assertIsNone(observed_rate(1, 2, False))

    def test_write_cohort_write_events_restore_ledger_transaction_guards(self):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            with self.assertRaises(Invalid):
                write_cohort(db, "sample-one", cohort(release="changed"))
            row = event_data(event("one", "INSTALL"))
            self.assertEqual(write_events(db, "sample-one", "pilot-1", [row])["inserted"], 1)
            self.assertEqual(write_events(db, "sample-one", "pilot-1", [row])["duplicates"], 1)
            restore_ledger(db, "sample-one", None)
        with self.assertRaises(Invalid):
            validate_snapshot({"cohorts": [], "events": "invalid"})

    def test_finance_apply_adjustment_eligible_events_and_funnel_counts(self):
        rows = [event_data(r) for r in self.history()]
        start, end, maturity = [iso_time(cohort()[k]) for k in ("starts_at", "ends_at", "matures_at")]
        installers, eligible = eligible_events(rows, start, end)
        self.assertEqual(len(installers), 1)
        self.assertTrue(eligible)
        self.assertEqual(funnel_counts(rows, start, end, maturity)["paid"], 1)
        self.assertEqual(finance(rows, "USD")["net_proceeds_minor"], 2000)
        issues = []
        apply_adjustment(event_data(event("orphan", "REFUND", amount=20, related="missing")), {}, {}, {}, {}, issues)
        self.assertEqual(issues, ["Unresolved adjustment: orphan"])

    def test_binding_data_validate_event_and_chain_issues_boundaries(self):
        rows = [event_data(r) for r in self.history()]
        payment, renewal = rows[4:6]
        self.assertEqual(binding_data(payment["subscription"]), payment["subscription"])
        self.assertEqual(validate_event(payment), payment)
        self.assertFalse(matches(None, r"[A-Z]+"))
        self.assertTrue(same_charge_scope(payment, renewal))
        self.assertFalse(same_charge_scope(payment, dict(renewal, subject_id="other")))
        self.assertEqual(chain_issues([payment, renewal]), [])
        self.assertTrue(chain_issues([renewal]))

    def test_group_counts_group_report_and_journey_report_scoped_rates(self):
        rows = [event_data(r) for r in self.history()]
        supplied = [r for r in rows if "subscription" in r]
        self.assertEqual(group_counts(supplied)["renewed_subjects"], 1)
        stamp = iso_time("2026-10-11T00:00:00+00:00")
        group = group_report(supplied[0]["subscription"], supplied, cohort(observability="PARTIAL"), stamp, [])
        self.assertIsNone(group["first_renewal_rate"])
        report = journey_report(cohort(), rows, stamp)
        self.assertEqual(report["groups"][0]["trial_to_paid_rate"], 1)
        self.assertEqual(report["coverage"], "SUPPLIED_NOT_VERIFIED")

    def test_local_journey_has_no_network_or_entitlement_authority(self):
        with patch("socket.socket") as network:
            self.ingest(self.history())
            result = self.report()
            network.assert_not_called()
        self.assertFalse(result["subscription_journey"]["entitlement_verified"])

    def test_duration_data_stage_times_mature_conversion_and_payment_timing(self):
        rows = [event_data(r) for r in self.history()]
        binding = rows[1]["subscription"]
        duration_data(binding)
        with self.assertRaises(Invalid):
            duration_data(dict(binding, trial_days=True))
        self.assertEqual(stage_times(rows, "PURCHASE"), {"opaque-1": iso_time("2026-09-05T00:00:00+00:00")})
        cutoff = iso_time("2026-09-10T00:00:00+00:00")
        self.assertEqual(mature_conversion(rows, "PURCHASE", "RENEWAL", 14, cutoff), (0, 0))
        self.assertEqual(payment_timing(rows, {"opaque-1": iso_time(rows[0]["occurred_at"])}), 259200)
        self.ingest(self.history())
        group = self.report()["subscription_journey"]["groups"][0]
        self.assertEqual(group["median_seconds_to_first_payment"], 259200)
        self.assertEqual(group["mature_paid_subjects"], 1)


if __name__ == "__main__":
    unittest.main()
