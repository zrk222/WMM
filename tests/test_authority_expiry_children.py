"""Retained child deadlines over real consent chains and synthetic provider edges."""
from datetime import datetime, timedelta, timezone
import json
import time
import unittest
from unittest.mock import patch

from mission_control.authority_expiry import AuthorityExpiry
from mission_control import campaign_monitor as monitor
from mission_control import campaign_monitor_authority as monitor_authority
from mission_control import campaign_schedule as schedule
from mission_control import campaign_schedule_authority as schedule_authority
from mission_control.common import Invalid, canonical, digest, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.organic_video_schedule import VideoSchedules
from mission_control.worker import run_once
from tests import test_campaign_monitor as monitor_fixture
from tests import test_campaign_execution as paid_fixture
from tests import test_campaign_schedule as schedule_fixture
from tests import test_campaign_video_execution as video_fixture
from tests.test_verified_review import OWNER as HTTP_OWNER


def extend(store, app, kind, identity, owner):
    service = AuthorityExpiry(store)
    review = service.preview(app, dict(principal=owner), dict(kind=kind, id=identity,
                             expires=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat()))
    service.confirm(app, dict(principal=owner), dict(review, request_id='child-boundary-extension',
                                                   extended_expiry_consent=True))
    return review['preview']['new_expiry']


class ScheduleChildTests(unittest.TestCase):
    def setUp(self):
        self.fixture = schedule_fixture.ScheduleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)

    def test_check_deadline_requires_current_capture_or_legacy_expiry_with_zero_grace(self):
        clock = datetime.now(timezone.utc)
        later = (clock + timedelta(days=2)).isoformat()
        with patch('time.time', return_value=clock.timestamp()):
            with self.assertRaises(PermissionError):
                schedule_authority.check_deadline({'permission_expires_at': clock.isoformat()}, later)
            with self.assertRaises(PermissionError):
                schedule_authority.check_deadline({}, clock.isoformat())
            schedule_authority.check_deadline({'permission_expires_at': later}, clock.isoformat())
            with self.assertRaises(Invalid):
                schedule_authority.check_deadline({'permission_expires_at': 'ambiguous'}, later)

    def test_old_schedule_deadline_stays_frozen_when_parent_extends(self):
        f = self.fixture
        service, draft, active, _ = f.prepare_batch()
        child = draft['summary']['permission_expires_at']
        original_hash = draft['summary_hash']
        extend(f.store, 'sample-one', 'CAMPAIGN', draft['summary']['scope_id'], HTTP_OWNER['principal'])
        with connection(f.store.path) as db:
            row = db.execute('SELECT summary,summary_hash FROM campaign_schedule_batches WHERE id=?', (active['id'],)).fetchone()
            self.assertEqual(row['summary_hash'], original_hash)
            self.assertEqual(json.loads(row['summary'])['permission_expires_at'], child)
        with patch('time.time', return_value=datetime.fromisoformat(child).timestamp()):
            schedule.tick(f.store)
            self.assertTrue(run_once(f.store))
            self.assertFalse(run_once(f.store))
        self.assertEqual(f.wire.posts, 0)
        with f.owner_bound():
            self.assertEqual(service.status('sample-one', active['id'])['items'][0]['job_status'], 'BLOCKED')

    def test_legacy_schedule_falls_back_to_original_scope_expiry(self):
        f = self.fixture
        _, draft, active, _ = f.prepare_batch()
        with connection(f.store.path) as db:
            legacy = dict(draft['summary']); original = legacy.pop('permission_expires_at')
            db.execute('UPDATE campaign_schedule_batches SET summary=?,summary_hash=? WHERE id=?',
                       (canonical(legacy), digest(legacy), active['id']))
        from tests.test_verified_review import OWNER
        extend(f.store, 'sample-one', 'CAMPAIGN', draft['summary']['scope_id'], OWNER['principal'])
        with patch('time.time', return_value=datetime.fromisoformat(original).timestamp()):
            schedule.tick(f.store)
            run_once(f.store)
        self.assertEqual(f.wire.posts, 0)

    def test_new_schedule_uses_effective_parent_and_executes_due_item_once(self):
        f = self.fixture
        scope = f.activate()
        from tests.test_verified_review import OWNER
        deadline = extend(f.store, 'sample-one', 'CAMPAIGN', scope['scope_id'], OWNER['principal'])
        due = datetime.now(timezone.utc) + timedelta(days=2)
        service = schedule.CampaignSchedules(f.store)
        with f.owner_bound():
            draft = service.prepare('sample-one', dict(scope_id=scope['scope_id'],
                                    items=[dict(due_at=due.isoformat(), request=f.post)]))
            self.assertEqual(draft['summary']['permission_expires_at'], deadline)
            service.activate('sample-one', draft['summary']['batch_id'], draft['summary_hash'])
        with patch('time.time', return_value=due.timestamp() + 1):
            self.assertEqual(schedule.tick(f.store), 1)
            self.assertTrue(run_once(f.store))
            self.assertEqual(schedule.tick(f.store), 0)
            self.assertFalse(run_once(f.store))
        self.assertEqual(f.wire.posts, 1)


