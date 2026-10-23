"""Typed non-creative experiments using isolated SQLite and explicit synthetic billing proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.experiments import (Experiments, action_state, observe_state, decide_state,
    restore_experiments, restore_history, restore_transition, validate_assessment, validate_creative_hashes)
from mission_control.service import Service
from mission_control.store import Store
from mission_control.subscription_variants import (validate_configuration, event_binding,
    source_data, source_row, bind_subscription, validate_frozen_subscription, variant_findings,
    exposure_findings, event_findings, comparable_variants, validate_horizons, variant_input)
from tests.test_experiments import prepared, observations, REGISTER, EXPOSE, ANALYZE, LATER


def configuration(arm="control", **changes):
    value = dict(version=1, experiment_type="PAYWALL", access_method="HARD" if arm == "control" else "SOFT",
                 placement="AFTER_ONBOARDING", product_id="com.example.monthly", offer_id="STANDARD",
                 storefront="US", variant_id=arm, price_minor=1000, renewal_price_minor=1000,
                 currency="USD", trial_days=0, intro_days=0, billing_period_days=14, renewal_terms="Synthetic 14-day renewal at USD10; cancel before renewal")
    return dict(value, **changes)


class SubscriptionVariantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "source/state.sqlite")
        self.service = Service(self.store)
        self.experiments = Experiments(self.store)
        self.plan = prepared(self.store)
        self.sources = {}
        for arm in ("control", "treatment"):
            config = configuration(arm)
            record = self.store.save_record("sample-one", dict(kind="billing", title="Synthetic tested configuration",
                source="Synthetic fixture; no real provider eligibility", data=dict(release="build-1", platform="iOS", locale="en-US",
                    result="PASS", sku=config["product_id"], currency="USD", price_minor=1000, restore_tested=True,
                    trial_eligibility_tested=True, eligibility_status="ELIGIBLE", checked_at=REGISTER,
                    expires_at="2026-11-01T00:00:00+00:00", subscription_configuration=config)))
            self.sources[arm] = record
            self.plan[arm] = dict(variant_type="SUBSCRIPTION", cohort_id="experiment-" + arm,
                                  source_record_id=record["id"], configuration=config)

    def tearDown(self):
        self.tmp.cleanup()

    def create(self):
        with patch("mission_control.experiments.now", return_value=REGISTER):
            return self.experiments.create("sample-one", self.plan)

    def evaluate(self, changes=None):
        current = self.create()
        with patch("mission_control.experiments.now", return_value=EXPOSE):
            self.experiments.act("sample-one", current["id"], dict(operation="observe", version=1, source="Synthetic observed exposure", observed_at=EXPOSE))
        for arm in ("control", "treatment"):
            rows = observations(arm)
            for row in rows:
                if row["type"] == "PURCHASE":
                    row["subscription"] = event_binding(self.plan[arm]["configuration"])
            for n in range(20):
                wall = dict(rows[0], event_id=arm + "wall" + str(n), subject_id=arm + str(n), type="PAYWALL_EXPOSURE",
                            subscription=event_binding(self.plan[arm]["configuration"]))
                rows.append(wall)
            if changes:
                changes(arm, rows)
            self.service.events("sample-one", {"cohort_id": "experiment-" + arm, "events": rows})
        with patch("mission_control.experiments.now", return_value=ANALYZE):
            result = self.experiments.evaluate("sample-one", current["id"])
        return current, result

    def test_typed_registration_evaluation_and_snapshot_replay(self):
        current, result = self.evaluate()
        self.assertEqual(result["result"]["status"], "EVALUATED")
        self.assertNotIn("asset_id", current["data"]["control"])
        self.assertIn("unverified", result["result"]["reports"]["control"]["subscription_proof_scope"])
        restored = Store(Path(self.tmp.name) / "restored/state.sqlite", seed=False)
        restored.restore(self.store.export("sample-one"))
        self.assertEqual(Experiments(restored).list("sample-one"), self.experiments.list("sample-one"))

    def test_validate_configuration_event_binding_reject_unknown_and_ambiguous_terms(self):
        config = configuration()
        self.assertEqual(validate_configuration(config), config)
        self.assertEqual(event_binding(config)["configuration_sha256"], digest(config))
        for key, value in (("version", True), ("price_minor", True), ("currency", "usd"), ("trial_days", -1),
                           ("placement", "UNKNOWN"), ("renewal_terms", ""), ("access_method", []), ("intro_days", True)):
            with self.subTest(key=key), self.assertRaises(Invalid):
                validate_configuration(dict(config, **{key: value}))
        with self.assertRaises(Invalid):
            validate_configuration(dict(config, private="extra"))

    def test_source_row_source_data_bind_subscription_scope_and_expiry(self):
        with connection(self.store.path) as db:
            variant = bind_subscription(db, "sample-one", self.plan["control"], REGISTER)
            row = source_row(db, "sample-one", variant["source_record_id"])
            self.assertEqual(source_data(row, variant["configuration"], variant["cohort"], REGISTER)["eligibility_status"], "ELIGIBLE")
            validate_frozen_subscription(db, "sample-one", variant)
            self.assertEqual(variant_findings(db, "sample-one", variant, ANALYZE), [])
            self.assertTrue(variant_findings(db, "sample-one", variant, "2026-12-01T00:00:00+00:00"))
            with self.assertRaises(Invalid):
                bind_subscription(db, "sample-two", self.plan["control"], REGISTER)
            with self.assertRaises(Invalid):
                source_row(db, "sample-two", row["id"])

    def test_changed_or_failed_billing_evidence_blocks_registration_and_evaluation(self):
        current = self.create()
        old = self.sources["control"]
        self.store.save_record("sample-one", dict(old, data=dict(old["data"], eligibility_status="INELIGIBLE")))
        with self.assertRaises(Invalid):
            self.create()
        with connection(self.store.path) as db:
            self.assertTrue(variant_findings(db, "sample-one", current["data"]["control"], LATER))
        with patch("mission_control.experiments.now", return_value=EXPOSE), self.assertRaises(Invalid):
            self.experiments.act("sample-one", current["id"], dict(operation="observe", version=1, source="Synthetic exposure", observed_at=EXPOSE))

    def test_event_findings_and_exposure_findings_reject_configuration_mismatch(self):
        def change(arm, rows):
            if arm == "treatment":
                next(r for r in rows if r["type"] == "PURCHASE")["subscription"]["variant_id"] = "wrong"
        _, result = self.evaluate(change)
        self.assertEqual(result["result"]["status"], "INCONCLUSIVE")
        self.assertIsNone(result["result"]["effect"])
        self.assertTrue(result["result"]["reports"]["treatment"]["subscription_variant_issues"])
        self.assertTrue(exposure_findings([dict(type="INSTALL", subject_id="one")]))
        self.assertEqual(event_findings([], dict(self.plan["control"], cohort=current_cohort(self.store))), [])

    def test_comparable_variants_validate_horizons_and_variant_input(self):
        with connection(self.store.path) as db:
            control, treatment = [bind_subscription(db, "sample-one", self.plan[arm], REGISTER) for arm in ("control", "treatment")]
        comparable_variants(control, treatment)
        validate_horizons(control, ANALYZE)
        self.assertEqual(variant_input(control), self.plan["control"])
        with self.assertRaises(Invalid):
            comparable_variants(control, dict(treatment, configuration=dict(treatment["configuration"], price_minor=50)))
        with self.assertRaises(Invalid):
            comparable_variants(control, {"cohort_id": "creative", "asset_id": "image"})
        with self.assertRaises(Invalid):
            validate_horizons(dict(control, configuration=dict(control["configuration"], billing_period_days=366)), ANALYZE)

    def test_action_state_observe_state_decide_state_validate_assessment_denials(self):
        current = self.create()
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):
                action_state(db, current, {"operation": "launch"})
            with self.assertRaises(Invalid):
                decide_state(db, current, {"operation": "decide"})
        with self.assertRaises(Invalid):
            observe_state(current, dict(operation="observe", version=1, source="Synthetic", observed_at=REGISTER))
        with self.assertRaises(Invalid):
            validate_assessment(current, current, {"data": {"definition_hash": current["hash"]}})
        with self.assertRaises(Invalid):
            validate_creative_hashes({"asset_hash": "bad", "creative_sha256": "a" * 64})

    def test_restore_experiments_restore_history_restore_transition_atomic_denials(self):
        current, result = self.evaluate()
        saved = self.experiments.list("sample-one")[0]
        with connection(self.store.path) as db:
            restore_experiments(db, "sample-one", None)
            bad = copy.deepcopy(saved)
            bad["version"] += 1
            with self.assertRaises(Invalid):
                restore_history(db, "sample-one", bad)
            with self.assertRaises(Invalid):
                restore_transition(db, saved, 2, "assessment", {"data": {}})
        snapshot = self.store.export("sample-one")
        snapshot["payload"]["experiments"][0]["data"]["control"]["configuration"]["price_minor"] = 5
        snapshot["sha256"] = digest(snapshot["payload"])
        restored = Store(Path(self.tmp.name) / "tampered/state.sqlite", seed=False)
        with self.assertRaises(Invalid):
            restored.restore(snapshot)
        self.assertEqual(restored.apps(), [])

    def test_offer_comparison_late_refund_and_expired_source(self):
        c = dict(self.plan["control"], configuration=configuration(experiment_type="OFFER"))
        t = dict(self.plan["treatment"], configuration=configuration("treatment", experiment_type="OFFER", access_method="HARD", price_minor=100, offer_id="INTRO"))
        comparable_variants(c, t)
        current, result = self.evaluate()
        self.service.events("sample-one", {"cohort_id": "experiment-control", "events": [dict(
            provider="export", event_id="late-refund", type="REFUND", subject_id="", occurred_at="2026-10-05T00:00:00+00:00",
            amount_minor=1000, currency="USD", related_event_id="controlPURCHASE0", source="Synthetic late refund")]})
        with patch("mission_control.experiments.now", return_value=LATER):
            updated = self.experiments.evaluate("sample-one", current["id"])
        self.assertNotEqual(updated["hash"], result["hash"])
        self.assertEqual(updated["result"]["reports"]["control"]["refunds_minor"], 1000)
        with patch("mission_control.experiments.now", return_value="2026-12-01T00:00:00+00:00"):
            expired = self.experiments.evaluate("sample-one", current["id"])
        self.assertEqual(expired["result"]["status"], "BLOCKED")
        self.assertIsNone(expired["result"]["effect"])


def current_cohort(store):
    """Read the synthetic immutable control cohort for direct validator boundaries."""
    with connection(store.path) as db:
        return json.loads(db.execute("SELECT data FROM growth_cohorts WHERE app_id=? AND id=?", ("sample-one", "experiment-control")).fetchone()[0])
