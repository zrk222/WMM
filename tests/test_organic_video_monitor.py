"""Real shared worker phase continuation; no live account or blind mutation retry."""

from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch

from mission_control.campaign_schedule import tick, execute
from mission_control.db import connection
from mission_control.common import canonical, digest
from mission_control import campaign_video_execution as video
from mission_control.organic_video_monitor import CONFIG
from mission_control.worker import run_once
from tests import test_organic_video_schedule as fixture
from tests import test_organic_video_policy as policies
from tests.test_campaign_video_execution import Transport

APP = policies.APP


class VideoObservationTests(unittest.TestCase):
    setUp_base = fixture.VideoScheduleTests.setUp_base
    setUp = fixture.VideoScheduleTests.setUp
    close = fixture.VideoScheduleTests.close
    request = fixture.VideoScheduleTests.request
    call = fixture.VideoScheduleTests.call
    admit = fixture.VideoScheduleTests.admit
    intent = fixture.VideoScheduleTests.intent
    owner_bound = fixture.VideoScheduleTests.owner_bound
    scheduled = fixture.VideoScheduleTests.scheduled
    provider = fixture.VideoScheduleTests.provider

    def start_processing(self):
        service, active, due, intent, body = self.scheduled()
        wire = Transport()
        wire.processing = True
        with patch("time.time", return_value=due + 1), self.provider(wire):
            self.assertEqual(tick(self.store), 1)
            self.assertTrue(run_once(self.store))
            self.assertEqual(tick(self.store), 0)
        return service, active, due, intent, wire

    def saved(self, service, active):
        with self.owner_bound("schedule-status", dict(batch_id=active["id"])):
            return service.status(APP, active["id"])

    def test_restart_processing_to_one_finish_retains_every_job_and_due_time(self):
        service, active, due, intent, wire = self.start_processing()
        first = self.saved(service, active)
        item = first["items"][0]
        self.assertEqual(first["summary"]["monitoring"], CONFIG)
        self.assertEqual(item["phase_checks"]["observation"]["state"], "WAITING")
        self.assertEqual(len(item["phase_checks"]["jobs"]), 1)
        with patch("time.time", return_value=due + 20):
            self.assertEqual(tick(self.store), 0)
        wire.processing = False
        with patch("time.time", return_value=due + 32), self.provider(wire):
            self.assertEqual(tick(self.store), 1)
            self.assertEqual(tick(self.store), 0)
            self.assertTrue(run_once(self.store))
            self.assertFalse(run_once(self.store))
        with patch("time.time", return_value=due + 63):
            self.assertEqual(tick(self.store), 0)
        final = self.saved(service, active)
        self.assertEqual(final["summary"], first["summary"])
        self.assertEqual(final["items"][0]["intent"]["id"], intent["id"])
        self.assertEqual(final["items"][0]["intent"]["stage"], "PROVIDER_PHASE_COMPLETE")
        self.assertEqual(final["items"][0]["intent"]["public_visibility"], "NOT_VERIFIED")
        phase = final["items"][0]["phase_checks"]
        self.assertEqual(phase["observation"]["state"], "COMPLETE")
        self.assertEqual(len(phase["jobs"]), 2)
        self.assertEqual(wire.calls.count("create"), 1)
        self.assertEqual(wire.calls.count("upload"), 1)
        self.assertEqual(wire.calls.count("publish"), 1)

    def test_acknowledged_finish_continues_read_only_while_lost_finish_stays_held(self):
        service, active, due, _, _ = self.scheduled()
        wire = Transport()
        wire.hook = lambda action: setattr(wire, "processing", True) if action == "publish" else None
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            run_once(self.store)
            tick(self.store)
        self.assertEqual(self.saved(service, active)["items"][0]["intent"]["stage"], "FINISH_ACKNOWLEDGED")
        wire.processing = False
        with patch("time.time", return_value=due + 32), self.provider(wire):
            self.assertEqual(tick(self.store), 1)
            run_once(self.store)
        self.assertEqual(wire.calls.count("publish"), 1)
        self.assertEqual(self.saved(service, active)["items"][0]["intent"]["stage"], "PROVIDER_PHASE_COMPLETE")

    def test_lost_finish_never_queues_observation_or_repeats_finish(self):
        service, active, due, _, _ = self.scheduled()
        wire = Transport()
        wire.failure = "publish"
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            run_once(self.store)
            self.assertEqual(tick(self.store), 0)
        with patch("time.time", return_value=due + 100), self.provider(wire):
            self.assertEqual(tick(self.store), 0)
            self.assertFalse(run_once(self.store))
        saved = self.saved(service, active)["items"][0]
        self.assertEqual(saved["phase_checks"]["observation"]["state"], "BLOCKED")
        self.assertEqual(len(saved["phase_checks"]["jobs"]), 1)
        self.assertTrue(saved["intent"]["recovery_required"])
        self.assertEqual(wire.calls.count("publish"), 1)

    def test_revoked_rights_before_due_observation_block_without_calls(self):
        service, active, due, _, wire = self.start_processing()
        count = len(wire.calls)
        self.f.media.review(
            APP, self.f.source["id"], dict(self.f.review, expected_version=1, status="REVOKED"), policies.OWNER
        )
        with patch("time.time", return_value=due + 32), self.provider(wire):
            self.assertEqual(tick(self.store), 0)
        self.assertEqual(len(wire.calls), count)
        self.assertEqual(self.saved(service, active)["items"][0]["phase_checks"]["observation"]["state"], "BLOCKED")

    def test_finite_followup_and_reserved_call_limits_block_new_work(self):
        service, active, due, intent, wire = self.start_processing()
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_video_observations SET sequence=?", (CONFIG["max_followup_jobs"],))
        with patch("time.time", return_value=due + 32):
            self.assertEqual(tick(self.store), 0)
        phase = self.saved(service, active)["items"][0]["phase_checks"]
        self.assertIn("ceiling", phase["observation"]["reason"])
        self.assertEqual(len(phase["jobs"]), 1)
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_video_observations SET sequence=0,state='WAITING',next_due=0")
            db.execute("UPDATE campaign_video_intents SET calls=40 WHERE id=?", (intent["id"],))
        with patch("time.time", return_value=due + 33):
            self.assertEqual(tick(self.store), 0)
        self.assertEqual(self.saved(service, active)["items"][0]["phase_checks"]["observation"]["state"], "BLOCKED")

    def test_off_cancels_a_queued_followup(self):
        service, active, due, _, wire = self.start_processing()
        calls = len(wire.calls)
        with patch("time.time", return_value=due + 32), self.provider(wire):
            self.assertEqual(tick(self.store), 1)
            from mission_control.campaign_schedule import CampaignSchedules

            with self.owner_bound("schedule-revoke", dict(batch_id=active["id"], version=active["version"])):
                CampaignSchedules(self.store).revoke(APP, active["id"], active["version"])
            self.assertFalse(run_once(self.store))
        self.assertEqual(len(wire.calls), calls)
        self.assertEqual(self.saved(service, active)["items"][0]["phase_checks"]["effective_state"], "OFF")

    def test_previous_completed_job_cannot_borrow_new_followup_lease(self):
        service, active, due, _, wire = self.start_processing()
        from mission_control.worker import json_job

        with connection(self.store.path) as db:
            old = json_job(db.execute("SELECT * FROM jobs WHERE action='campaign_post'").fetchone())
        count = len(wire.calls)
        with patch("time.time", return_value=due + 32), self.provider(wire):
            self.assertEqual(tick(self.store), 1)
            with self.assertRaises(PermissionError):
                execute(self.store, old)
        self.assertEqual(len(wire.calls), count)
        self.assertEqual(len(self.saved(service, active)["items"][0]["phase_checks"]["jobs"]), 2)

    def test_pre_upgrade_schedule_does_not_gain_followup_authority(self):
        service, active, due, _, _ = self.scheduled()
        summary = dict(active["summary"])
        summary.pop("monitoring")
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_schedule_batches SET summary=?,summary_hash=? WHERE id=?",
                (canonical(summary), digest(summary), active["id"]),
            )
        wire = Transport()
        wire.processing = True
        with patch("time.time", return_value=due + 1), self.provider(wire):
            tick(self.store)
            run_once(self.store)
            self.assertEqual(tick(self.store), 0)
        with patch("time.time", return_value=due + 32), self.provider(wire):
            self.assertEqual(tick(self.store), 0)
            self.assertFalse(run_once(self.store))
        phase = self.saved(service, active)["items"][0]["phase_checks"]
        self.assertEqual(phase["observation"]["state"], "OFF")
        self.assertEqual(len(phase["jobs"]), 1)


if __name__ == "__main__":
    unittest.main()
