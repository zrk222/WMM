"""Feature -> hook -> capture/render -> exact approval -> receipt, with no live effects."""

import copy
import unittest
from datetime import datetime, timedelta, timezone
from typing import Any

from mission_control.common import canonical, digest, now
from mission_control.creative_briefs import Briefs
from mission_control.db import connection
from mission_control.operator_client import ClientError
from tests import test_marketing_review as http_fixture
from tests.test_creative_production import ready_production

CHANGE = "44444444-4444-4444-8444-444444444444"
DEMO = "55555555-5555-4555-8555-555555555555"
STUDY = "66666666-6666-4666-8666-666666666666"


class MiniDemoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = http_fixture.MarketingReviewHTTPTests("test_catalog_fields_match_closed_marketing_actions")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store
        current = self.store.app("sample")
        self.store.save_app(
            "sample",
            dict(
                name="Synthetic Demo App",
                job="Inspect a synthetic example",
                audience="Synthetic owners",
                activation="Saved example",
                release="test-build",
                locale="en-US",
                currency="USD",
                website="https://example.com",
            ),
            current["version"],
        )
        _, _, self.records, definition = ready_production(self.store, "sample")
        self.brief = Briefs(self.store).save("sample", {"data": definition})
        self.change = self.fixture.call(
            "change",
            id=CHANGE,
            title="Show one fictional conversation",
            shipped_at=now(),
            shipment_sha256="c" * 64,
            claim_ids=[self.records["claim"]["id"]],
        )
        # A real protected owner operation registers the source/channel/creative link.
        start = datetime.now(timezone.utc) + timedelta(minutes=1)
        self.study: Any = self.fixture.client.request(
            "POST",
            "/api/apps/sample/observational-campaign/register",
            dict(
                request_id=STUDY,
                manifest_version=self.store.app("sample")["version"],
                definition=dict(
                    id=STUDY,
                    name="Synthetic mini demo",
                    hypothesis="Tagged visits may register",
                    source="youtube",
                    creative_id=self.brief["id"],
                    landing_path="/start",
                    starts_at=start.isoformat(),
                    ends_at=(start + timedelta(days=2)).isoformat(),
                    landing_event="landing",
                    registration_event="registration",
                    attribution_model="FIRST_TOUCH",
                    collector_source_id="synthetic-collector",
                ),
            ),
        )
        self.body: dict[str, Any] = dict(
            id=DEMO,
            change_id=CHANGE,
            change_hash=self.change["hash"],
            brief_id=self.brief["id"],
            brief_hash=self.brief["hash"],
            channel="youtube",
            study_id=STUDY,
            study_hash=self.study["study_hash"],
            hook_review=dict(
                audience="Synthetic owners",
                problem="How to inspect an example",
                reason_to_watch="See the actual saved result",
                opening_end_seconds=5,
                brief_hash=self.brief["hash"],
                reviewed=True,
            ),
        )

    def test_feature_to_demo_uses_real_brief_and_existing_render_gateway(self) -> None:
        topics = self.fixture.call("topics")
        self.assertEqual(topics["topics"][0]["status"], "TOPIC_FOR_REVIEW")
        demo = self.fixture.call("prepare-demo", **self.body)
        self.assertEqual(demo["data"]["state"], "PREPARED_NOT_APPROVED")
        self.assertIn("utm_source=youtube", demo["data"]["tagged_link"])
        self.assertIn("utm_campaign=" + STUDY, demo["data"]["tagged_link"])
        self.assertEqual(demo["data"]["capture_assets"], self.brief["data"]["content"]["screens"])
        self.assertFalse(demo["data"]["authority_issued"])
        status = self.fixture.call("demo-status", id=DEMO, hash=demo["hash"], publication_id=None)
        self.assertEqual(status["render_operation"]["operation"], "hypit.queue")
        self.assertEqual(status["steps"][2]["state"], "NOT_RUN")
        self.assertEqual(status["steps"][-1]["state"], "NOT_VERIFIED")
        self.assertEqual(self.fixture.call("prepare-demo", **self.body), demo)

    def test_publication_gate_uses_publication_compatible_render_and_exact_link(self) -> None:
        from mission_control.common import Invalid
        from mission_control.mini_demo_publication import check

        demo = self.fixture.call("prepare-demo", **self.body)
        render_id = "88888888-8888-4888-8888-888888888888"
        data = dict(inputs=dict(request=dict(brief_hash=self.brief["hash"])))
        from mission_control.worker import enqueue

        job = enqueue(self.store, "sample", "hypit_render", data, "fixture-job")
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO hypit_renders VALUES(?,?,?,?,?,?)",
                ("sample", render_id, job["id"], canonical(data), digest(data), now()),
            )
            draft = dict(artifact=dict(id=render_id), provider="youtube", link=demo["data"]["tagged_link"])
            check(db, self.store, "sample", draft)
            with self.assertRaises(Invalid):
                check(db, self.store, "sample", dict(draft, link="https://example.com/wrong"))
            with self.assertRaises(Invalid):
                check(db, self.store, "sample", dict(draft, provider="tiktok"))
            db.execute(
                "UPDATE records SET data=?,hash=? WHERE id=?",
                (
                    canonical(dict(self.records["claim"]["data"], claim="Changed claim")),
                    "d" * 64,
                    self.records["claim"]["id"],
                ),
            )
            with self.assertRaises(Invalid):
                check(db, self.store, "sample", draft)

    def test_hook_gate_rejects_missing_false_changed_or_late_review(self) -> None:
        for changes in (
            {"reviewed": False},
            {"brief_hash": "d" * 64},
            {"opening_end_seconds": 11},
            {"opening_end_seconds": True},
            {"audience": ""},
            {"reason_to_watch": ""},
        ):
            body = copy.deepcopy(self.body)
            body["hook_review"].update(changes)
            with self.assertRaises(ClientError):
                self.fixture.call("prepare-demo", **body)
        body = copy.deepcopy(self.body)
        del body["hook_review"]["problem"]
        with self.assertRaises(ClientError):
            self.fixture.call("prepare-demo", **body)
        self.assertEqual(self.fixture.call("claims")["stale_count"], 0)

    def test_foreign_channel_creative_or_source_cannot_be_rebound(self) -> None:
        with self.assertRaises(ClientError):
            self.fixture.call("prepare-demo", **dict(self.body, channel="tiktok"))
        with self.assertRaises(ClientError):
            self.fixture.call("prepare-demo", **dict(self.body, brief_hash="d" * 64))
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE records SET data=?,hash=? WHERE id=?",
                (
                    canonical(dict(self.records["claim"]["data"], claim="Changed synthetic capability")),
                    digest(dict(self.records["claim"]["data"], claim="Changed synthetic capability")),
                    self.records["claim"]["id"],
                ),
            )
        self.assertEqual(self.fixture.call("topics")["topics"][0]["status"], "STALE_SOURCE")
        with self.assertRaises(ClientError):
            self.fixture.call("prepare-demo", **self.body)

    def test_retention_requires_declared_source_and_mature_source_join(self) -> None:
        demo = self.fixture.call("prepare-demo", **self.body)
        today = datetime.now(timezone.utc)
        through = now()
        body = dict(
            id="77777777-7777-4777-8777-777777777777",
            demo_id=DEMO,
            demo_hash=demo["hash"],
            source_id="wrong-source",
            days=1,
            observed_at=through,
            coverage_from=(today - timedelta(days=3)).isoformat(),
            coverage_through=through,
            complete=True,
            source_event_count=0,
            source_receipt_sha256="e" * 64,
            events=[],
        )
        with self.assertRaises(ClientError):
            self.fixture.call("retention", **body)
        body["source_id"] = "synthetic-collector"
        result = self.fixture.call("retention", **body)
        self.assertEqual(result["data"]["report"]["status"], "PARTIAL_OR_IMMATURE")
        self.assertIsNone(result["data"]["report"]["rate"])
        self.assertIsNone(result["data"]["report"]["retained_subjects"])
        with self.assertRaises(ClientError):
            self.fixture.call("retention", **dict(body, days=True))


if __name__ == "__main__":
    unittest.main()
