"""Actual owner route saves selected scoped actions and rejects obsolete recommendations."""

import unittest
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from mission_control.db import connection
from mission_control.operator_client import OperatorClient
from tests import test_apple_metrics_http_route as fixtures


class SearchStoreActionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = fixtures.AppleMetricsRouteTests("test_owner_can_queue_observe_and_pause_without_provider_calls")
        self.addCleanup(self.route.doCleanups)
        self.route.setUp()
        self.body: dict[str, Any] = dict(
            manifest_version=self.route.app["version"], start="2026-01-01", end="2026-01-05"
        )

    def test_concurrent_saves_preserve_distinct_action_receipts(self) -> None:
        fetch = fixtures.BASE + "search-review"
        save = fixtures.BASE + "search-review-save"
        current = self.route.post(fetch, self.body)["search_review"]
        actions = current["actions"]
        self.assertGreaterEqual(len(actions), 2)
        body = dict(self.body, review_hash=current["review_hash"], action_id=actions[0]["id"])
        with ThreadPoolExecutor(max_workers=2) as pool:
            receipts = list(pool.map(lambda _: self.route.post(save, body)["receipt"], range(2)))
        self.assertEqual(receipts[0], receipts[1])
        self.assertEqual(receipts[0]["action"], actions[0])
        self.assertEqual(receipts[0]["saved_by"], "owner")
        self.assertEqual(receipts[0]["status"], "SAVED")
        other = self.route.post(save, dict(body, action_id=actions[1]["id"]))["receipt"]
        after = self.route.post(fetch, self.body)["search_review"]
        self.assertEqual(after["review_hash"], current["review_hash"])
        self.assertEqual({row["id"] for row in after["saved_actions"]}, {receipts[0]["id"], other["id"]})
        with connection(self.route.store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 0)

    def test_stale_source_date_unknown_action_and_unauthenticated_save_are_rejected(self) -> None:
        fetch = fixtures.BASE + "search-review"
        save = fixtures.BASE + "search-review-save"
        current = self.route.post(fetch, self.body)["search_review"]
        body = dict(self.body, review_hash=current["review_hash"], action_id=current["actions"][0]["id"])
        anon = OperatorClient(self.route.client.origin)
        anon.bootstrap()
        self.route.reject(anon, save, body, 403)
        self.route.reject(self.route.client, save, dict(body, end="2026-01-06"), 400)
        self.route.reject(self.route.client, save, dict(body, action_id="unknown-action"), 400)
        # An unchanged Apple app and an equivalent empty inventory can still belong to a new source version.
        with connection(self.route.store.path, write=True) as db:
            db.execute("UPDATE records SET version=version+1 WHERE id=?", (self.route.record["id"],))
        self.route.reject(self.route.client, save, body, 400)
        self.assertEqual(self.route.post(fetch, self.body)["search_review"]["saved_actions"], [])
        with connection(self.route.store.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM search_store_action_receipts").fetchone()[0], 0)

    def test_owner_can_recover_receipt_after_source_change_only_in_the_same_window(self) -> None:
        fetch = fixtures.BASE + "search-review"
        save = fixtures.BASE + "search-review-save"
        old = self.route.post(fetch, self.body)["search_review"]
        body = dict(self.body, review_hash=old["review_hash"], action_id=old["actions"][0]["id"])
        saved = self.route.post(save, body)["receipt"]
        with connection(self.route.store.path, write=True) as db:
            db.execute("UPDATE records SET version=version+1 WHERE id=?", (self.route.record["id"],))
        after = self.route.post(fetch, self.body)["search_review"]
        self.assertNotEqual(old["review_hash"], after["review_hash"])
        self.assertEqual(after["saved_actions"], [])
        self.assertEqual(
            after["earlier_plans"], [dict(review_hash=old["review_hash"], saved_actions=[saved], assignments={})]
        )
        self.route.reject(self.route.client, save, body, 400)
        self.assertEqual(
            self.route.post(fetch, dict(self.body, start="2026-01-02"))["search_review"]["earlier_plans"], []
        )
