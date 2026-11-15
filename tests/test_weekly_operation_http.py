"""Weekly private operational projection uses trusted current local identity."""

import unittest
from unittest.mock import patch
from tests import test_campaign_monitor_integration as fixtures


class WeeklyOperationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.CampaignMonitorIntegrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_get_passes_current_local_owner_and_signed_out_passes_none(self):
        with patch("mission_control.weekly_inbox.review", return_value={"schema": "probe"}) as review:
            value = self.fixture.client.request("GET", "/api/weekly-review")
            self.assertEqual(value["schema"], "probe")
            self.assertEqual(review.call_args.kwargs["user"]["principal"], "owner")
            self.fixture.client.request("POST", "/api/identity/logout", {})
            self.fixture.client.request("GET", "/api/weekly-review")
            self.assertIsNone(review.call_args.kwargs["user"])


if __name__ == "__main__":
    unittest.main()
