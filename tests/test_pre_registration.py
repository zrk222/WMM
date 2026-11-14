"""Pre-registration drafts compose app facts without creating authority."""

import tempfile
import unittest
from pathlib import Path

from mission_control.evidence_gate import measurement_plan
from mission_control.pre_registration import draft
from mission_control.service import Service
from mission_control.store import Store


def app(website="https://example.test/app"):
    return dict(id="sample-one", data=dict(name="Synthetic app", release="1.2.3", website=website))


def records(*providers):
    return [dict(kind="connection", data=dict(provider=provider)) for provider in providers]


class PreRegistrationTests(unittest.TestCase):
    def test_ready_draft_tags_the_link_and_validates_its_plan(self):
        result = draft(app(), records("posthog", "revenuecat"), goal="paid conversion")
        self.assertEqual(result["status"], "READY_FOR_OWNER_REVIEW")
        self.assertEqual(result["missing"], [])
        plan = result["measurement_plan"]
        self.assertEqual(plan["primary_metric"], "paid_conversion")
        self.assertIn("utm_campaign=" + plan["campaign_tag"], result["tagged_link"])
        self.assertEqual(measurement_plan(plan)["campaign_tag"], plan["campaign_tag"])
        self.assertEqual(result["experiment_draft"]["primary_metric"], "paid_conversion")

    def test_missing_link_or_source_keeps_the_draft_blocked(self):
        no_link = draft(app(website=""), records("posthog", "revenuecat"), goal="paid conversion")
        self.assertEqual(no_link["status"], "DRAFT")
        self.assertIsNone(no_link["measurement_plan"])
        self.assertTrue(any("HTTPS landing link" in item for item in no_link["missing"]))
        no_outcome = draft(app(), records("posthog"), goal="paid conversion")
        self.assertEqual(no_outcome["status"], "DRAFT")
        self.assertTrue(any("outcome or cash source" in item for item in no_outcome["missing"]))

    def test_workspace_exposes_a_pre_registration_draft(self):
        with tempfile.TemporaryDirectory() as folder:
            service = Service(Store(Path(folder) / "state.sqlite"))
            self.assertIn("pre_registration", service.workspace("sample-one"))


if __name__ == "__main__":
    unittest.main()