class MonitorChildTests(unittest.TestCase):
    def setUp(self):
        self.fixture = monitor_fixture.CampaignMonitorTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_monitor_final_provider_admission_checks_own_expiry_after_parent_extension(self):
        f = self.fixture
        plan, job = f.job()
        deadline = datetime.fromisoformat(plan['summary']['proposal']['expires_at']).timestamp()
        extend(f.store, 'sample', 'CAMPAIGN', f.scope['scope_id'], 'owner')
        with connection(f.store.path) as db:
            db.execute('UPDATE jobs SET lease=? WHERE id=?', (deadline + 60, job['id']))
        with monitor_authority.bound(f.store, job) as capability:
            capability.update(action='RECONCILE', intent_id=f.intent['id'])
            with patch('time.time', return_value=deadline):
                with self.assertRaises(PermissionError):
                    monitor_authority.admit(f.store)
        with connection(f.store.path) as db:
            self.assertEqual(db.execute('SELECT units FROM campaign_monitors WHERE id=?', (plan['id'],)).fetchone()[0], 0)

    def test_new_monitor_can_choose_later_effective_parent_bound_without_changing_old_plan(self):
        f = self.fixture
        old = f.activate()
        original = old['summary_hash']
        extend(f.store, 'sample', 'CAMPAIGN', f.scope['scope_id'], 'owner')
        chosen = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        with f.owner():
            draft = f.monitors.prepare('sample', f.body(expires_at=chosen))
            new = f.monitors.activate('sample', draft['id'], draft['summary_hash'])
        self.assertEqual(new['summary']['proposal']['expires_at'], chosen)
        with connection(f.store.path) as db:
            self.assertEqual(db.execute('SELECT summary_hash FROM campaign_monitors WHERE id=?', (old['id'],)).fetchone()[0], original)
        # Its parent formerly expired after one hour. The new monitor is still
        # current before its own date and within the fixture's provider expiry.
        with patch('time.time', return_value=time.time() + 3700), connection(f.store.path) as db:
            row = db.execute('SELECT * FROM campaign_monitors WHERE id=?', (new['id'],)).fetchone()
            self.assertEqual(monitor.checked(db, row)['proposal']['expires_at'], chosen)


class PaidChildTests(unittest.TestCase):
    def test_new_paid_schedule_due_and_end_use_effective_permission_without_extra_budget(self):
        f = paid_fixture.PaidTests()
        f.setUp()
        self.addCleanup(f.doCleanups)
        extend(f.store, 'sample', 'CAMPAIGN', f.paid_scope['scope_id'], 'owner')
        scope = f.service.get_scope('sample', f.paid_scope['scope_id'])
        due = datetime.now(timezone.utc) + timedelta(days=1)
        body = dict(f.adbody, end_time=(due + timedelta(days=1)).isoformat())
        item = dict(operation='campaign.ad-launch', due_at=due.isoformat(), request=body)
        with connection(f.store.path) as db:
            self.assertEqual(schedule.prepare_item(item, scope, db, 'sample')[2]['end_time'], body['end_time'])
            body['end_time'] = (due + timedelta(days=3)).isoformat()
            with self.assertRaises(PermissionError):
                schedule.prepare_item(item, scope, db, 'sample')
        self.assertEqual(scope['max_total_minor'], 100)
        self.assertEqual(f.transport.objects, {})


