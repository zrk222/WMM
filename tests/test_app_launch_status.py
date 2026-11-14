"""Launch status requires scoped, current observations."""

import unittest
from datetime import timedelta

from mission_control.app_launch_status import ConnectRead, StorefrontRead, resolve
from mission_control.common import iso_time

NOW = iso_time("2026-11-14T12:00:00Z")


class AppLaunchStatusTests(unittest.TestCase):
    def test_live_version_stays_live_during_update_review(self) -> None:
        connect: ConnectRead = {
            "observed_at": NOW.isoformat(),
            "complete": True,
            "states": ["WAITING_FOR_REVIEW", "READY_FOR_DISTRIBUTION"],
        }
        result = resolve(connect, [{"observed_at": NOW.isoformat(), "storefront": "CA", "state": "AVAILABLE"}], NOW)
        self.assertEqual(result["status"], "LIVE")
        self.assertEqual(result["verified_storefronts"], ["CA"])
        self.assertIs(result["authority_issued"], False)
        self.assertEqual(resolve(connect, [], NOW)["status"], "UNKNOWN")

    def test_awaiting_review_needs_complete_inventory_and_no_conflicting_listing(self) -> None:
        connect: ConnectRead = {
            "observed_at": NOW.isoformat(),
            "complete": True,
            "states": ["WAITING_FOR_REVIEW"],
        }
        self.assertEqual(resolve(connect, [], NOW)["status"], "IN_REVIEW")
        public: StorefrontRead = {"observed_at": NOW.isoformat(), "storefront": "US", "state": "AVAILABLE"}
        self.assertEqual(resolve(connect, [public], NOW)["reason"], "SOURCE_CONFLICT")
        connect["complete"] = False
        self.assertEqual(resolve(connect, [], NOW)["status"], "UNKNOWN")

    def test_stale_evidence_or_empty_lookup_does_not_certify_availability_or_removal(self) -> None:
        connect: ConnectRead = {
            "observed_at": (NOW - timedelta(days=2)).isoformat(),
            "complete": True,
            "states": ["READY_FOR_DISTRIBUTION"],
        }
        public: StorefrontRead = {"observed_at": NOW.isoformat(), "storefront": "CA", "state": "AVAILABLE"}
        self.assertEqual(resolve(connect, [public], NOW)["status"], "UNKNOWN")
        connect["observed_at"] = NOW.isoformat()
        public["state"] = "NOT_LISTED"
        self.assertEqual(resolve(connect, [public], NOW, previous_verified_live=True)["status"], "UNKNOWN")
        connect["states"] = ["REMOVED_FROM_SALE"]
        self.assertEqual(resolve(connect, [public], NOW)["status"], "UNKNOWN")
        self.assertEqual(resolve(connect, [public], NOW, previous_verified_live=True)["status"], "REMOVED")
