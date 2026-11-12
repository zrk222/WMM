"""Fresh child work uses current parent permission without extending old packets."""

from datetime import datetime, timedelta, timezone
import copy
import json
import unittest
from unittest.mock import patch

from mission_control.authority_expiry import AuthorityExpiry
from mission_control.common import iso_time
from mission_control.db import connection
from mission_control.operator_client import OperatorClient
from mission_control.worker import enqueue
from tests import test_agent_handoffs as handoffs
from tests import test_agent_review_dispatch as reviews
from tests import test_organic_video_collector as collector
from tests import test_verified_review as identities


def extend(store, owner, identity):
    service = AuthorityExpiry(store)
    body = dict(kind="AGENT_GRANT", id=identity, expires=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat())
    preview = service.preview("sample-one", owner, body)
    return service.confirm(
        "sample-one", owner, dict(preview, request_id="extend-workflow", extended_expiry_consent=True)
    )


class HandoffExpiryWorkflowTests(unittest.TestCase):
    setUp = handoffs.HandoffTests.setUp
    tearDown = handoffs.HandoffTests.tearDown
    body = handoffs.HandoffTests.body
    issue = handoffs.HandoffTests.issue

    def test_fresh_handoff_uses_extended_parent_and_old_packet_stays_unchanged(self):
        issued = self.issue(["handoff.create", "jobs.read"])
        client = OperatorClient(self.origin, issued["token"])
        job = enqueue(self.store, "sample-one", "pipeline", dict(stage=1), "fixture-private-key")

        def create(hours):
            return client.call(
                dict(
                    app_id="sample-one",
                    operation="handoff.create",
                    input=dict(
                        job_id=job["id"],
                        recipient="replacement",
                        operations=["jobs.read"],
                        expires=(datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(),
                    ),
                )
            )

        old = create(0.25)
        extend(self.store, identities.OWNER, issued["grant"]["id"])
        fresh = create(12)
        self.assertGreater(iso_time(fresh["expires"]), iso_time(issued["grant"]["expires"]))
        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute("SELECT expires FROM agent_handoffs WHERE id=?", (old["id"],)).fetchone()[0], old["expires"]
            )
            payload = json.loads(
                db.execute("SELECT payload FROM agent_handoffs WHERE id=?", (fresh["id"],)).fetchone()[0]
            )
            self.assertGreater(iso_time(payload["source"]["expires"]), iso_time(issued["grant"]["expires"]))


class ReviewedExpiryWorkflowTests(unittest.TestCase):
    setUp = reviews.ReviewedDispatchTests.setUp
    setUp_base = reviews.ReviewedDispatchTests.setUp_base
    tearDown = reviews.ReviewedDispatchTests.tearDown
    body = reviews.ReviewedDispatchTests.body
    envelope = reviews.ReviewedDispatchTests.envelope
    listing_body = reviews.ReviewedDispatchTests.listing_body
    issue_reviewed = reviews.ReviewedDispatchTests.issue_reviewed

    def test_new_checkpoint_keeps_independent_24_hour_bound_after_parent_extension(self):
        old = self.dispatch.prepare(self.token, "review-old", self.input)
        extend(self.store, identities.OWNER, self.issued["grant"]["id"])
        fresh = self.dispatch.prepare(self.token, "review-new", self.input)
        with connection(self.store.path) as db:
            rows = {
                row["id"]: json.loads(row["data"])["packet"]
                for row in db.execute("SELECT id,data FROM agent_checkpoints")
            }
        self.assertGreater(iso_time(rows["review-new"]["expires"]), iso_time(self.issued["grant"]["expires"]))
        self.assertLessEqual(iso_time(rows["review-new"]["expires"]), datetime.now(timezone.utc) + timedelta(hours=24))
        self.assertEqual(rows["review-old"]["expires"], old["checkpoint"]["packet"]["expires"])
        self.assertEqual(fresh["checkpoint"]["state"], "WAITING_REVIEW")


class CollectorExpiryWorkflowTests(unittest.TestCase):
    setUp = collector.CollectorTests.setUp
    owner_call = collector.CollectorTests.owner_call
    agent_call = collector.CollectorTests.agent_call
    claim_task = collector.CollectorTests.claim_task

    def test_new_discovery_respects_current_grant_and_retains_own_deadline(self):
        extend(self.store, self.owner, self.grant["grant"]["id"])
        body = copy.deepcopy(self.body)
        body["policy"]["expires"] = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        saved = self.owner_call(body)
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch("mission_control.organic_video_collector.datetime") as clock:
            clock.now.return_value = future
            claimed = self.claim_task(saved)
        self.assertGreater(iso_time(claimed["claim_until"]), future)
        self.assertLessEqual(iso_time(claimed["claim_until"]), iso_time(body["policy"]["expires"]))


if __name__ == "__main__":
    unittest.main()