class ReelChildTests(unittest.TestCase):
    def setUp(self):
        self.fixture = video_fixture.ReelExecutionTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_reel_capture_expiry_blocks_next_mutation_but_preserves_owner_recovery(self):
        f = self.fixture
        intent = f.intent()
        old_deadline = f.admitted['data']['permission_expires_at']
        extend(f.store, video_fixture.APP, 'ORGANIC_POLICY', f.policy['id'], video_fixture.OWNER['principal'])
        class Clock:
            at = datetime.now(timezone.utc)
            @classmethod
            def now(cls, tz=None):
                return cls.at
        def expire_after_create(action):
            if action == 'create':
                Clock.at = datetime.fromisoformat(old_deadline)
        f.transport.hook = expire_after_create
        with patch('mission_control.organic_video_policy.datetime', Clock):
            with self.assertRaisesRegex(PermissionError, 'child authority expired'):
                f.call('execute', dict(intent_id=intent['id']))
            recovered = f.call('reconcile', dict(intent_id=intent['id']))
            self.assertEqual(recovered['remote_id'], '456')
            with self.assertRaises(PermissionError):
                f.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(f.transport.calls, ['create', 'read'])
        self.assertNotIn('upload', f.transport.calls)
        self.assertNotIn('publish', f.transport.calls)

    def test_legacy_reel_admission_falls_back_to_immutable_policy_deadline(self):
        f = self.fixture
        with connection(f.store.path) as db:
            legacy = dict(f.admitted['data']); legacy.pop('permission_expires_at')
            admission_hash = digest(legacy)
            # Construct a pre-capture database fixture. Restore the production
            # immutability trigger before exercising any service entry point.
            trigger = db.execute("SELECT sql FROM sqlite_master WHERE name='organic_video_admissions_no_update'").fetchone()[0]
            db.execute('DROP TRIGGER organic_video_admissions_no_update')
            try:
                db.execute('UPDATE organic_video_admissions SET data=?,hash=? WHERE id=?',
                           (canonical(legacy), admission_hash, f.admitted['id']))
            finally:
                db.execute(trigger)
        f.body['admission_hash'] = admission_hash
        intent = f.intent()
        extend(f.store, video_fixture.APP, 'ORGANIC_POLICY', f.policy['id'], video_fixture.OWNER['principal'])
        expired = datetime.fromisoformat(f.policy['data']['policy']['expires_at'])
        with patch('mission_control.organic_video_policy.datetime') as clock:
            clock.now.return_value = expired
            with self.assertRaisesRegex(PermissionError, 'child authority expired'):
                f.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(f.transport.calls, [])

    def long_intent(self):
        f = self.fixture
        policy = f.fixture.create(dict(f.fixture.policy, mode='STANDING_GENERATED',
                                      approved_output_hashes=[], max_calls=40))
        deadline = extend(f.store, video_fixture.APP, 'ORGANIC_POLICY', policy['id'], video_fixture.OWNER['principal'])
        admitted = f.fixture.call('admit', f.fixture.admission(policy, reserve_calls=20))
        self.assertEqual(admitted['data']['permission_expires_at'], deadline)
        output = admitted['data']['output']
        f.body = dict(f.body, request_id=uid(), policy_id=policy['id'], policy_hash=policy['hash'],
                      admission_id=admitted['id'], admission_hash=admitted['hash'],
                      artifact_id=output['artifact_id'], artifact_sha256=output['artifact_sha256'])
        return f.intent(), deadline

    def test_extended_generation_permission_cannot_publish_unreviewed_reel(self):
        f = self.fixture
        intent, _ = self.long_intent()
        later = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch('mission_control.organic_video_policy.datetime') as clock:
            clock.now.return_value = later
            with self.assertRaisesRegex(PermissionError, 'approve this exact rendered Reel'):
                f.call('execute', dict(intent_id=intent['id']))
        self.assertEqual(f.transport.calls, [])

    def test_scheduled_reel_uses_its_captured_item_deadline_after_original_policy_expiry(self):
        f = self.fixture
        intent, deadline = self.long_intent()
        due = datetime.now(timezone.utc) + timedelta(hours=2)
        service = VideoSchedules(f.store)
        from mission_control import campaign_video_execution as video
        body = dict(policy_id=f.body['policy_id'], policy_hash=f.body['policy_hash'],
                    items=[dict(intent_id=intent['id'], due_at=due.isoformat())])
        envelope = dict(app_id=video_fixture.APP, operation='organic-video.schedule-prepare', input=body)
        with bound_owner(f.store, envelope, f.fixture.sessions, 'fixture-session', video_fixture.OWNER), protected(f.store, envelope):
            draft = service.prepare(video_fixture.APP, body)
        self.assertEqual(draft['summary']['items'][0]['permission_expires_at'], deadline)
        activation = dict(batch_id=draft['summary']['batch_id'], summary_hash=draft['summary_hash'])
        envelope = dict(app_id=video_fixture.APP, operation='organic-video.schedule-activate', input=activation)
        with bound_owner(f.store, envelope, f.fixture.sessions, 'fixture-session', video_fixture.OWNER), protected(f.store, envelope):
            service.activate(video_fixture.APP, activation)
        f.transport.Context = video.provider.Context
        with patch('time.time', return_value=due.timestamp() + 1), patch.object(video, 'provider', f.transport):
            self.assertEqual(schedule.tick(f.store), 1)
            self.assertTrue(run_once(f.store))
            self.assertFalse(run_once(f.store))
        self.assertEqual(f.transport.calls.count('publish'), 1)
        with connection(f.store.path) as db:
            self.assertEqual(video._row(db, video_fixture.APP, intent['id'])['stage'], 'PROVIDER_PHASE_COMPLETE')


if __name__ == '__main__':
    unittest.main()
