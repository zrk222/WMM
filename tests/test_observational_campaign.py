"""Durable synthetic lifecycle tests for one-arm observational attribution."""
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.observational_campaign import ObservationalCampaign
from mission_control.operation_authority import PROTECTED
from mission_control.store import Store

APP = "sample-one"
STUDY = "11111111-1111-4111-8111-111111111111"
REQUEST = "22222222-2222-4222-8222-222222222222"
SOURCE_RECEIPT = "a" * 64


class ObservationalCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "campaign.sqlite", seed=False)
        self.store.save_app(APP, {"name": "Synthetic app", "website": "https://example.test/home", "release": "r1"})
        self.service = ObservationalCampaign(self.store)
        self._ensure_tables()
        self.authority = "synthetic-owner"
        self._real_context = None
        self.clock = datetime(2030, 1, 1, tzinfo=timezone.utc)
        self._clock_patch = patch("mission_control.observational_campaign.now", side_effect=self._now)
        self._clock_patch.start()
        self.addCleanup(self._clock_patch.stop)

    def _now(self):
        return self.clock.isoformat().replace("+00:00", "Z")

    def _set_context(self, action, body, app_id=APP):
        self._real_context = PROTECTED.get()
        PROTECTED.set({"store": str(self.store.path.resolve()), "envelope": canonical({"app_id": app_id, "operation": "observational-campaign." + action, "input": body})})

    def _clear_context(self):
        PROTECTED.set(self._real_context)

    def invoke(self, action, body):
        if action == "ingest":
            self.clock += timedelta(seconds=30)
        self._set_context(action, body)
        try:
            with patch("mission_control.operation_authority.check", return_value=self.authority):
                return self.service.dispatch(APP, action, body)
        finally:
            self._clear_context()

    def definition(self, **changes):
        start = self.clock + timedelta(seconds=13)
        value = {"id": STUDY, "name": "Organic post", "hypothesis": "Tagged post visits can be linked to registration.",
                 "source": "facebook", "creative_id": "creative_1", "landing_path": "/start",
                 "starts_at": start.isoformat(), "ends_at": (start + timedelta(days=10)).isoformat(),
                 "landing_event": "landing", "registration_event": "registration", "attribution_model": "FIRST_TOUCH"}
        value.update(changes)
        return value

    def register(self, **definition):
        app = self.store.app(APP)
        index = self.count("observational_campaign_studies")
        study_id = f"{index + 1:08d}-1111-4111-8111-111111111111"
        request_id = f"{index + 1:08d}-2222-4222-8222-222222222222"
        body = {"request_id": request_id, "manifest_version": app["version"], "definition": self.definition(id=study_id, **definition)}
        receipt = self.invoke("register", body)
        return body, receipt

    def scoped(self, receipt, action, **data):
        app = self.store.app(APP)
        body = {"study_id": receipt["study_id"], "study_hash": receipt["study_hash"], "manifest_version": app["version"], **data}
        return body

    def event(self, receipt, event_id, subject, kind, occurred_at=None, **changes):
        start = self.store.app(APP)["data"].get("release")
        study_row = self.db_row(receipt["study_id"])
        when = occurred_at or (self.clock + timedelta(seconds=12)).isoformat()
        value = {"event_id": event_id, "subject_id": subject, "type": kind, "occurred_at": when,
                 "campaign_token": receipt["study_id"], "consent": "GRANTED", "bot": False, "internal_test": False}
        value.update(changes)
        return value

    def db_row(self, study_id):
        with connection(self.store.path) as db:
            return db.execute("SELECT data,hash FROM observational_campaign_studies WHERE app_id=? AND study_id=?", (APP, study_id)).fetchone()

    def batch(self, receipt, events, batch_id="33333333-3333-4333-8333-333333333333", source_id="wize-api", complete=True, coverage_count=None):
        if coverage_count is None:
            coverage_count = {kind: sum(1 for event in events if event["type"] == kind) for kind in ("LANDING", "REGISTRATION")}
        return {"batch_id": batch_id, "study_id": receipt["study_id"], "study_hash": receipt["study_hash"],
                "app_version": self.store.app(APP)["version"], "source_id": source_id,
                "source_receipt_sha256": SOURCE_RECEIPT, "observed_at": (self.clock + timedelta(seconds=30)).isoformat(),
                "coverage": {kind: {"complete": complete, "source_event_count": coverage_count[kind] if complete else None}
                             for kind in ("LANDING", "REGISTRATION")}, "events": events}

    def test_registration_is_local_immutable_plan_and_url_is_canonical(self):
        body, receipt = self.register()
        self.assertEqual(receipt["status"], "REGISTERED")
        self.assertNotIn("launch", receipt)
        repeated = self.invoke("register", body)
        self.assertTrue(repeated["idempotent"])
        link = self.invoke("link", self.scoped(receipt, "link"))
        self.assertEqual(link["url"].count("&") + 1, 4)
        self.assertIn("utm_campaign=" + receipt["study_id"], link["url"])

    def test_no_context_rejected_and_wrong_app_or_action_context_rejected(self):
        with self.assertRaises(PermissionError):
            self.service.dispatch(APP, "history", {})
        body, receipt = self.register()
        wrong = self.scoped(receipt, "report")
        self._set_context("ingest", wrong)
        try:
            with self.assertRaises(PermissionError):
                self.service.report(APP, wrong)
        finally:
            self._clear_context()
        self._set_context("report", wrong, "other-app")
        try:
            with self.assertRaises(PermissionError):
                self.service.report(APP, wrong)
        finally:
            self._clear_context()

    def test_landing_registration_join_out_of_order_and_unknown_versus_complete_zero(self):
        _, receipt = self.register()
        start = self.clock + timedelta(seconds=13)
        landing = self.event(receipt, "landing1", "subject1", "LANDING", start.isoformat())
        registration = self.event(receipt, "register1", "subject1", "REGISTRATION", (start + timedelta(seconds=1)).isoformat())
        another_landing = self.event(receipt, "landing2", "subject2", "LANDING", start.isoformat())
        repeated_subject = self.event(receipt, "landing3", "subject2", "LANDING", start.isoformat())
        body = self.scoped(receipt, "ingest", batch=self.batch(receipt, [registration, landing, another_landing, repeated_subject]))
        self.invoke("ingest", body)
        report = self.invoke("report", self.scoped(receipt, "report"))
        self.assertEqual(report["landing_subjects"], 2)
        self.assertEqual(report["linked_registration_subjects"], 1)
        self.assertEqual(report["status"], "ATTRIBUTED_DESCRIPTIVE_ONLY")
        self.assertEqual(report["checkpoint"]["state"], "SOURCE_NOT_DECLARED")
        self.assertIsNone(report["checkpoint"]["ratio_counts"])
        self.assertNotIn("lift", report)
        self.assertEqual(report["provenance"], "SOURCE_REPORTED_NOT_PROVIDER_VERIFIED")

        _, empty_receipt = self.register()
        empty_batch = self.batch(empty_receipt, [], batch_id="44444444-4444-4444-8444-444444444444", complete=False)
        self.invoke("ingest", self.scoped(empty_receipt, "ingest", batch=empty_batch))
        unknown = self.invoke("report", self.scoped(empty_receipt, "report"))
        self.assertIsNone(unknown["landing_subjects"])
        complete_batch = self.batch(empty_receipt, [], batch_id="55555555-5555-4555-8555-555555555555", complete=True)
        self.invoke("ingest", self.scoped(empty_receipt, "ingest", batch=complete_batch))
        zero = self.invoke("report", self.scoped(empty_receipt, "report"))
        self.assertEqual(zero["landing_subjects"], 0)

    def test_declared_collector_must_reconcile_both_event_types_after_close(self):
        definition, receipt = self.register(collector_source_id="wize-api")
        start = self.clock + timedelta(seconds=13)
        events = [self.event(receipt, "land-a", "a", "LANDING", start.isoformat()),
                  self.event(receipt, "land-b", "b", "LANDING", start.isoformat()),
                  self.event(receipt, "reg-a", "a", "REGISTRATION", (start + timedelta(seconds=1)).isoformat()),
                  self.event(receipt, "unmatched", "c", "REGISTRATION", (start + timedelta(seconds=1)).isoformat())]
        with self.assertRaisesRegex(Invalid, "differs from the collector"):
            self.invoke("ingest", self.scoped(receipt, "ingest", batch=self.batch(receipt, events, source_id="other")))
        self.assertEqual(self.count("observational_campaign_batches"), 0)
        self.invoke("ingest", self.scoped(receipt, "ingest", batch=self.batch(receipt, events)))
        binding = self.scoped(receipt, "report")
        early = self.invoke("report", binding)
        self.assertEqual(early["checkpoint"]["state"], "COLLECTING")
        self.assertFalse(early["coverage"]["LANDING"]["coverage_complete"])
        self.assertIsNone(early["checkpoint"]["ratio_counts"])
        self.clock = datetime.fromisoformat(definition["definition"]["ends_at"]) + timedelta(seconds=1)
        overdue = self.invoke("report", binding)
        self.assertEqual(overdue["checkpoint"]["state"], "COVERAGE_INCOMPLETE")
        self.assertEqual(overdue["checkpoint"]["coverage_issues"],
                         {"LANDING": "BEFORE_CLOSE", "REGISTRATION": "BEFORE_CLOSE"})
        final = self.batch(receipt, [], batch_id="44444444-4444-4444-8444-444444444444",
                           coverage_count={"LANDING": 2, "REGISTRATION": 2})
        self.invoke("ingest", self.scoped(receipt, "ingest", batch=final))
        ready = self.invoke("report", binding)
        self.assertEqual(ready["checkpoint"]["state"], "DESCRIPTIVE_READY")
        self.assertEqual(ready["checkpoint"]["ratio_counts"], {"linked_registrations": 1, "eligible_landings": 2})
        self.assertEqual(ready["exclusions"]["UNMATCHED_REGISTRATION"], 1)
        self.assertNotEqual(overdue["source_hash"], ready["source_hash"])
        mismatch = self.batch(receipt, [], batch_id="55555555-5555-4555-8555-555555555555",
                              coverage_count={"LANDING": 2, "REGISTRATION": 1})
        self.invoke("ingest", self.scoped(receipt, "ingest", batch=mismatch))
        current = self.invoke("report", binding)
        self.assertEqual(current["checkpoint"]["coverage_issues"], {"REGISTRATION": "COUNT_MISMATCH"})
        self.assertIsNone(current["checkpoint"]["ratio_counts"])

    def test_missing_coverage_and_reconciled_zero_are_distinct(self):
        definition, receipt = self.register(collector_source_id="wize-api")
        self.clock = datetime.fromisoformat(definition["definition"]["ends_at"]) + timedelta(seconds=1)
        binding = self.scoped(receipt, "report")
        missing = self.invoke("report", binding)
        self.assertEqual(missing["checkpoint"]["coverage_issues"],
                         {"LANDING": "MISSING_RECEIPT", "REGISTRATION": "MISSING_RECEIPT"})
        self.assertIsNone(missing["landing_subjects"])
        self.invoke("ingest", self.scoped(receipt, "ingest", batch=self.batch(receipt, [])))
        complete = self.invoke("report", binding)
        self.assertEqual(complete["checkpoint"]["state"], "NO_ELIGIBLE_LANDINGS")
        self.assertEqual((complete["landing_subjects"], complete["linked_registration_subjects"]), (0, 0))
        self.assertIsNone(complete["checkpoint"]["ratio_counts"])

    def test_exclusions_explicit_and_bot_false_not_human_claim(self):
        _, receipt = self.register()
        start = self.clock + timedelta(seconds=13)
        events = [
            self.event(receipt, "ok", "s1", "LANDING", start.isoformat()),
            self.event(receipt, "denied", "s2", "LANDING", start.isoformat(), consent="DENIED"),
            self.event(receipt, "unknown-consent", "s3", "LANDING", start.isoformat(), consent="UNKNOWN"),
            self.event(receipt, "unknown-bot", "s4", "LANDING", start.isoformat(), bot=None),
            self.event(receipt, "test", "s5", "LANDING", start.isoformat(), internal_test=True),
            self.event(receipt, "missing-token", "s6", "LANDING", start.isoformat(), campaign_token=None),
            self.event(receipt, "wrong-token", "s7", "LANDING", start.isoformat(), campaign_token="66666666-6666-4666-8666-666666666666"),
            self.event(receipt, "unmatched", "s8", "REGISTRATION", start.isoformat()),
        ]
        body = self.scoped(receipt, "ingest", batch=self.batch(receipt, events))
        self.invoke("ingest", body)
        report = self.invoke("report", self.scoped(receipt, "report"))
        self.assertEqual(report["landing_subjects"], 1)
        self.assertEqual(report["linked_registration_subjects"], 0)
        self.assertEqual(report["exclusions"]["CONSENT_DENIED"], 1)
        self.assertEqual(report["exclusions"]["CONSENT_UNKNOWN"], 1)
        self.assertEqual(report["exclusions"]["BOT_UNKNOWN"], 1)
        self.assertEqual(report["exclusions"]["INTERNAL_TEST"], 1)
        self.assertEqual(report["exclusions"]["TOKEN_MISSING"], 1)
        self.assertEqual(report["exclusions"]["TOKEN_INVALID"], 1)
        self.assertEqual(report["exclusions"]["UNMATCHED_REGISTRATION"], 1)
        self.assertIn("bot=false is not proof of a human.", report["limits"])

    def test_exact_batch_retry_conflict_is_atomic_and_source_mismatch_stays_incomplete(self):
        _, receipt = self.register()
        when = self.clock + timedelta(seconds=13)
        events = [self.event(receipt, "first", "s1", "LANDING", when.isoformat()), self.event(receipt, "second", "s2", "LANDING", when.isoformat())]
        batch = self.batch(receipt, events)
        first = self.invoke("ingest", self.scoped(receipt, "ingest", batch=batch))
        retry = self.invoke("ingest", self.scoped(receipt, "ingest", batch=copy.deepcopy(batch)))
        self.assertEqual(first, retry)
        self.assertEqual(first["inserted"], 2)

        changed = copy.deepcopy(batch)
        changed["events"][0]["subject_id"] = "tampered"
        with self.assertRaises(Invalid):
            self.invoke("ingest", self.scoped(receipt, "ingest", batch=changed))
        collision = self.batch(receipt, [dict(events[0], subject_id="different")], batch_id="77777777-7777-4777-8777-777777777777")
        before = self.count("observational_campaign_events")
        with self.assertRaises(Invalid):
            self.invoke("ingest", self.scoped(receipt, "ingest", batch=collision))
        self.assertEqual(self.count("observational_campaign_events"), before)

        mismatch = self.batch(receipt, [], batch_id="88888888-8888-4888-8888-888888888888", coverage_count={"LANDING": 1, "REGISTRATION": 0})
        self.invoke("ingest", self.scoped(receipt, "ingest", batch=mismatch))
        report = self.invoke("report", self.scoped(receipt, "report"))
        self.assertFalse(report["coverage"]["LANDING"]["coverage_complete"])
        self.assertTrue(report["coverage"]["LANDING"]["mismatch"])

    def test_correction_is_append_only_and_report_uses_replacement(self):
        _, receipt = self.register()
        when = self.clock + timedelta(seconds=13)
        original = self.event(receipt, "landing", "s1", "LANDING", when.isoformat(), consent="DENIED")
        batch = self.batch(receipt, [original])
        self.invoke("ingest", self.scoped(receipt, "ingest", batch=batch))
        with connection(self.store.path) as db:
            stored = db.execute("SELECT hash FROM observational_campaign_events WHERE app_id=? AND source_id='wize-api' AND event_id='landing'", (APP,)).fetchone()
        replacement = dict(original, consent="GRANTED")
        correction = {"correction_id": "99999999-9999-4999-8999-999999999999", "source_id": "wize-api", "event_id": "landing",
                      "original_hash": stored["hash"], "replacement": replacement, "reason": "Corrected synthetic consent classification"}
        result = self.invoke("correct", self.scoped(receipt, "correct", correction=correction))
        self.assertEqual(result["original_hash"], stored["hash"])
        report = self.invoke("report", self.scoped(receipt, "report"))
        self.assertEqual(report["landing_subjects"], 1)
        self.assertEqual(report["exclusions"]["CONSENT_DENIED"], 0)
        with connection(self.store.path) as db:
            row = db.execute("SELECT data,hash FROM observational_campaign_events WHERE app_id=? AND source_id='wize-api' AND event_id='landing'", (APP,)).fetchone()
            correction_row = db.execute("SELECT replacement_hash FROM observational_campaign_corrections WHERE app_id=? AND event_id='landing'", (APP,)).fetchone()
        self.assertEqual(digest(json.loads(row["data"])), row["hash"])
        from mission_control.observational_campaign_contract import event_data
        study_data = json.loads(self.db_row(receipt["study_id"])["data"])
        normalized = event_data(replacement, receipt["study_id"], study_data["starts_at"], study_data["ends_at"], (self.clock + timedelta(seconds=30)).isoformat())
        self.assertEqual(correction_row["replacement_hash"], digest(normalized))

    def test_app_drift_and_storage_corruption_fail_closed(self):
        _, receipt = self.register()
        body = self.scoped(receipt, "report")
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], release="r2"), app["version"])
        with self.assertRaises(Invalid):
            self.invoke("report", body)

        _, receipt2 = self.register()
        self._corrupt("DROP TRIGGER observational_campaign_studies_no_update", ())
        self._corrupt("UPDATE observational_campaign_studies SET data=? WHERE app_id=? AND study_id=?", ("{}", APP, receipt2["study_id"]))
        with self.assertRaises(Invalid):
            self.invoke("report", self.scoped(receipt2, "report"))

    def test_history_bounded_and_manifest_drift_rejected(self):
        _, receipt = self.register()
        history = self.invoke("history", {})
        self.assertEqual(len(history["records"]), 1)
        self.assertEqual(history["limit"], 100)
        body = self.scoped(receipt, "report")
        body["manifest_version"] += 1
        with self.assertRaises(Invalid):
            self.invoke("report", body)

    def _corrupt(self, query, values):
        with connection(self.store.path) as db:
            db.execute(query, values)

    def count(self, table):
        with connection(self.store.path) as db:
            return db.execute("SELECT count(*) FROM " + table).fetchone()[0]

    def _ensure_tables(self):
        from mission_control.observational_campaign import _tables
        with connection(self.store.path) as db:
            _tables(db)


if __name__ == "__main__":
    unittest.main()
