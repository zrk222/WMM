"""Real protected owner HTTP and exact gateway coverage for both update briefs."""

import unittest
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from mission_control.common import digest, now
from mission_control.db import connection
from mission_control.marketing_effort import summary
from mission_control.operation_catalog import request_data
from mission_control.operator_client import ClientError, OperatorClient
from tests import test_campaign_owner_reports as report_fixture

OPERATIONS = (
    "marketing-review.index-artifact",
    "marketing-review.claims",
    "marketing-review.check-artifact",
    "marketing-review.effort",
    "marketing-review.change",
    "marketing-review.topics",
    "marketing-review.prepare-demo",
    "marketing-review.demo-status",
    "marketing-review.retention",
)


class MarketingReviewHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = report_fixture.CampaignOwnerReportsTests(
            "test_report_retains_pause_observation_and_rejects_rebound_receipts"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        self.client = self.fixture.fixture.client
        self.scope = self.fixture.chosen()["scope_id"]
        self.base = "/api/apps/sample/marketing-review/"

    def call(self, action: str, **body: Any) -> dict[str, Any]:
        result = self.client.request("POST", self.base + action, dict(scope_id=self.scope, **body))
        assert isinstance(result, dict)
        return result

    def artifact(self) -> dict[str, Any]:
        return self.call(
            "index-artifact",
            id="11111111-1111-4111-8111-111111111111",
            url="https://example.com/offer",
            approved_claim_text="An exact approved synthetic claim.",
            claim_ids=[],
            published_at=now(),
        )

    def test_protected_http_source_change_and_owner_report(self) -> None:
        saved = self.artifact()
        current = self.call("claims")
        self.assertEqual(current["artifacts"][0]["status"], "SOURCE_UNCHANGED")
        app = self.store.app("sample")
        self.store.save_app("sample", dict(app["data"], release="changed-product"), app["version"])
        report = self.fixture.capture()["report"]
        self.assertEqual(report["stale_claims"]["stale_count"], 1)
        self.assertEqual(
            report["stale_claims"]["artifacts"][0]["approved_claim_text"], saved["data"]["approved_claim_text"]
        )
        self.assertIn("stale public claims", report["next_action"])
        self.assertFalse(report["stale_claims"]["automatic_changes"])
        # Immutable report replay does not acquire new network or edit authority.
        self.assertEqual(self.call("claims")["stale_count"], 1)

    def test_missing_effort_is_unknown_and_recorded_zero_is_not_missing(self) -> None:
        window = dict(starts_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat(), ends_at=now())
        with connection(self.store.path) as db:
            self.assertIsNone(summary(db, "sample", "owner", self.scope, window)["minutes"])
        stamp = now()
        body = dict(
            id="22222222-2222-4222-8222-222222222222",
            occurred_at=stamp,
            checks_run=2,
            reviews_completed=1,
            minutes=0,
            evidence_sha256="a" * 64,
            note="Synthetic check receipt",
        )
        saved = self.call("effort", **body)
        self.assertEqual(self.call("effort", **body), saved)
        with self.assertRaises(ClientError):
            self.call("effort", **dict(body, minutes=1))
        chosen = self.fixture.chosen(
            measurement_window=dict(
                starts_at=window["starts_at"], ends_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
            )
        )
        first = self.fixture.capture(chosen)["report"]
        self.assertEqual(first["verification_effort"]["minutes"], 0)
        self.assertEqual(first["verification_effort"]["checks_run"], 2)
        second = self.fixture.capture(chosen)["report"]
        self.assertEqual(second["comparison"]["verification_effort"]["status"], "COMPARABLE_RECORDED_EFFORT")
        self.assertEqual(second["comparison"]["verification_effort"]["previous"]["reviews_completed"], 1)
        with connection(self.store.path) as db:
            self.assertIsNone(
                summary(db, "sample", "different-owner", self.scope, chosen["measurement_window"])["minutes"]
            )
            half_open = summary(db, "sample", "owner", self.scope, dict(starts_at=window["starts_at"], ends_at=stamp))
            self.assertIsNone(half_open["minutes"])

    def test_public_read_is_explicit_and_reports_never_fetch(self) -> None:
        saved = self.artifact()
        with patch(
            "mission_control.campaign_stale_claims.PublicReader", side_effect=AssertionError("No network during report")
        ):
            self.fixture.capture()
            self.call("claims")
        with patch(
            "mission_control.marketing_review.verify_public", return_value=dict(status="WORDING_FOUND")
        ) as reader:
            result = self.call("check-artifact", id=saved["id"], hash=saved["hash"])
            self.assertEqual(result["observation"]["status"], "WORDING_FOUND")
            reader.assert_called_once_with(saved["data"]["url"], saved["data"]["approved_claim_text"])

    def test_anonymous_foreign_scope_and_invalid_inputs_are_denied(self) -> None:
        anonymous = OperatorClient(self.client.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request("POST", self.base + "claims", dict(scope_id=self.scope))
        for payload in (dict(scope_id="foreign"), dict(scope_id=self.scope, owner="forged")):
            with self.assertRaises(ClientError):
                self.client.request("POST", self.base + "claims", payload)
        for values in (
            dict(minutes=True),
            dict(checks_run=-1),
            dict(reviews_completed=1.5),
            dict(evidence_sha256="bad"),
            dict(occurred_at="2035-01-01T00:00:00Z"),
        ):
            body = dict(
                id="33333333-3333-4333-8333-333333333333",
                occurred_at=now(),
                checks_run=1,
                reviews_completed=1,
                minutes=1,
                evidence_sha256="a" * 64,
                note="Synthetic",
            )
            with self.assertRaises(ClientError):
                self.call("effort", **dict(body, **values))
        self.assertEqual(self.call("topics")["topics"], [])

    def test_catalog_fields_match_closed_marketing_actions(self) -> None:
        from mission_control.marketing_review import FIELDS

        for operation in OPERATIONS:
            action = operation.split(".")[1]
            request = request_data(
                dict(app_id="sample", operation=operation, input={key: None for key in FIELDS[action]})
            )
            self.assertEqual(request["path"], self.base + action)

    def test_published_post_automatically_keeps_original_wording_and_source(self) -> None:
        # The campaign fixture's verified initial post predates this scope; use its actual retained snapshot.
        with connection(self.store.path) as db:
            artifact_rows = db.execute("SELECT * FROM marketing_review_evidence WHERE kind='ARTIFACT'").fetchall()
        self.assertTrue(artifact_rows, "A verified fixture post should be indexed automatically")
        data = __import__("json").loads(artifact_rows[0]["data"])
        self.assertEqual(data["provenance"], "VERIFIED_CAMPAIGN_RECEIPT")
        self.assertTrue(data["approved_claim_text"])
        self.assertEqual(data["source_sha256"], digest(data["source"]))


if __name__ == "__main__":
    unittest.main()
