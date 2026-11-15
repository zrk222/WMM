"""Regression witnesses for retained schedule authority identity."""

import sqlite3
import unittest
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from mission_control.campaign_schedule_authority import (
    ScheduledJob,
    bound,
    check,
    check_content,
    check_deadline,
    check_lease,
    check_scope,
    video_content,
    video_context,
    video_deadline,
)
from mission_control.common import canonical, digest, iso_time
from mission_control.organic_video_schedule import KIND
from mission_control.store import Store


class ScheduleAuthorityBoundaryTests(unittest.TestCase):
    def test_leased_dispatch_checks_effect_reviewed_request_and_listing(self) -> None:
        with TemporaryDirectory() as directory:
            store = Store(Path(directory) / "workspace.sqlite")
            request = {"link": "https://example.com/listing"}
            body = dict(item_id="item", due_at="2027-01-01T00:00:00+00:00", request=request)
            scope = dict(scope_id="scope", approval_hash="proof", owner_principal="owner")
            summary = dict(
                batch_id="batch",
                scope_id="scope",
                scope_hash="proof",
                owner="owner",
                app_id="app",
                items=[body],
                permission_expires_at="2099-01-01T00:00:00+00:00",
            )
            job_data = dict(batch_id="batch", item_id="item", scope_id="scope", request=request)
            job: ScheduledJob = {"id": "job", "attempts": 1, "data": job_data}
            due = iso_time(body["due_at"]).timestamp()
            row = dict(
                summary=canonical(summary),
                summary_hash=digest(summary),
                body=canonical(body),
                body_hash=digest(body),
                data=canonical(job_data),
                batch_id="batch",
                app_id="app",
                action="campaign_post",
                batch_status="ACTIVE",
                item_status="QUEUED",
                job_status="RUNNING",
                attempts=1,
                lease=due + 61,
                due=due,
            )
            base = "mission_control.campaign_schedule_authority"
            self.assertFalse(check(store, "app", "schedule:job", scope, "RUN_POST"))
            with (
                bound(store, job),
                patch(base + ".connection", return_value=nullcontext(object())),
                patch(base + "._leased_row", return_value=row) as retained,
                patch(base + ".removed_listing", return_value=False) as removed,
                patch(base + ".time.time", return_value=due + 1),
            ):
                self.assertTrue(check(store, "app", "schedule:job", scope, "RUN_POST"))
                for actor, action, message in (
                    ("schedule:other", "RUN_POST", "cannot authorize"),
                    ("schedule:job", "PAUSE", "cannot authorize"),
                    ("schedule:job", "RUN_AD", "does not match effect"),
                ):
                    with self.subTest(actor=actor, action=action), self.assertRaisesRegex(PermissionError, message):
                        check(store, "app", actor, scope, action)
                retained.return_value = None
                with self.assertRaisesRegex(PermissionError, "job is unavailable"):
                    check(store, "app", "schedule:job", scope, "RUN_POST")
                retained.return_value = dict(row, data=canonical(dict(job_data, item_id="substitute")))
                with self.assertRaisesRegex(PermissionError, "worker input changed"):
                    check(store, "app", "schedule:job", scope, "RUN_POST")
                retained.return_value = dict(row, action="campaign_ad")
                with self.assertRaisesRegex(PermissionError, "worker operation changed"):
                    check(store, "app", "schedule:job", scope, "RUN_POST")
                retained.return_value = row
                removed.return_value = True
                with self.assertRaisesRegex(PermissionError, "removed from the App Store"):
                    check(store, "app", "schedule:job", scope, "RUN_POST")

    def test_paid_schedule_binds_the_retained_operation(self) -> None:
        body = {"item_id": "item", "request": {}, "operation": "campaign.ad-launch", "due_at": "2027-01-01T00:00:00Z"}
        summary = dict(batch_id="batch", scope_id="scope", scope_hash="hash", owner="owner", app_id="app", items=[body])
        scope = dict(scope_id="scope", approval_hash="hash", owner_principal="owner", expires_at="2099-01-01T00:00:00Z")
        data = dict(batch_id="batch", scope_id="scope", item_id="item", request={}, operation="campaign.ad-launch")
        row = dict(
            action="campaign_ad",
            batch_id="batch",
            summary_hash=digest(summary),
            body_hash=digest(body),
            due=iso_time(body["due_at"]).timestamp(),
        )
        check_content(row, data, body, summary, "app", scope)
        with self.assertRaisesRegex(PermissionError, "inputs changed"):
            check_content(row, dict(data, operation="campaign.publish"), body, summary, "app", scope)

    def test_reel_requires_exact_actor_row_and_policy(self) -> None:
        operation = "organic-video.intent-execute"
        with TemporaryDirectory() as directory:
            store = Store(Path(directory) / "workspace.sqlite")
            with sqlite3.connect(":memory:") as db:
                with self.assertRaisesRegex(PermissionError, "Current scheduled Reel"):
                    video_context(db, store, "app", "schedule:job", operation, {})
                with bound(store, {"id": "job", "attempts": 1, "data": {}}):
                    with self.assertRaisesRegex(PermissionError, "actor or datastore changed"):
                        video_context(db, store, "app", "schedule:other", operation, {})
                    with (
                        patch("mission_control.campaign_schedule_authority._leased_row", return_value=None),
                        self.assertRaisesRegex(PermissionError, "Reel job is unavailable"),
                    ):
                        video_context(db, store, "app", "schedule:job", operation, {})
                db.execute("CREATE TABLE organic_video_policies(app_id TEXT, id TEXT, data TEXT)")
                with self.assertRaisesRegex(PermissionError, "Reel policy is unavailable"):
                    video_deadline(db, "app", {"policy_id": "policy"}, {})
                item = dict(
                    item_id="item",
                    request={"intent_id": "intent", "intent_hash": "reviewed"},
                    operation=operation,
                    due_at="2027-01-01T00:00:00Z",
                )
                summary = dict(
                    kind=KIND,
                    app_id="app",
                    batch_id="batch",
                    scope_id="policy",
                    scope_hash="hash",
                    items=[item],
                    owner="owner",
                )
                data = dict(
                    batch_id="batch", item_id="item", scope_id="policy", operation=operation, request=item["request"]
                )
                row = dict(
                    summary=canonical(summary),
                    summary_hash=digest(summary),
                    body=canonical(item),
                    body_hash=digest(item),
                    data=canonical(data),
                    batch_id="batch",
                    job_id="job",
                    due=iso_time(item["due_at"]).timestamp(),
                )
                active = (str(store.path), "job", 1, digest(data))
                with self.assertRaisesRegex(PermissionError, "Reel inputs changed"):
                    video_content(db, row, active, "app", operation, {"intent_id": "substitute"})
                intent = dict(
                    hash="replaced", data=canonical({"request": {"policy_id": "policy", "policy_hash": "hash"}})
                )
                with (
                    patch("mission_control.campaign_video_execution._row", return_value=intent),
                    self.assertRaisesRegex(PermissionError, "Reel intent or policy changed"),
                ):
                    video_content(db, row, active, "app", operation, {"intent_id": "intent"})

    def test_a_matching_scope_cannot_authorize_a_different_batch(self) -> None:
        scope = {
            "scope_id": "scope",
            "approval_hash": "hash",
            "owner_principal": "owner",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        summary = {"batch_id": "approved", "app_id": "app", "scope_id": "scope", "scope_hash": "hash", "owner": "owner"}
        check_scope({"batch_id": "approved"}, summary, "app", scope)
        with self.assertRaisesRegex(PermissionError, "Scheduled campaign batch changed"):
            check_scope({"batch_id": "other"}, summary, "app", scope)

    def test_a_matching_batch_cannot_replace_scope_approval(self) -> None:
        scope = {
            "scope_id": "scope",
            "approval_hash": "reviewed",
            "owner_principal": "owner",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }
        summary = {
            "batch_id": "approved",
            "app_id": "app",
            "scope_id": "scope",
            "scope_hash": "other",
            "owner": "owner",
        }
        with self.assertRaisesRegex(PermissionError, "Scheduled campaign scope changed"):
            check_scope({"batch_id": "approved"}, summary, "app", scope)

    def test_reviewed_deadline_denies_at_equality(self) -> None:
        expiry = "2030-01-01T00:00:00+00:00"
        with (
            patch("mission_control.campaign_schedule_authority.time.time", return_value=1893456000),
            self.assertRaisesRegex(PermissionError, "Scheduled campaign approval expired"),
        ):
            check_deadline({"permission_expires_at": expiry}, "2099-01-01T00:00:00+00:00")

    def test_worker_lease_denies_at_equality(self) -> None:
        row = {
            "app_id": "app",
            "action": "campaign_post",
            "batch_status": "ACTIVE",
            "item_status": "QUEUED",
            "job_status": "RUNNING",
            "attempts": 1,
            "lease": 100,
            "due": 99,
        }
        with patch("mission_control.campaign_schedule_authority.time.time", return_value=100):
            check_lease(dict(row, lease=101), "app", ("workspace", "job", 1))
            with self.assertRaisesRegex(PermissionError, "Scheduled campaign worker lease changed"):
                check_lease(row, "app", ("workspace", "job", 1))
