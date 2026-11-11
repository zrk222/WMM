"""Closed schema and canonical URL checks for observational campaign records."""
import unittest
from datetime import datetime, timedelta, timezone

from mission_control.common import Invalid
from mission_control.observational_campaign_contract import (
    ACTION_FIELDS, batch_data, definition_data, event_data, schema_contract, tagged_url,
)


class ObservationalCampaignContractTests(unittest.TestCase):
    def setUp(self):
        self.created = datetime(2030, 1, 1, tzinfo=timezone.utc).isoformat()
        self.study_id = "68f99f13-4f5f-4b01-8d0a-b3e4f4e28e82"
        self.definition = {
            "id": self.study_id, "name": "Organic post", "hypothesis": "A useful post leads to registrations.",
            "source": "facebook", "creative_id": "creative_A1", "landing_path": "/start",
            "starts_at": "2030-01-01T00:00:10Z", "ends_at": "2030-01-30T00:00:10Z",
            "landing_event": "landing", "registration_event": "registration", "attribution_model": "FIRST_TOUCH",
        }
        self.study = definition_data(self.definition, self.created)
        self.study["hash"] = "a" * 64

    def test_closed_action_fields_and_json_safe_catalog_contract(self):
        self.assertEqual(ACTION_FIELDS["history"], {"required": (), "optional": ("offset",)})
        value = schema_contract()
        self.assertEqual(value["max_batch_events"], 500)
        self.assertEqual(value["history_limit"], 100)
        self.assertIn("source_coverage_unknown", value["exclusions"])
        self.assertEqual(value["report_scope"], "ATTRIBUTED_DESCRIPTIVE_ONLY; no installs, activation, paid conversion, revenue, lift, or causal decision")

    def test_registration_enforces_future_window_and_opaque_fields(self):
        for field, value in (("source", "x.com"), ("creative_id", "bad/value"), ("landing_path", "https://other.example/path"),
                             ("landing_path", "/start?next=https://other.example"), ("attribution_model", "LAST_TOUCH")):
            with self.subTest(field=field, value=value), self.assertRaises(Invalid):
                definition_data(dict(self.definition, **{field: value}), self.created)
        with self.assertRaises(Invalid):
            definition_data(dict(self.definition, starts_at="2030-01-01T00:00:00Z"), self.created)
        with self.assertRaises(Invalid):
            definition_data(dict(self.definition, ends_at="2030-02-01T00:00:11Z"), self.created)

    def test_canonical_url_is_same_origin_with_exactly_four_parameters(self):
        url = tagged_url("https://wizeme.example/path", self.study)
        self.assertEqual(url, "https://wizeme.example/start?utm_source=facebook&utm_medium=organic&utm_campaign=" + self.study_id + "&utm_content=creative_A1")
        with self.assertRaises(Invalid):
            tagged_url("http://wizeme.example", self.study)
        with self.assertRaises(Invalid):
            tagged_url("https://user:pass@wizeme.example", self.study)

    def test_event_contract_keeps_explicit_unknown_states_and_utc(self):
        event = {"event_id": "e1", "subject_id": "s1", "type": "LANDING", "occurred_at": "2030-01-01T01:00:12+01:00",
                 "campaign_token": self.study_id, "consent": "UNKNOWN", "bot": None, "internal_test": False}
        result = event_data(event, self.study_id, self.study["starts_at"], self.study["ends_at"], "2030-01-02T00:00:00Z")
        self.assertEqual(result["occurred_at"], "2030-01-01T00:00:12.000000Z")
        self.assertIsNone(result["bot"])
        for bad in (dict(event, extra=True), dict(event, subject_id="user@example.com"), dict(event, bot=1),
                    dict(event, occurred_at="2030-01-01T00:00:00"), dict(event, occurred_at="2030-01-31T00:00:00Z")):
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                event_data(bad, self.study_id, self.study["starts_at"], self.study["ends_at"], "2030-02-01T00:00:00Z")

    def test_batch_bounds_and_coverage_zero_vs_unknown(self):
        body = {"batch_id": "cd89f69a-0e87-42fa-afc1-713c40531ea3", "study_id": self.study_id,
                "study_hash": self.study["hash"], "app_version": 1, "source_id": "wize-api",
                "source_receipt_sha256": "b" * 64, "observed_at": "2030-01-02T00:00:00Z",
                "coverage": {kind: {"complete": True, "source_event_count": 0} for kind in ("LANDING", "REGISTRATION")}, "events": []}
        study = {"id": self.study_id, "hash": self.study["hash"], "data": self.study}
        normalized = batch_data(body, study, 1, "2030-01-02T00:00:01Z")
        self.assertEqual(normalized["coverage"]["LANDING"], {"complete": True, "source_event_count": 0})
        with self.assertRaises(Invalid):
            batch_data(dict(body, events=[{}] * 501), study, 1, "2030-01-02T00:00:01Z")
        with self.assertRaises(Invalid):
            batch_data(dict(body, coverage={"LANDING": {"complete": True, "source_event_count": None}, "REGISTRATION": body["coverage"]["REGISTRATION"]}), study, 1, "2030-01-02T00:00:01Z")


if __name__ == "__main__":
    unittest.main()
