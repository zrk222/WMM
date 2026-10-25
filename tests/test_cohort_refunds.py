"""Prove manual cohort arithmetic matches post-refund event-ledger semantics."""
import copy
from datetime import datetime
import unittest

from mission_control.ledger import report as ledger_report
from mission_control.metrics import cohort_metrics


STARTS_AT = "2026-09-01T00:00:00+00:00"
ENDS_AT = "2026-09-08T00:00:00+00:00"
MATURES_AT = "2026-10-01T00:00:00+00:00"
AS_OF = "2026-10-11T00:00:00+00:00"


def ledger_event(event_id, kind, amount_minor=0, related_event_id=""):
    return {
        "provider": "synthetic",
        "event_id": event_id,
        "type": kind,
        "subject_id": "opaque-user-1",
        "occurred_at": "2026-09-02T00:00:00+00:00",
        "amount_minor": amount_minor,
        "currency": "USD",
        "related_event_id": related_event_id,
        "source": "Synthetic in-memory refund parity fixture",
    }


def manual_cohort(refund_minor=0, installs=1, activated=1, paid=1,
                  acquisition_cost_minor=300, delivery_cost_minor=100):
    gross_purchase_minor = 2000 if paid else 0
    return {
        "cohort_id": "pilot-1",
        "currency": "USD",
        "horizon": "D30",
        "mature": True,
        "installs": installs,
        "activated": activated,
        "paid": paid,
        "acquisition_cost_minor": acquisition_cost_minor,
        "net_proceeds_minor": gross_purchase_minor - refund_minor,
        "delivery_cost_minor": delivery_cost_minor,
        "refunds_minor": refund_minor,
    }


def event_ledger(refund_minor=0, activity=True, as_of=AS_OF,
                 acquisition_cost_minor=300, delivery_cost_minor=100):
    cohort = {
        "cohort_id": "pilot-1",
        "release": "synthetic-build",
        "platform": "iOS",
        "locale": "en-US",
        "currency": "USD",
        "starts_at": STARTS_AT,
        "ends_at": ENDS_AT,
        "matures_at": MATURES_AT,
        "attribution_method": "Synthetic fixture",
        "observability": "OBSERVED",
        "source": "Synthetic in-memory parity fixture",
    }
    events = []
    if activity:
        events.extend((
            ledger_event("install", "INSTALL"),
            ledger_event("activation", "ACTIVATION"),
            ledger_event("purchase", "PURCHASE", 2000),
        ))
        if refund_minor:
            events.append(ledger_event("refund-1", "REFUND", refund_minor, "purchase"))
    events.extend((
        ledger_event("cost-acquisition", "COST_ACQUISITION", acquisition_cost_minor),
        ledger_event("cost-delivery", "COST_DELIVERY", delivery_cost_minor),
    ))
    return ledger_report(cohort, events, datetime.fromisoformat(as_of))


class CohortRefundSemanticsTests(unittest.TestCase):
    def test_manual_and_ledger_contribution_match_for_refund_cases(self):
        for refund_minor in (0, 500, 2000):
            with self.subTest(refund_minor=refund_minor):
                manual_data = manual_cohort(refund_minor=refund_minor)
                original_data = copy.deepcopy(manual_data)
                manual = cohort_metrics(manual_data)
                ledger = event_ledger(refund_minor=refund_minor)

                self.assertEqual(manual_data, original_data)
                self.assertEqual(manual["counts"]["refunds_minor"], refund_minor)
                self.assertEqual(ledger["refunds_minor"], refund_minor)
                self.assertEqual(manual["counts"]["net_proceeds_minor"], 2000 - refund_minor)
                self.assertEqual(manual["contribution_minor"],
                                 ledger["net_proceeds_minor"] - ledger["delivery_cost_minor"])
                self.assertEqual(manual["contribution_after_acquisition_minor"],
                                 ledger["contribution_after_acquisition_minor"])

    def test_zero_denominators_remain_null_and_match_ledger(self):
        manual = cohort_metrics(manual_cohort(
            installs=0, activated=0, paid=0, acquisition_cost_minor=0,
            delivery_cost_minor=0))
        ledger = event_ledger(
            activity=False, acquisition_cost_minor=0, delivery_cost_minor=0)

        self.assertEqual(ledger["status"], "SUPPLIED_RECONCILED")
        self.assertIsNone(manual["activation_rate"])
        self.assertIsNone(manual["paid_conversion"])
        self.assertIsNone(manual["paid_cac_minor"])
        self.assertIsNone(ledger["paid_cac_minor"])
        self.assertEqual(manual["contribution_after_acquisition_minor"],
                         ledger["contribution_after_acquisition_minor"])

    def test_immature_cohorts_are_inconclusive_without_contribution(self):
        manual_data = manual_cohort(refund_minor=500)
        manual_data["mature"] = False
        manual = cohort_metrics(manual_data)
        ledger = event_ledger(refund_minor=500, as_of="2026-09-20T00:00:00+00:00")

        self.assertEqual(manual["status"], "INCONCLUSIVE")
        self.assertNotIn("contribution_minor", manual)
        self.assertEqual(ledger["status"], "INCONCLUSIVE")
        self.assertFalse(ledger["mature"])
        self.assertIsNone(ledger["contribution_after_acquisition_minor"])


if __name__ == "__main__":
    unittest.main()
