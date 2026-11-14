"""Launch status requires scoped, current observations."""

import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mission_control.app_launch_history import Sources, current, history, retain
from mission_control.app_launch_status import ConnectRead, StorefrontRead, resolve
from mission_control.apple_storefront import lookup
from mission_control.common import Invalid, iso_time
from mission_control.store import Store

NOW = iso_time("2026-11-14T12:00:00Z")


class AppLaunchStatusTests(unittest.TestCase):
    def test_public_listing_needs_exact_app_and_country_and_no_credentials(self) -> None:
        row = {"trackId": 123, "kind": "software", "trackViewUrl": "https://apps.apple.com/ca/app/example/id123"}
        with patch("mission_control.apple_storefront.read_json") as request:
            request.return_value = {"resultCount": 1, "results": [row]}
            result, fingerprint = lookup("123", "CA")
            self.assertEqual(result["state"], "AVAILABLE")
            self.assertEqual(len(fingerprint), 64)
            request.assert_called_once_with("https://itunes.apple.com/lookup?id=123&country=ca", {}, timeout=8)
            with self.assertRaisesRegex(Invalid, "storefront"):
                lookup("123", "US")
            with self.assertRaisesRegex(Invalid, "different app"):
                lookup("124", "CA")
            request.return_value = {"resultCount": 0, "results": []}
            self.assertEqual(lookup("123", "CA")[0]["state"], "NOT_LISTED")

    def test_history_preserves_exact_retry_and_previous_verified_status(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "launch.sqlite"
            version = Store(path).app("sample-one")["version"]
            storefront: StorefrontRead = {"observed_at": NOW.isoformat(), "storefront": "CA", "state": "AVAILABLE"}
            released: ConnectRead = {
                "observed_at": NOW.isoformat(),
                "states": ["READY_FOR_DISTRIBUTION"],
                "complete": True,
            }
            sources = Sources(released, [storefront])
            with patch("mission_control.app_launch_history.now", return_value=NOW.isoformat()):
                live = retain(path, "sample-one", version, sources)
                self.assertEqual(retain(path, "sample-one", version, sources), live)
                self.assertEqual(current(path, "sample-one", version, NOW)["status"], "LIVE")
                self.assertEqual(current(path, "sample-two", version, NOW)["status"], "UNKNOWN")
                with self.assertRaises(Invalid):
                    retain(path, "sample-one", version + 1, sources)
            later = NOW + timedelta(days=2)
            stale = current(path, "sample-one", version, later)
            self.assertEqual(stale["status"], "UNKNOWN")
            self.assertTrue(stale["stale"])
            removed: ConnectRead = {
                "observed_at": later.isoformat(),
                "states": ["REMOVED_FROM_SALE"],
                "complete": True,
            }
            with patch("mission_control.app_launch_history.now", return_value=later.isoformat()):
                receipt = retain(path, "sample-one", version, Sources(removed, []))
            self.assertEqual(receipt["status"], "REMOVED")
            self.assertEqual(receipt["previous_status"], "LIVE")
            self.assertEqual(history(path, "sample-one", version), [receipt, live])

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
