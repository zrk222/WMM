"""Verify that private reports prioritize unresolved Meta pause evidence."""

import unittest

from mission_control.campaign_owner_reports import next_action


class CampaignPauseGuidanceTests(unittest.TestCase):
    def test_report_without_a_monitor_uses_the_saved_effective_pause_evidence(self) -> None:
        monitor = {"id": None, "last_observation": None}
        for readback, expected in (
            ({}, "do not confirm an effective Meta pause"),
            ({"pause_readback": {"effective_status": None}}, "do not confirm an effective Meta pause"),
            ({"pause_readback": {"effective_status": "WITH_ISSUES"}}, "do not confirm an effective Meta pause"),
            ({"pause_readback": {"effective_status": "ACTIVE"}}, "reporting active delivery"),
            ({"pause_readback": {"effective_status": "PAUSED"}}, "Choose a primary outcome"),
        ):
            with self.subTest(readback=readback):
                campaign = {
                    "status": "ACTIVE",
                    "expires_at": "2999-01-01T00:00:00+00:00",
                    "receipts": [{"status": "PAUSED_campaign", **readback}],
                }
                guidance = next_action(campaign, monitor, None)
                self.assertIn(expected, guidance)
                if expected != "Choose a primary outcome":
                    self.assertIn("do not retry the pause", guidance)
