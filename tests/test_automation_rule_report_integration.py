"""Scheduled rules save exact existing private report selections, with no provider effects."""

import copy
import sqlite3
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from mission_control import automation_proposal_schedule as schedules
from mission_control import automation_proposals as proposals
from mission_control import automation_rule_report_integration as integration
from mission_control.automation_proposals import RuleRef, dismiss, inbox, run
from mission_control.automation_store import save
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.service import Service
from mission_control.store import Store
from tests import test_campaign_owner_reports as fixtures
from tests.test_automation_rules import EXAMPLE
from tests.test_ledger import cohort as event_cohort

START = datetime(2026, 11, 15, 7, tzinfo=timezone.utc)


class RuleReportIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.CampaignOwnerReportsTests(
            "test_private_report_immutable_hash_missing_kpis_and_no_effects"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.app = "sample"
        self.owner = "owner"
        self.template = self.fixture.capture()
        self.document = copy.deepcopy(EXAMPLE)
        self.document["mode"] = "AUTO_WITHIN_GRANT"
        self.document["rules"][1]["when"] = {"fact": "metrics.cohort_count", "op": "eq", "value": 0}
        self.report_ref = {"report_id": self.template["id"], "report_hash": self.template["hash"]}
        self.app_version: int = self.store.app(self.app)["version"]
        self.rule_ref = self.save_rules()
        self.body = {
            "enabled": True,
            "version": None,
            "app_version": self.app_version,
            "saved": self.rule_ref,
            "study": None,
            "interval_hours": 1,
            "expires_at": (START + timedelta(days=3)).isoformat(),
            "max_runs": 2,
            "report_integration": self.report_ref,
        }

    def save_rules(self) -> RuleRef:
        saved = save(self.store, self.app, {"principal": self.owner}, self.document)
        assert saved is not None
        return {"version": saved["version"], "hash": saved["hash"]}

    def enable(self, **changes: object) -> dict[str, object]:
        with patch.object(schedules, "now", return_value=START.isoformat()):
            return schedules.configure(self.store, self.app, self.owner, {**self.body, **changes})

    def receipts(self) -> list[sqlite3.Row]:
        with connection(self.store.path) as db:
            return db.execute(
                "SELECT * FROM campaign_owner_reports WHERE app_id=? AND owner=? ORDER BY rowid",
                (self.app, self.owner),
            ).fetchall()

    def test_match_saves_one_private_report_with_receipt_and_survives_restart(self) -> None:
        self.assertEqual(self.enable()["mode"], "SAVE_PRIVATE_REPORT")
        due = START + timedelta(hours=1)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: schedules.evaluate_due(self.store, self.app, due), range(2)))
        result = inbox(self.store, self.app, self.owner)
        self.assertIsNotNone(result["latest_run"])
        assert result["latest_run"] is not None
        receipt = result["latest_run"].get("integration")
        assert receipt is not None
        self.assertEqual(receipt["status"], "REPORT_SAVED")
        originals, generated = self.receipts()
        self.assertEqual(originals["id"], self.template["id"])
        self.assertEqual((generated["id"], generated["hash"]), (receipt.get("report_id"), receipt.get("report_hash")))
        state = schedules.read(self.store, self.app, self.owner)
        assert state is not None and isinstance(state["binding"], dict)
        self.assertEqual(generated["capture_key"], state["binding"]["report_integration"]["capture_key"])
        self.assertEqual(
            integration.report_view(generated)["report"]["selection"], self.template["report"]["selection"]
        )
        reopened = Store(Path(self.store.path), seed=False)
        schedules.evaluate_due(reopened, self.app, due + timedelta(hours=1))
        latest = inbox(reopened, self.app, self.owner)["latest_run"]
        assert latest is not None
        self.assertEqual((latest.get("integration") or {}).get("status"), "NO_NEW_MATCH")
        self.assertEqual(len(self.receipts()), 2)

    def test_stale_hash_foreign_report_or_advice_only_rule_cannot_arm(self) -> None:
        request = self.report_ref
        with self.assertRaisesRegex(Invalid, "private report changed"):
            self.enable(report_integration={**request, "report_hash": "e" * 64})
        foreign_id = str(uuid.uuid4())
        with connection(self.store.path, write=True) as db:
            db.execute(
                """INSERT INTO campaign_owner_reports
                   SELECT ?,app_id,'different-owner',plan_id,capture_key,data,hash,comparison_key,created
                   FROM campaign_owner_reports WHERE id=?""",
                (foreign_id, self.template["id"]),
            )
        with self.assertRaisesRegex(Invalid, "unavailable for this owner"):
            self.enable(report_integration={**request, "report_id": foreign_id})
        self.document["mode"] = "PROPOSE_ONLY"
        with self.assertRaisesRegex(Invalid, "AUTO_WITHIN_GRANT"):
            self.enable(saved=self.save_rules())
        self.document["mode"] = "AUTO_WITHIN_GRANT"
        self.document["rules"][1]["then"]["propose"]["tool"] = "campaign.outbox.publish"
        with self.assertRaisesRegex(Invalid, "AUTO_WITHIN_GRANT"):
            self.enable(saved=self.save_rules())
        self.assertIsNone(schedules.read(self.store, self.app, self.owner))
        self.assertEqual(len(self.receipts()), 1)

    def test_missing_match_never_dispatches_an_external_recommendation(self) -> None:
        self.document["rules"][1]["when"] = {"fact": "study.coverage", "op": "eq", "value": "COMPLETE"}
        self.document["rules"][2]["then"]["propose"]["tool"] = "campaign.outbox.publish"
        self.enable(saved=self.save_rules())
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        result = inbox(self.store, self.app, self.owner)
        self.assertEqual(result["proposals"][0]["proposal"]["tool"], "campaign.outbox.publish")
        assert result["latest_run"] is not None
        self.assertEqual((result["latest_run"].get("integration") or {}).get("status"), "NO_NEW_MATCH")
        self.assertEqual(len(self.receipts()), 1)

    def test_expiry_rolls_back_report_and_receipt_after_save(self) -> None:
        limit = START + timedelta(hours=3)
        self.enable(expires_at=limit.isoformat())
        with (
            patch.object(schedules, "now", side_effect=[(limit - timedelta(seconds=1)).isoformat(), limit.isoformat()]),
            patch.object(integration, "save_report", wraps=integration.save_report) as capture,
        ):
            schedules.evaluate_due(self.store, self.app)
        capture.assert_called_once()
        status = schedules.read(self.store, self.app, self.owner)
        assert status is not None
        self.assertEqual(status["status"], "EXPIRED")
        self.assertEqual(status["run_count"], 0)
        self.assertEqual(len(self.receipts()), 1)
        self.assertIsNone(inbox(self.store, self.app, self.owner)["latest_run"])

    def test_changed_template_stops_the_integration_atomically(self) -> None:
        self.enable()
        with connection(self.store.path, write=True) as db:
            db.execute("UPDATE campaign_owner_reports SET hash=? WHERE id=?", ("f" * 64, self.template["id"]))
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        status = schedules.read(self.store, self.app, self.owner)
        assert status is not None
        self.assertEqual(status["status"], "BLOCKED")
        self.assertEqual(len(self.receipts()), 1)
        self.assertIsNone(inbox(self.store, self.app, self.owner)["latest_run"])

    def test_existing_open_recommendation_integrates_once_but_dismissed_never_acts(self) -> None:
        with patch.object(proposals, "now", return_value=(START - timedelta(days=8)).isoformat()):
            baseline = run(self.store, self.app, self.owner, self.app_version, self.rule_ref)
        pending = inbox(self.store, self.app, self.owner)["proposals"]
        result = next(row["proposal"] for row in pending if row["proposal"]["action"] == "review_result")
        self.assertNotIn("integration", baseline)
        self.enable()
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        self.assertEqual(len(self.receipts()), 2)
        dismiss(self.store, self.app, self.owner, result["id"])
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=2))
        self.assertEqual(len(self.receipts()), 2)

    def test_dismissing_before_enabling_prevents_a_private_save(self) -> None:
        run(self.store, self.app, self.owner, self.app_version, self.rule_ref)
        pending = inbox(self.store, self.app, self.owner)["proposals"]
        result = next(row["proposal"] for row in pending if row["proposal"]["action"] == "review_result")
        dismiss(self.store, self.app, self.owner, result["id"])
        self.enable()
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        self.assertEqual(len(self.receipts()), 1)

    def test_recent_pending_recommendation_waits_through_cooldown(self) -> None:
        with patch.object(proposals, "now", return_value=START.isoformat()):
            run(self.store, self.app, self.owner, self.app_version, self.rule_ref)
        self.enable()
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        self.assertEqual(len(self.receipts()), 1)

    def test_unrelated_fact_change_does_not_save_a_second_report(self) -> None:
        self.document["rules"][1]["cooldown"] = ""
        self.enable(saved=self.save_rules())
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        real = proposals._project_snapshot
        with patch.object(proposals, "_project_snapshot", side_effect=lambda *args: {**real(*args), "unrelated": 1}):
            schedules.evaluate_due(self.store, self.app, START + timedelta(hours=2))
        self.assertEqual(len(self.receipts()), 2)
        latest = inbox(self.store, self.app, self.owner)["latest_run"]
        assert latest is not None
        self.assertTrue(any(item["status"] == "SAVED" for item in latest["proposals"]))
        status = schedules.read(self.store, self.app, self.owner)
        assert status is not None
        self.assertEqual(
            status["saved_report"], {"report_id": self.receipts()[-1]["id"], "report_hash": self.receipts()[-1]["hash"]}
        )

    def test_repeating_schedule_saves_distinct_evidence_up_to_the_owner_limit(self) -> None:
        self.fixture.cohort(activated=40)
        self.fixture.cohort(activated=25, identity="second-cohort")
        Service(self.store).cohort(self.app, event_cohort())
        self.document["rules"][1]["when"]["value"] = 2
        self.document["rules"][1]["cooldown"] = ""
        self.enable(
            saved=self.save_rules(),
            max_runs=6,
            report_integration={**self.report_ref, "max_reports": 2},
        )

        def tick(hours: int) -> None:
            stamp = START + timedelta(hours=hours)
            reopened = Store(Path(self.store.path), seed=False)
            with patch("mission_control.campaign_owner_reports.now", return_value=stamp.isoformat()):
                schedules.evaluate_due(reopened, self.app, stamp)

        tick(1)
        self.assertEqual(len(self.receipts()), 2)
        self.fixture.cohort(activated=40)  # Same evidence, new record version and timestamp.
        tick(2)
        self.assertEqual(len(self.receipts()), 2)
        self.fixture.cohort(activated=60)
        tick(3)
        reports = self.receipts()
        self.assertEqual(len(reports), 3)
        saved = integration.report_view(reports[-1])
        self.assertEqual(
            next(
                row["observed"]
                for row in saved["report"]["kpis"]["rows"]
                if row["metric"] == "Cohort 1: activation_rate"
            ),
            "0.6",
        )
        self.assertEqual(saved["report"]["comparison"]["previous_id"], reports[-2]["id"])
        latest = inbox(self.store, self.app, self.owner)["latest_run"]
        assert latest is not None
        self.assertEqual((latest.get("integration") or {}).get("report_hash"), saved["hash"])
        tick(3)
        self.fixture.cohort(activated=70)
        tick(4)
        self.assertEqual(len(self.receipts()), 3)
        status = schedules.read(self.store, self.app, self.owner)
        assert status is not None
        self.assertEqual(status["saved_report_count"], 2)
        self.assertEqual(status["saved_report"], {"report_id": saved["id"], "report_hash": saved["hash"]})

    def test_repeating_schedule_does_not_recapture_an_older_revision(self) -> None:
        self.fixture.cohort(activated=40)
        self.document["rules"][1]["when"]["value"] = 1
        self.document["rules"][1]["cooldown"] = ""
        self.enable(saved=self.save_rules(), max_runs=4, report_integration={**self.report_ref, "max_reports": 4})
        for hour, activations in enumerate((40, 60, 40), start=1):
            self.fixture.cohort(activated=activations)
            schedules.evaluate_due(self.store, self.app, START + timedelta(hours=hour))
        self.assertEqual(len(self.receipts()), 3)

    def test_report_limit_requires_exact_bounded_integer(self) -> None:
        for invalid in (None, True, 0, 3, 1.5, "2"):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(Invalid, "private report limit"):
                self.enable(report_integration={**self.report_ref, "max_reports": invalid})
        self.assertIsNone(schedules.read(self.store, self.app, self.owner))

    def test_partial_match_with_missing_branch_does_not_save(self) -> None:
        self.document["rules"][1]["when"] = {
            "any": [
                {"fact": "study.coverage", "op": "eq", "value": "COMPLETE"},
                {"fact": "metrics.cohort_count", "op": "eq", "value": 0},
            ]
        }
        self.enable(saved=self.save_rules())
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        latest = inbox(self.store, self.app, self.owner)["latest_run"]
        assert latest is not None
        self.assertTrue(any(row["status"] == "MATCH" and row["missing"] for row in latest["results"]))
        self.assertEqual(len(self.receipts()), 1)

    def test_study_dates_are_bound_without_equating_study_and_experiment_ids(self) -> None:
        study = {"study_id": "synthetic-study", "study_hash": "a" * 64, "manifest_version": self.app_version}
        window = self.template["report"]["selection"]["measurement_window"]
        with (
            patch.object(schedules, "_study_facts", return_value={"window": {**window, "ends_at": START.isoformat()}}),
            self.assertRaisesRegex(Invalid, "same dates"),
        ):
            self.enable(study=study)
        with patch.object(schedules, "_study_facts", return_value={"window": window}):
            self.assertEqual(self.enable(study=study)["mode"], "SAVE_PRIVATE_REPORT")

    def test_older_match_cannot_bypass_latest_action_cooldown(self) -> None:
        self.document["rules"][1]["cooldown"] = "PT2H"
        rules = self.save_rules()
        original = proposals._project_snapshot
        with patch.object(proposals, "now", return_value=(START - timedelta(hours=5)).isoformat()):
            run(self.store, self.app, self.owner, self.app_version, rules)
        with (
            patch.object(proposals, "_project_snapshot", side_effect=lambda *args: {**original(*args), "changed": 1}),
            patch.object(proposals, "now", return_value=START.isoformat()),
        ):
            run(self.store, self.app, self.owner, self.app_version, rules)
        self.enable(saved=rules)
        schedules.evaluate_due(self.store, self.app, START + timedelta(hours=1))
        self.assertEqual(len(self.receipts()), 1)
