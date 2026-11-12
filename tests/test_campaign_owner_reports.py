"""Private local reports over actual SQLite and synthetic saved campaign history.

The APIs exercise object_data, owned_resource, experiment_source, assessment_view,
effect_view, campaign_view, report_view, save_report, plan_view, checked_plan,
report_due and job_authority against actual persisted evidence and authority.
Static Forge name routing is not a behavioral coverage claim.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time
import unittest
import uuid
from unittest.mock import patch

from mission_control import campaign_owner_reports as core
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.worker import claim
from tests import test_campaign_monitor_integration as fixture

EXPERIMENT = "99999999-9999-4999-8999-999999999999"


def positive_effect():
    return dict(control_rate=0.2, treatment_rate=0.29, difference=0.09, interval=[0.06, 0.12], method="synthetic")


class CampaignOwnerReportsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.CampaignMonitorIntegrationTests(
            "test_real_owner_domain_post_and_protected_http_contract"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.monitor = self.fixture.activate()
        self.reports = core.Reports(self.store)
        mock = patch(
            "mission_control.campaign_transport.MetaTransport.request",
            side_effect=AssertionError("No provider reads"),
        )
        mock.start()
        self.addCleanup(mock.stop)
        mock = patch(
            "mission_control.agent_access.AgentAccess.secret",
            side_effect=AssertionError("No inference secrets"),
        )
        mock.start()
        self.addCleanup(mock.stop)
        mock = patch(
            "mission_control.social_secrets.Secrets.load",
            side_effect=AssertionError("No social secrets"),
        )
        mock.start()
        self.addCleanup(mock.stop)

    @contextmanager
    def owner(self):
        envelope = dict(app_id="sample", operation="campaign.owner-report.fixture", input={})
        with bound_owner(
            self.store,
            envelope,
            self.fixture.server.identities,
            self.fixture.client.csrf,
            dict(principal="owner"),
        ):
            with protected(self.store, envelope):
                yield

    def chosen(self, **changes):
        return dict(
            dict(
                scope_id=self.fixture.scope["scope_id"],
                monitor_id=self.monitor["id"],
                experiment_id=None,
                measurement_window=dict(
                    starts_at="2026-10-01T00:00:00+00:00",
                    ends_at="2026-11-01T00:00:00+00:00",
                ),
            ),
            **changes,
        )

    def capture(self, chosen=None, key=None):
        with self.owner():
            return self.reports.capture(
                "sample",
                dict(
                    selection=chosen or self.chosen(),
                    request_key=key or str(uuid.uuid4()),
                ),
            )

    def test_report_retains_pause_observation_and_rejects_rebound_receipts(self):
        flow = self.fixture.fixture.service
        intent = self.fixture.intent
        self.fixture.wire.objects[intent["ids"]["campaign"]]["effective_status"] = "PAUSED"
        paused = flow.run_pause("sample", "owner", self.fixture.scope["scope_id"], intent["id"])
        saved = self.capture()
        ad = next(r for r in saved["report"]["campaign"]["receipts"] if r["kind"] == "AD")
        self.assertEqual(
            ad["pause_readback"],
            {
                key: paused["pause_readback"][key]
                for key in ("configured_status", "effective_status", "observed_at", "sha256")
            },
        )
        self.assertEqual(saved["report"]["campaign"]["retained_commitment_minor"], 80)
        self.assertEqual(saved["report"]["campaign"]["spend"], "UNKNOWN_PROVIDER_REPORTS_MAY_LAG")
        with connection(self.store.path) as db:
            row = db.execute("SELECT data FROM campaign_pause_receipts").fetchone()
            import json

            damaged = json.loads(row["data"])
            damaged["scope_id"] = "foreign-scope"
            db.execute("UPDATE campaign_pause_receipts SET data=?,hash=?", (canonical(damaged), digest(damaged)))
        with self.assertRaises(Invalid):
            self.capture()

    def test_legacy_paused_state_has_no_invented_provider_receipt(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='PAUSED_campaign'")
        ad = next(r for r in self.capture()["report"]["campaign"]["receipts"] if r["kind"] == "AD")
        self.assertNotIn("pause_readback", ad)

    def test_invalid_pause_receipt_hash_time_and_identity_stop_capture(self):
        import json

        flow = self.fixture.fixture.service
        flow.run_pause("sample", "owner", self.fixture.scope["scope_id"], self.fixture.intent["id"])
        with connection(self.store.path) as db:
            original = json.loads(db.execute("SELECT data FROM campaign_pause_receipts").fetchone()["data"])
        for change in (
            {"observed_at": "not-a-date"},
            {"campaign_id": "999"},
            {"account_id": "999"},
            {"request_hash": "0" * 64},
            {"app_id": "foreign"},
            {},
        ):
            with self.subTest(change=change):
                data = {**original, **change}
                with connection(self.store.path) as db:
                    db.execute(
                        "UPDATE campaign_pause_receipts SET data=?,hash=?",
                        (canonical(data), digest(data) if change else "0" * 64),
                    )
                with self.assertRaises(Invalid):
                    self.capture()

    def plan(self, chosen=None, **changes):
        value = dict(
            selection=chosen or self.chosen(),
            cadence_seconds=30,
            expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            max_reports=2,
        )
        value.update(changes)
        with self.owner():
            draft = self.reports.prepare("sample", value)
            return self.reports.activate("sample", draft["id"], draft["summary_hash"])

    def experiment(self, analysis_at=None, status=None, window=None, effect=None, assessed_at=None):
        definition = dict(
            primary_metric="activation_rate",
            analysis_at=analysis_at or (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            control={"cohort": window} if window else {},
            treatment={"cohort": window} if window else {},
            minimum_detectable_effect=0.05,
        )
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",
                (
                    "sample",
                    EXPERIMENT,
                    canonical(definition),
                    digest(definition),
                    "OBSERVING",
                    1,
                    now(),
                    now(),
                ),
            )
            if status:
                assessment = dict(
                    status=status,
                    definition_hash=digest(definition),
                    diagnostics={"sample_ratio_chi_square": None},
                    guardrail_findings=[],
                    effect=effect,
                )
                db.execute(
                    "INSERT INTO experiment_assessments VALUES(?,?,?,?,?,?)",
                    (
                        "sample",
                        EXPERIMENT,
                        digest(assessment),
                        canonical(assessment),
                        assessed_at or now(),
                        1,
                    ),
                )
        return definition

    def cohort(self, activated=40, currency="CAD", identity="report-cohort"):
        data = dict(
            cohort_id="synthetic-cohort",
            currency=currency,
            installs=100,
            activated=activated,
            paid=10,
            mature=True,
            acquisition_cost_minor=5000,
            net_proceeds_minor=9000,
            delivery_cost_minor=1000,
            refunds_minor=0,
            horizon="30days",
        )
        old = next((r for r in self.store.records("sample") if r["id"] == identity), None)
        self.store.save_record(
            "sample",
            dict(
                id=identity,
                version=old["version"] if old else None,
                kind="cohort",
                title="Synthetic cohort",
                source="PRIVATE_SOURCE_LABEL",
                data=data,
            ),
        )

    def test_private_report_immutable_hash_missing_kpis_and_no_effects(self):
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0],
                0,
            )
        with self.assertRaises(PermissionError):
            self.reports.capture("sample", dict(selection=self.chosen(), request_key=str(uuid.uuid4())))
        result = self.capture()
        report = result["report"]
        self.assertEqual(result["hash"], digest(report))
        self.assertEqual(report["visibility"], "PRIVATE_OWNER_ONLY")
        self.assertFalse(report["authority_issued"])
        self.assertEqual(report["campaign"]["retained_commitment_minor"], 80)
        self.assertEqual(report["kpi_coverage"]["available_rows"], 0)
        self.assertGreater(report["kpi_coverage"]["unknown_rows"], 0)
        self.assertEqual(report["campaign"]["outcome_attribution"], "NOT_ESTABLISHED")
        self.assertEqual(report["kpis"]["appID"], "sample")
        self.assertIsNone(report["experiment"])
        self.assertEqual(report["comparison"]["status"], "NO_COMPATIBLE_PREVIOUS_SNAPSHOT")
        self.assertEqual(len(report["source_hash"]), 64)
        for private in (
            "synthetic-secret",
            "synthetic-token",
            "credential_ref",
            "PRIVATE_SOURCE_LABEL",
        ):
            self.assertNotIn(private, canonical(result))
        self.assertEqual(self.fixture.wire.posts, 1)
        self.assertEqual(len(self.fixture.wire.objects), 4)

    def test_workflow_activity_does_not_change_business_kpi_coverage(self):
        before = self.capture()["report"]
        stamp = now()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO creative_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample",
                    "synthetic-batch",
                    "synthetic-key",
                    "hash",
                    "PRIVATE_PLAN",
                    "hash",
                    "ACTIVE",
                    360,
                    stamp,
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO agent_handoffs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "synthetic-handoff",
                    "sample",
                    None,
                    "PRIVATE_RECIPIENT",
                    "PRIVATE_PAYLOAD",
                    "hash",
                    stamp,
                    stamp,
                    "READY",
                    None,
                    None,
                    1,
                ),
            )
        after = self.capture()["report"]
        self.assertEqual(before["kpi_coverage"], after["kpi_coverage"])
        self.assertEqual(after["kpi_coverage"]["available_rows"], 0)
        self.assertEqual(after["kpis"]["rows"], before["kpis"]["rows"])
        self.assertEqual(after["comparison"]["status"], "COMPATIBLE_SAVED_OBSERVATIONS")
        self.assertEqual(after["comparison"]["changes"], [])
        self.assertNotIn("PRIVATE_PAYLOAD", canonical(after))
        self.cohort()
        with_kpis = self.capture()["report"]
        self.assertGreater(with_kpis["kpi_coverage"]["available_rows"], 0)
        self.assertTrue(any(row["metric"].startswith("Cohort 1:") for row in with_kpis["kpis"]["rows"]))

    def test_capture_idempotent_key_and_selection_race(self):
        key = str(uuid.uuid4())
        first = self.capture(key=key)
        second = self.capture(key=key)
        self.assertEqual(first, second)
        window = dict(starts_at="2026-09-01T00:00:00+00:00", ends_at="2026-10-01T00:00:00+00:00")
        with self.assertRaises(Invalid):
            self.capture(self.chosen(measurement_window=window), key)
        with self.owner():
            self.assertEqual(self.reports.read("sample", first["id"]), first)

    def test_foreign_scope_monitor_experiment_and_revoked_owner_are_denied(self):
        for chosen in (
            self.chosen(scope_id=str(uuid.uuid4())),
            self.chosen(monitor_id=str(uuid.uuid4())),
            self.chosen(experiment_id=EXPERIMENT),
        ):
            with self.assertRaises(Invalid):
                self.capture(chosen)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_monitors SET owner='foreign-owner' WHERE id=?",
                (self.monitor["id"],),
            )
        with self.assertRaises(Invalid):
            self.capture()
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_monitors SET owner='owner' WHERE id=?",
                (self.monitor["id"],),
            )
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED' WHERE app_id='sample'")
        with self.assertRaises(PermissionError):
            self.capture()

    def test_unknown_pending_receipts_and_saved_monitor_observation_remain_unknown(
        self,
    ):
        from mission_control.campaign_monitor import tick

        tick(self.store)
        job = claim(self.store)
        observation = dict(
            status="BLOCKED",
            observations=[
                dict(
                    intent_id=self.fixture.intent["id"],
                    status="UNKNOWN",
                    recovery="ABANDONED_UNKNOWN",
                )
            ],
            private="SECRET_RESULT",
        )
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='BLOCKED',result=? WHERE id=?",
                (canonical(observation), job["id"]),
            )
            db.execute("UPDATE campaign_paid_intents SET status='PENDING_ACTIVE_campaign'")
        report = self.capture()["report"]
        self.assertEqual(report["monitor"]["last_observation"]["status"], "BLOCKED")
        self.assertEqual(
            report["monitor"]["last_observation"]["observations"][0]["status"],
            "UNKNOWN",
        )
        self.assertEqual(
            report["next_action"],
            "Inspect and reconcile the exact uncertain campaign receipts; do not replay mutations.",
        )
        self.assertNotIn("SECRET_RESULT", canonical(report))
        self.assertEqual(report["campaign"]["retained_commitment_minor"], 80)

    def test_blocked_monitor_with_verified_receipts_prioritizes_recovery_over_kpis(self):
        from mission_control.campaign_monitor import tick

        self.cohort()
        tick(self.store)
        job = claim(self.store)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='BLOCKED',result=? WHERE id=?",
                (canonical(dict(status="BLOCKED", observations=[])), job["id"]),
            )
            before_jobs = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        before_effects = canonical(self.fixture.wire.objects)
        with (
            patch.object(self.fixture.wire, "publish", side_effect=AssertionError("No publication")),
            patch.object(self.fixture.wire, "read_paid", side_effect=AssertionError("No provider read")),
            patch.object(self.fixture.wire, "set_paid_status", side_effect=AssertionError("No mutation")),
        ):
            report = self.capture()["report"]
        self.assertTrue(report["campaign"]["receipts"])
        self.assertEqual([r["status"] for r in report["campaign"]["receipts"]], ["ACTIVE_campaign"])
        self.assertEqual(report["monitor"]["last_observation"]["status"], "BLOCKED")
        self.assertGreater(report["kpi_coverage"]["available_rows"], 0)
        self.assertEqual(
            report["next_action"],
            "Inspect the blocked monitor and reconcile its saved campaign receipts; do not replay mutations.",
        )
        self.assertEqual(report["campaign"]["retained_commitment_minor"], 80)
        self.assertFalse(report["authority_issued"])
        self.assertEqual(canonical(self.fixture.wire.objects), before_effects)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], before_jobs)

    def test_blocked_report_plan_explains_failed_job_in_status_and_history(self):
        plan = self.plan()
        core.tick(self.store)
        job = claim(self.store)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE jobs SET status='FAILED',result=? WHERE id=?",
                (canonical(dict(diagnostic="PRIVATE_PROVIDER_DIAGNOSTIC")), job["id"]),
            )
            db.execute("UPDATE campaign_report_plans SET status='BLOCKED' WHERE id=?", (plan["id"],))
        with self.owner():
            status = self.reports.status("sample", plan["id"])
            history = self.reports.history("sample")
        self.assertIn("previous report snapshot", status["next_action"])
        self.assertEqual(history["plans"][0]["next_action"], status["next_action"])
        self.assertNotIn("PRIVATE_PROVIDER_DIAGNOSTIC", canonical(status))
        with connection(self.store.path) as db:
            before = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        self.assertEqual(core.tick(self.store), 0)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM jobs").fetchone()[0], before)

    def test_same_definition_window_previous_snapshot_descriptive_comparison(self):
        self.cohort()
        first = self.capture()
        self.cohort(activated=60)
        second = self.capture()
        comparison = second["report"]["comparison"]
        self.assertEqual(comparison["status"], "COMPATIBLE_SAVED_OBSERVATIONS")
        self.assertEqual(comparison["previous_id"], first["id"])
        row = next(
            r
            for r in comparison["changes"]
            if r["metric"] == "Cohort1: activation_rate" or r["metric"] == "Cohort 1: activation_rate"
        )
        self.assertEqual((row["previous"], row["current"]), ("0.4", "0.6"))
        self.assertNotEqual(first["report"]["source_hash"], second["report"]["source_hash"])
        self.cohort(activated=60, currency="USD")
        incompatible = self.capture()["report"]["comparison"]
        self.assertEqual(incompatible["status"], "NO_COMPATIBLE_PREVIOUS_SNAPSHOT")
        window = dict(starts_at="2026-09-01T00:00:00+00:00", ends_at="2026-10-01T00:00:00+00:00")
        self.assertEqual(
            self.capture(self.chosen(measurement_window=window))["report"]["comparison"]["status"],
            "NO_COMPATIBLE_PREVIOUS_SNAPSHOT",
        )

    def test_existing_experiment_maturity_and_assessment_no_new_evaluation(self):
        self.experiment(status="INCONCLUSIVE")
        report = self.capture(self.chosen(experiment_id=EXPERIMENT))["report"]
        self.assertEqual(report["experiment"]["maturity"], "AWAITING_ANALYSIS")
        self.assertEqual(report["experiment"]["assessment"]["status"], "INCONCLUSIVE")
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM experiment_assessments").fetchone()[0],
                1,
            )
        self.assertIsNone(report["experiment"]["assessment"]["effect"])

    def test_optional_monitor_and_app_kpis_do_not_substitute_for_primary_outcome(self):
        self.cohort()
        chosen = self.chosen(monitor_id=None)
        report = self.capture(chosen)["report"]
        self.assertGreater(report["kpi_coverage"]["available_rows"], 0)
        self.assertIn("Choose a primary outcome", report["next_action"])
        self.assertEqual(report["monitor"]["status"], "NOT_SELECTED")

    def test_saved_experiment_recommendation_requires_matching_mature_window(self):
        chosen = self.chosen(experiment_id=EXPERIMENT, monitor_id=None)
        window = chosen["measurement_window"]
        self.experiment(
            analysis_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            status="EVALUATED",
            window=dict(window, starts_at="2026-09-30T20:00:00-04:00"),
            effect=positive_effect(),
        )
        wrong_window = self.chosen(
            experiment_id=EXPERIMENT,
            monitor_id=None,
            measurement_window=dict(window, starts_at="2026-10-02T00:00:00+00:00"),
        )
        unmatched = self.capture(wrong_window)["report"]
        self.assertIn("exact acquisition dates", unmatched["next_action"])
        self.assertEqual(unmatched["experiment"]["review_window_alignment"], "NOT_MATCHED")
        matched = self.capture(chosen)["report"]
        self.assertIn("untouched holdout", matched["next_action"])
        self.assertTrue(matched["experiment"]["assessment_in_window"])

    def test_matching_report_rejects_assessment_saved_before_analysis(self):
        chosen = self.chosen(experiment_id=EXPERIMENT, monitor_id=None)
        self.experiment(
            analysis_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            assessed_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
            status="EVALUATED",
            window=chosen["measurement_window"],
            effect=positive_effect(),
        )
        report = self.capture(chosen)["report"]
        self.assertFalse(report["experiment"]["assessment_in_window"])
        self.assertIn("explicitly evaluate", report["next_action"])
        self.assertNotIn("untouched holdout", report["next_action"])

    def test_finite_plan_hash_activation_tick_restart_and_local_job_idempotency(self):
        plan = self.plan()
        self.assertEqual(core.tick(self.store), 1)
        self.assertEqual(core.tick(self.store), 0)
        job = claim(self.store)
        self.fixture.client.request("POST", "/api/identity/logout", {})
        first = core.execute(self.store, job)
        second = core.execute(self.store, job)
        self.assertEqual(first, second)
        self.assertEqual(first["plan_id"], plan["id"])
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0],
                1,
            )
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (job["id"],))
            db.execute("UPDATE campaign_report_plans SET due=0 WHERE id=?", (plan["id"],))
        restarted = core.Reports(self.store)
        self.assertIsNotNone(restarted)
        self.assertEqual(core.tick(self.store), 1)

    def test_finite_bounds_duplicate_tick_and_max_reports(self):
        with self.owner():
            for change in (
                dict(cadence_seconds=29),
                dict(max_reports=True),
                dict(expires_at=(datetime.now(timezone.utc) + timedelta(days=8)).isoformat()),
            ):
                with self.assertRaises(Invalid):
                    body = dict(
                        selection=self.chosen(),
                        cadence_seconds=30,
                        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                        max_reports=1,
                    )
                    body.update(change)
                    self.reports.prepare("sample", body)
        plan = self.plan(max_reports=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _: core.tick(self.store), range(2))), 1)
        job = claim(self.store)
        core.execute(self.store, job)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED' WHERE id=?", (job["id"],))
            db.execute("UPDATE campaign_report_plans SET due=0 WHERE id=?", (plan["id"],))
        self.assertEqual(core.tick(self.store), 0)
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT status FROM campaign_report_plans WHERE id=?", (plan["id"],)).fetchone()[0],
                "BLOCKED",
            )
        with self.owner():
            status = self.reports.status("sample", plan["id"])
            history = self.reports.history("sample")
        self.assertIn("report limit", status["next_action"])
        self.assertEqual(history["plans"][0]["next_action"], status["next_action"])

    def test_blocked_plan_expiry_and_changed_binding_recommend_review(self):
        plan = self.plan()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_report_plans SET status='BLOCKED' WHERE id=?", (plan["id"],))
            db.execute("UPDATE campaign_scopes SET summary_hash='changed' WHERE app_id='sample'")
        with self.owner():
            changed = self.reports.status("sample", plan["id"])
        self.assertTrue(
            any(phrase in changed["next_action"] for phrase in ("binding changed", "could not be confirmed"))
        )

    def test_blocked_expired_plan_recommends_review(self):
        plan = self.plan()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_report_plans SET status='BLOCKED' WHERE id=?", (plan["id"],))
            row = db.execute("SELECT summary FROM campaign_report_plans WHERE id=?", (plan["id"],)).fetchone()
            summary = core.object_data(row["summary"])
            summary["proposal"]["expires_at"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            db.execute(
                "UPDATE campaign_report_plans SET summary=?,summary_hash=? WHERE id=?",
                (canonical(summary), digest(summary), plan["id"]),
            )
        with self.owner():
            expired = self.reports.status("sample", plan["id"])
        self.assertIn("expired", expired["next_action"])

    def test_blocked_tampered_plan_does_not_trust_expiry_or_leak_summary(self):
        plan = self.plan()
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_report_plans SET status='BLOCKED',summary=?,summary_hash='tampered' WHERE id=?",
                (canonical(dict(proposal=dict(expires_at="2000-01-01T00:00:00+00:00", private="SECRET"))), plan["id"]),
            )
        with self.owner():
            status = self.reports.status("sample", plan["id"])
        self.assertIn("could not be verified", status["next_action"])
        self.assertNotIn("SECRET", canonical(status))

    def test_job_authority_host_lease_inputs_owner_and_app_source_checks(self):
        plan = self.plan()
        core.tick(self.store)
        job = claim(self.store)
        wrong = dict(job, data=dict(job["data"], run=2))
        with self.assertRaises(PermissionError):
            core.execute(self.store, wrong)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=0 WHERE id=?", (job["id"],))
        with self.assertRaises(PermissionError):
            core.execute(self.store, job)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET lease=? WHERE id=?", (time.time() + 60, job["id"]))
            db.execute("UPDATE apps SET version=version+1 WHERE id='sample'")
        with self.assertRaises(PermissionError):
            core.execute(self.store, job)
        self.assertEqual(core.tick(self.store), 0)
        self.assertIsNotNone(plan)

    def test_off_plan_and_expiry_stop_no_implicit_reports(self):
        plan = self.plan()
        core.tick(self.store)
        with self.owner():
            off = self.reports.off("sample", plan["id"], plan["version"])
        self.assertEqual(off["status"], "OFF")
        self.assertIsNone(claim(self.store))
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0],
                0,
            )
        with self.owner():
            self.assertEqual(len(self.reports.history("sample")["plans"]), 1)

    def test_source_summary_tamper_and_snapshot_role_race_roll_back_capture(self):
        original = core.snapshot

        def revoke(db, store, app_id, observed, **kwargs):
            result = original(db, store, app_id, observed, **kwargs)
            db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id='sample'")
            return result

        with patch.object(core, "snapshot", side_effect=revoke):
            with self.assertRaises((Invalid, PermissionError)):
                self.capture()
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0],
                0,
            )
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_scopes SET summary_hash='changed'")
        with self.assertRaises(Invalid):
            self.capture()

    def test_historical_off_expired_sources_remain_reportable_and_custom_experiment_id(
        self,
    ):
        self.experiment(status="INCONCLUSIVE")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("PRAGMA defer_foreign_keys=ON")
            db.execute("UPDATE experiments SET id='appgrowth-trial' WHERE id=?", (EXPERIMENT,))
            db.execute(
                "UPDATE experiment_assessments SET experiment_id='appgrowth-trial' WHERE experiment_id=?",
                (EXPERIMENT,),
            )
            db.execute("UPDATE campaign_scopes SET status='REVOKED'")
            db.execute("UPDATE campaign_monitors SET status='OFF'")
        result = self.capture(self.chosen(experiment_id="appgrowth-trial"))
        self.assertEqual(result["report"]["experiment"]["id"], "appgrowth-trial")
        self.assertEqual(result["report"]["campaign"]["status"], "REVOKED")
        self.assertIn("historical", result["report"]["next_action"])
        with self.assertRaises(Invalid):
            self.capture(self.chosen(experiment_id="missing-custom-trial"))

    def test_metric_definitions_ignore_observed_values_but_bind_units_and_window(self):
        self.cohort()
        first = self.capture()
        self.cohort(activated=50)
        second = self.capture()
        self.assertEqual(
            first["report"]["kpi_coverage"]["metric_definitions_hash"],
            second["report"]["kpi_coverage"]["metric_definitions_hash"],
        )
        self.assertEqual(second["report"]["comparison"]["status"], "COMPATIBLE_SAVED_OBSERVATIONS")

    def test_exact_plan_approval_hash_and_twenty_due_job_bound(self):
        proposal = dict(
            selection=self.chosen(),
            cadence_seconds=30,
            expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            max_reports=1,
        )
        with self.owner():
            draft = self.reports.prepare("sample", proposal)
            with self.assertRaises(Invalid):
                self.reports.activate("sample", draft["id"], "0" * 64)
            self.assertEqual(self.reports.status("sample", draft["id"])["status"], "DRAFT")
            self.reports.activate("sample", draft["id"], draft["summary_hash"])
        for unused in range(20):
            self.plan(max_reports=1)
        self.assertEqual(core.tick(self.store), 20)
        self.assertEqual(core.tick(self.store), 1)
        self.assertEqual(core.tick(self.store), 0)
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM jobs WHERE action='campaign_owner_report'").fetchone()[0],
                21,
            )

    def test_revoked_role_blocks_queued_report_without_persisting_private_snapshot(
        self,
    ):
        self.plan()
        core.tick(self.store)
        job = claim(self.store)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id='sample'")
        with self.assertRaises(PermissionError):
            core.execute(self.store, job)
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0],
                0,
            )
        self.assertEqual(core.tick(self.store), 0)

    def test_scope_expiry_is_observation_not_report_authority_expiry(self):
        plan = self.plan()
        future = datetime.fromisoformat(self.fixture.scope["expires_at"]).timestamp() + 1
        with (
            patch("time.time", return_value=future),
            patch.object(
                core,
                "now",
                return_value=datetime.fromtimestamp(future, timezone.utc).isoformat(),
            ),
        ):
            self.assertEqual(core.tick(self.store), 1)
            job = claim(self.store)
            result = core.execute(self.store, job)
        self.assertEqual(result["plan_id"], plan["id"])
        self.assertIn("historical", result["report"]["next_action"])
        self.assertFalse(result["report"]["authority_issued"])

    def test_real_http_owner_capture_read_and_plan_prepare_closed_inputs(self):
        from mission_control import server as http
        from mission_control.operator_client import ClientError, OperatorClient

        route = "/api/apps/sample/campaign-owner-reports/"
        original = http.owner_domain_post

        def router(parts):
            if len(parts) > 3 and parts[3] == "campaign-owner-reports":
                return core.post
            return original(parts)

        with patch.object(http, "owner_domain_post", side_effect=router):
            anonymous = OperatorClient(self.fixture.client.origin)
            anonymous.bootstrap()
            with self.assertRaises(ClientError):
                anonymous.request("POST", route + "history", {})
            saved = self.fixture.client.request(
                "POST",
                route + "capture",
                dict(selection=self.chosen(), request_key=str(uuid.uuid4())),
            )
            read = self.fixture.client.request("POST", route + "read", dict(report_id=saved["id"]))
            self.assertEqual(saved, read)
            self.assertEqual(
                len(self.fixture.client.request("POST", route + "history", {})["reports"]),
                1,
            )
            with self.assertRaises(ClientError):
                self.fixture.client.request("POST", route + "read", dict(report_id=saved["id"], owner="forged"))
            self.assertFalse(saved["report"]["authority_issued"])

    def test_wrong_host_plan_tamper_expiry_and_foreign_job_fail_closed(self):
        plan = self.plan()
        core.tick(self.store)
        job = claim(self.store)
        with patch.object(core, "store_identity", return_value="another-store"):
            with self.assertRaises(PermissionError):
                core.execute(self.store, job)
        with patch("time.time", return_value=time.time() + 8 * 86400):
            with self.assertRaises(PermissionError):
                core.execute(self.store, job)
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_report_plans SET summary_hash='changed' WHERE id=?",
                (plan["id"],),
            )
        with self.assertRaises(PermissionError):
            core.execute(self.store, job)


if __name__ == "__main__":
    unittest.main()
