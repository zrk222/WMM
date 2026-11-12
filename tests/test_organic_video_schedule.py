"""Shared durable queue, exact retained video capability and no replay on restart."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

from mission_control import campaign_video_execution as video
from mission_control.campaign_schedule import CampaignSchedules, execute, tick
from mission_control.campaign_schedule_authority import bound
from mission_control.campaign_video_transport import Context
from mission_control.common import Invalid, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.organic_video_schedule import VideoSchedules
from mission_control.worker import claim, run_once
from tests.test_campaign_video_execution import Transport
from tests import test_organic_video_access as gateway_fixture
from tests import test_organic_video_policy as fixture

APP = fixture.APP


class VideoScheduleTests(unittest.TestCase):
    setUp_base = gateway_fixture.VideoGatewayTests.setUp_base
    close = gateway_fixture.VideoGatewayTests.close
    request = gateway_fixture.VideoGatewayTests.request
    setUp = gateway_fixture.VideoGatewayTests.setUp
    call = gateway_fixture.VideoGatewayTests.call
    admit = gateway_fixture.VideoGatewayTests.admit
    intent = gateway_fixture.VideoGatewayTests.intent

    @contextmanager
    def owner_bound(self, action, body):
        envelope = dict(app_id=APP, operation="organic-video." + action, input=body)
        with bound_owner(self.store, envelope, self.server.identities, self.owner.csrf, fixture.OWNER):
            with protected(self.store, envelope):
                yield

    def scheduled(self):
        intent = self.intent()
        due = datetime.now(timezone.utc) + timedelta(seconds=20)
        body = dict(
            policy_id=self.policy["id"],
            policy_hash=self.policy["hash"],
            items=[dict(intent_id=intent["id"], due_at=due.isoformat())],
        )
        schedules = VideoSchedules(self.store)
        with self.owner_bound("schedule-prepare", body):
            draft = schedules.prepare(APP, body)
        activation = dict(batch_id=draft["summary"]["batch_id"], summary_hash=draft["summary_hash"])
        with self.owner_bound("schedule-activate", activation):
            active = schedules.activate(APP, activation)
        return schedules, active, due.timestamp(), intent, body

    @contextmanager
    def provider(self, wire):
        wire.Context = Context

        def facebook(config, secret, token, alive):
            alive()
            return SimpleNamespace(
                subject_id="fixture-subject",
                permissions=["pages_manage_posts", "pages_show_list", "pages_read_engagement"],
            )

        def page(secret, token, identity, alive):
            alive()
            return dict(id="123", tasks=["CREATE_CONTENT"]), "synthetic-page"

        with (
            patch.object(
                video, "_credentials", return_value=({}, "synthetic-secret", dict(access_token="synthetic-user"))
            ),
            patch.object(video, "facebook", side_effect=facebook),
            patch.object(video, "selected_page", side_effect=page),
            patch.object(video, "provider", wire),
        ):
            yield

    def test_shared_tick_executes_once_and_owner_history_retains_exact_intent(self):
        self.policy = self.request(
            "policy-create",
            dict(
                request_id=uid(),
                policy=dict(
                    self.f.policy,
                    mode="STANDING_GENERATED",
                    approved_output_hashes=[],
                    max_calls=40,
                ),
            ),
        )
        schedules, active, due, intent, _ = self.scheduled()
        wire = Transport()
        with patch("time.time", return_value=due + 1), self.provider(wire):
            self.assertEqual(tick(self.store), 1)
            self.assertEqual(tick(self.store), 0)
            self.assertTrue(run_once(self.store))
            self.assertFalse(run_once(self.store))
        with self.owner_bound("schedule-status", dict(batch_id=active["id"])):
            saved = CampaignSchedules(self.store).status(APP, active["id"])
            self.assertEqual(CampaignSchedules(self.store).history(APP)["batches"][0], saved)
        self.assertEqual(saved["items"][0]["intent"]["id"], intent["id"])
        self.assertEqual(saved["items"][0]["job_status"], "SUCCEEDED")
        self.assertEqual(saved["items"][0]["intent"]["stage"], "PROVIDER_PHASE_COMPLETE")
        self.assertEqual(saved["items"][0]["intent"]["public_visibility"], "NOT_VERIFIED")
        self.assertEqual(wire.calls.count("publish"), 1)

    def test_off_cancels_shared_queue_and_prevents_provider_calls(self):
        _, active, due, _, _ = self.scheduled()
        wire = Transport()
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            with self.owner_bound("schedule-revoke", dict(batch_id=active["id"], version=active["version"])):
                saved = CampaignSchedules(self.store).revoke(APP, active["id"], active["version"])
            self.assertEqual(saved["status"], "OFF")
            self.assertFalse(run_once(self.store))
        self.assertEqual(wire.calls, [])

    def test_current_upload_progress_renews_only_the_live_worker_lease(self):
        _, _, due, intent, _ = self.scheduled()
        clock = [due + 1]
        wire = Transport()
        wire.hook = lambda action: clock.__setitem__(0, clock[0] + 20)
        with patch("time.time", side_effect=lambda: clock[0]), self.provider(wire):
            tick(self.store)
            self.assertTrue(run_once(self.store))
        self.assertGreater(clock[0], due + 60)
        with connection(self.store.path) as db:
            self.assertEqual(video._row(db, APP, intent["id"])["stage"], "PROVIDER_PHASE_COMPLETE")
        self.assertEqual(wire.calls.count("publish"), 1)

    def test_source_rights_revoked_after_queue_stop_execution(self):
        _, _, due, _, _ = self.scheduled()
        wire = Transport()
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            self.f.media.review(
                APP, self.f.source["id"], dict(self.f.review, expected_version=1, status="REVOKED"), fixture.OWNER
            )
            self.assertTrue(run_once(self.store))
        self.assertEqual(wire.calls, [])

    def test_off_during_upload_blocks_finish_without_erasing_remote_identity(self):
        _, active, due, intent, _ = self.scheduled()
        wire = Transport()

        def off(action):
            if action == "upload":
                with self.owner_bound("schedule-revoke", dict(batch_id=active["id"], version=active["version"])):
                    CampaignSchedules(self.store).revoke(APP, active["id"], active["version"])

        wire.hook = off
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            self.assertTrue(run_once(self.store))
        self.assertNotIn("publish", wire.calls)
        with connection(self.store.path) as db:
            self.assertEqual(video._row(db, APP, intent["id"])["remote_id"], "456")

    def test_lost_finish_and_expired_running_lease_are_never_replayed(self):
        _, active, due, intent, _ = self.scheduled()
        wire = Transport()
        wire.failure = "publish"
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            self.assertTrue(run_once(self.store))
            self.assertFalse(run_once(self.store))
        self.assertEqual(wire.calls.count("publish"), 1)
        with connection(self.store.path) as db:
            retained = video._view(video._row(db, APP, intent["id"]))
        self.assertEqual(retained["stage"], "FINISH_PENDING")
        self.assertTrue(retained["recovery_required"])
        with patch("time.time", return_value=due + 100), self.provider(wire):
            self.assertFalse(run_once(self.store))
        self.assertEqual(wire.calls.count("publish"), 1)

    def test_retained_capability_rejects_wrong_attempt_tampering_and_scheduled_reconcile(self):
        _, active, due, intent, _ = self.scheduled()
        with patch("time.time", return_value=due + 1):
            tick(self.store)
            job = claim(self.store)
            with bound(self.store, job), connection(self.store.path) as db:
                with self.assertRaises(PermissionError):
                    video._authority(
                        db,
                        self.store,
                        APP,
                        "schedule:" + job["id"],
                        "organic-video.intent-reconcile",
                        dict(intent_id=intent["id"]),
                    )
            with self.assertRaises(PermissionError):
                execute(self.store, dict(job, attempts=job["attempts"] + 1))
            with connection(self.store.path) as db:
                db.execute("UPDATE campaign_schedule_items SET body=? WHERE batch_id=?", ("{}", active["id"]))
            with self.assertRaises((PermissionError, KeyError)):
                execute(self.store, job)
        with patch("time.time", return_value=due + 100):
            self.assertIsNone(claim(self.store))

    def test_revoked_policy_stops_dispatch_and_duplicate_intent_cannot_be_rescheduled(self):
        schedules, _, due, _, body = self.scheduled()
        with self.owner_bound("schedule-prepare", body):
            with self.assertRaises(Invalid):
                schedules.prepare(APP, body)
        self.request("policy-revoke", dict(policy_id=self.policy["id"], policy_hash=self.policy["hash"]))
        wire = Transport()
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            self.assertTrue(run_once(self.store))
        self.assertEqual(wire.calls, [])


if __name__ == "__main__":
    unittest.main()
