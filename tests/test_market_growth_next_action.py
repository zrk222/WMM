"""Verify that research issues produce one practical next move."""

import unittest

from mission_control.market_research import next_intent_action


class MarketGrowthNextActionTests(unittest.TestCase):
    def test_current_public_listing_and_product_fit_precede_demand(self) -> None:
        self.assertEqual(next_intent_action(["demand", "current_listing"], "iOS")[0], "REFRESH_LISTING")
        self.assertEqual(next_intent_action(["demand", "app_proof"], "iOS")[0], "VERIFY_PRODUCT_FIT")

    def test_collect_queries_without_equating_paid_results_with_organic_rank(self) -> None:
        code, action = next_intent_action(["demand"], "iOS")
        self.assertEqual(code, "COLLECT_QUERY_EVIDENCE")
        self.assertIn("Apple Ads search-term report", action)
        self.assertIn("organic position and paid queries separately", action)
        self.assertNotIn("Apple", next_intent_action(["demand"], "Android")[1])

    def test_ready_intent_still_names_control_and_approval(self) -> None:
        code, action = next_intent_action([], "iOS")
        self.assertEqual(code, "REVIEW_ONE_TEST")
        self.assertIn("metric, sample and stop rule", action)
        self.assertIn("seeking approval", action)
