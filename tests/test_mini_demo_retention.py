"""Mature source-joined retention, exclusions, duplicate identity and unknown coverage."""

import copy
import unittest
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from mission_control.common import Invalid, iso_time
from mission_control.db import connection
from mission_control.mini_demo_retention import assess
from tests import test_observational_campaign as source_fixture


class DemoRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = source_fixture.ObservationalCampaignTests(
            "test_registration_is_local_immutable_plan_and_url_is_canonical"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        registration, receipt = self.fixture.register(collector_source_id="synthetic-api", source="youtube")
        self.study = receipt
        start = iso_time(registration["definition"]["starts_at"])
        end = iso_time(registration["definition"]["ends_at"])
        self.registered = start + timedelta(hours=1)
        self.fixture.clock = end + timedelta(days=3)
        events = [
            self.fixture.event(receipt, "land-a", "person-a", "LANDING", occurred_at=start.isoformat()),
            self.fixture.event(
                receipt, "register-a", "person-a", "REGISTRATION", occurred_at=self.registered.isoformat()
            ),
            self.fixture.event(receipt, "land-b", "person-b", "LANDING", occurred_at=start.isoformat()),
            self.fixture.event(
                receipt, "register-b", "person-b", "REGISTRATION", occurred_at=self.registered.isoformat()
            ),
        ]
        batch = self.fixture.batch(receipt, events, source_id="synthetic-api")
        self.fixture.invoke("ingest", self.fixture.scoped(receipt, "ingest", batch=batch))
        self.demo = dict(data=dict(study_id=receipt["study_id"], study_hash=receipt["study_hash"], channel="youtube"))
        returned = dict(
            event_id="return-a",
            subject_id="person-a",
            campaign_token=receipt["study_id"],
            occurred_at=(self.registered + timedelta(days=1, minutes=10)).isoformat(),
            consent="GRANTED",
            bot=False,
            internal_test=False,
        )
        self.body: dict[str, Any] = dict(
            source_id="synthetic-api",
            days=1,
            observed_at=self.fixture._now(),
            coverage_from=start.isoformat(),
            coverage_through=self.fixture._now(),
            complete=True,
            source_event_count=1,
            source_receipt_sha256="a" * 64,
            events=[returned],
        )

    def assess(self, body: dict[str, Any] | None = None) -> dict:
        with (
            patch("mission_control.mini_demo_retention.now", return_value=self.fixture._now()),
            connection(self.fixture.store.path) as db,
        ):
            return assess(db, source_fixture.APP, self.demo, body or self.body)

    def test_mature_same_source_landing_registration_return_join(self) -> None:
        result = self.assess()
        self.assertEqual(result["status"], "DESCRIPTIVE_READY")
        self.assertEqual(result["registered_subjects"], 2)
        self.assertEqual(result["retained_subjects"], 1)
        self.assertEqual(result["rate"], 0.5)
        self.assertFalse(result["causal_lift"])

    def test_duplicates_do_not_inflate_and_conflicts_fail(self) -> None:
        body = copy.deepcopy(self.body)
        body["events"].append(copy.deepcopy(body["events"][0]))
        self.assertEqual(self.assess(body)["retained_subjects"], 1)
        body["events"][1]["subject_id"] = "person-b"
        with self.assertRaises(Invalid):
            self.assess(body)

    def test_wrong_tag_namespace_and_count_fail_closed(self) -> None:
        for key, value in (("source_id", "other-api"), ("source_event_count", 2), ("days", True)):
            with self.assertRaises(Invalid):
                self.assess(dict(self.body, **{key: value}))
        body = copy.deepcopy(self.body)
        body["events"][0]["campaign_token"] = "foreign-tag"  # noqa: S105 - synthetic public campaign tag
        with self.assertRaises(Invalid):
            self.assess(body)

    def test_unmatched_bot_internal_or_denied_return_is_not_retention(self) -> None:
        for key, value in (
            ("subject_id", "foreign-person"),
            ("consent", "DENIED"),
            ("bot", True),
            ("internal_test", True),
        ):
            body = copy.deepcopy(self.body)
            body["events"][0][key] = value
            result = self.assess(body)
            self.assertEqual(result["retained_subjects"], 0)
        partial = self.assess(dict(self.body, complete=False))
        self.assertIsNone(partial["rate"])
        self.assertIsNone(partial["retained_subjects"])


if __name__ == "__main__":
    unittest.main()
