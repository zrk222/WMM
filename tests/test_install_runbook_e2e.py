"""Synthetic end-to-end runbook path: register study -> import installs -> linked report."""
from unittest.mock import patch
import unittest
from datetime import timedelta
from mission_control.install_attribution import record_batch, report, summary
from mission_control.review_access import Access
from tests import test_observational_campaign as campaign_fixture

OWNER = {"principal": "github:owner", "login": "owner"}


class RunbookPathTests(unittest.TestCase):
    def setUp(self):
        self.fx = campaign_fixture.ObservationalCampaignTests("test_registration_is_local_immutable_plan_and_url_is_canonical")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        Access(self.fx.store).bootstrap(campaign_fixture.APP, OWNER, {"confirm_owner": True})

    def test_synthetic_path_links_install_batch_to_registered_study(self):
        body, receipt = self.fx.register()
        campaign = receipt["study_id"]
        definition = body["definition"]
        starts, ends = definition["starts_at"], definition["ends_at"]
        install_time = (self.fx.clock + timedelta(days=1)).isoformat()
        batch = dict(source="MMP", campaign_token=campaign,
                     request_id="33333333-3333-4333-8333-333333333333",
                     source_receipt_sha256="a" * 64, observed_at=ends,
                     window=dict(starts_at=starts, ends_at=ends),
                     coverage=dict(complete=True, source_event_count=1),
                     installs=[dict(install_id="install_a", state="ATTRIBUTED", occurred_at=install_time)])
        with patch("mission_control.install_attribution.now", return_value=ends):
            result = record_batch(self.fx.store, campaign_fixture.APP, OWNER, batch)
        self.assertEqual(result["inserted"], 1)
        value = report(self.fx.store, campaign_fixture.APP, OWNER, campaign, day=1)
        self.assertEqual(value["study_status"], "LINKED")
        self.assertEqual(value["study"]["study_hash"], receipt["study_hash"])
        self.assertEqual(value["campaign_start"], definition["starts_at"])
        self.assertEqual(value["counts"]["ATTRIBUTED"], 1)
        self.assertEqual(value["coverage_status"], "COMPLETE")
        self.assertNotIn("rate", value)
        self.assertNotIn("lift", value)
        summary_value = summary(self.fx.store, campaign_fixture.APP)["campaigns"][0]
        self.assertEqual(summary_value["study_status"], "LINKED")
        self.assertNotIn("counts", summary_value)


if __name__ == "__main__":
    unittest.main()


