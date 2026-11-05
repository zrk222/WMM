"""Agreement review of real campaign consent and captured schedule deadlines."""
from datetime import datetime, timedelta, timezone
import unittest

from mission_control.authority_expiry import AuthorityExpiry
from mission_control.automation_agreement import Agreement
from mission_control.campaign_schedule import CampaignSchedules
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from tests.test_campaign_schedule import ScheduleTests
from tests.test_verified_review import OWNER


class AgreementExpiryTests(unittest.TestCase):
    def setUp(self):
        self.f = ScheduleTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.addCleanup(self.f.tearDown)

    def review(self, scope, batch=None, observed=None):
        return Agreement(self.f.store, clock=lambda: observed or datetime.now(timezone.utc)).preview(
            'sample-one', OWNER, dict(manifest_version=1, workflow_policy_id=None,
                                     campaign_scope_id=scope, schedule_batch_id=batch))['summary']

    def extend(self, scope, days):
        service = AuthorityExpiry(self.f.store)
        review = service.preview('sample-one', OWNER, dict(kind='CAMPAIGN', id=scope,
                    expires=(datetime.now(timezone.utc) + timedelta(days=days)).isoformat()))
        service.confirm('sample-one', OWNER, dict(review, request_id=f'agreement-extension-{days}',
                                                   extended_expiry_consent=True))
        return review['preview']['new_expiry']

    def test_long_initial_issuance_is_visible_and_hash_bound(self):
        self.f.scope['expires_at'] = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
        self.f.scope['extended_expiry_consent'] = True
        scope = self.f.activate()
        result = self.review(scope['scope_id'])['campaign']
        self.assertTrue(result['approval']['extended_expiry_consent'])
        self.assertEqual(result['approval_hash'], scope['approval_hash'])
        self.assertEqual(result['permission_expires_at'], self.f.scope['expires_at'])
        self.assertEqual(result['consent_revision'], 1)

    def test_long_issuance_rejects_malformed_optional_consent(self):
        scope = self.f.activate()
        with connection(self.f.store.path) as db:
            import json
            row = db.execute(
                'SELECT summary FROM campaign_scopes WHERE id=?', (scope['scope_id'],)
            ).fetchone()
            saved = json.loads(row['summary'])
            saved['extended_expiry_consent'] = 1
            db.execute(
                'UPDATE campaign_scopes SET summary=?,summary_hash=? WHERE id=?',
                (canonical(saved), digest(saved), scope['scope_id']),
            )
        with self.assertRaisesRegex(Invalid, 'consent needs repair'):
            self.review(scope['scope_id'])

    def test_extension_and_independent_new_and_old_child(self):
        f = self.f
        service, old, active, _ = f.prepare_batch()
        scope = old['summary']['scope_id']
        original = old['summary']['permission_expires_at']
        with connection(f.store.path) as db:
            old_summary = db.execute(
                'SELECT summary FROM campaign_schedule_batches WHERE id=?', (active['id'],)
            ).fetchone()['summary']
        deadline = self.extend(scope, 3)
        due = datetime.now(timezone.utc) + timedelta(days=2)
        with f.owner_bound():
            new = service.prepare('sample-one', dict(scope_id=scope, items=[dict(due_at=due.isoformat(), request=f.post)]))
            service.activate('sample-one', new['summary']['batch_id'], new['summary_hash'])
        result = self.review(scope, new['summary']['batch_id'])
        self.assertEqual(result['campaign']['permission_expires_at'], deadline)
        self.assertEqual(result['schedule']['permission_expires_at'], deadline)
        self.assertEqual(result['campaign']['approval_hash'], old['summary']['scope_hash'])
        self.assertEqual(result['campaign']['approval']['expires_at'], original)
        self.assertEqual(result['schedule']['items'][0]['due_at'], due.isoformat())
        self.extend(scope, 5)
        later_parent_view = self.review(scope, new['summary']['batch_id'])
        self.assertNotEqual(later_parent_view['campaign']['permission_expires_at'], deadline)
        self.assertEqual(later_parent_view['schedule']['permission_expires_at'], deadline)
        with connection(f.store.path) as db:
            unchanged = db.execute(
                'SELECT summary FROM campaign_schedule_batches WHERE id=?', (active['id'],)
            ).fetchone()['summary']
        self.assertEqual(unchanged, old_summary)
        old_view = self.review(scope, active['id'], datetime.fromisoformat(original) + timedelta(seconds=1))
        self.assertIn('SCHEDULE_PERMISSION_EXPIRED', old_view['schedule']['blockers'])
        self.assertNotIn('CAMPAIGN_SCOPE_EXPIRED', old_view['campaign']['blockers'])
        with connection(f.store.path) as db:
            row = db.execute('SELECT summary FROM campaign_schedule_batches WHERE id=?', (active['id'],)).fetchone()
            import json
            saved = json.loads(row['summary'])
            saved['permission_expires_at'] = 'invalid'
            db.execute('UPDATE campaign_schedule_batches SET summary=?,summary_hash=? WHERE id=?',
                       (canonical(saved), digest(saved), active['id']))
        with self.assertRaises((Invalid, ValueError)):
            self.review(scope, active['id'])

    def test_schedule_summary_hash_and_parent_bound_tampering_reject(self):
        f = self.f
        _, old, active, _ = f.prepare_batch()
        scope = old['summary']['scope_id']
        with connection(f.store.path) as db:
            row = db.execute(
                'SELECT summary,summary_hash FROM campaign_schedule_batches WHERE id=?',
                (active['id'],),
            ).fetchone()
            saved = __import__('json').loads(row['summary'])
            saved['permission_expires_at'] = (
                datetime.now(timezone.utc) + timedelta(days=10)
            ).isoformat()
            db.execute(
                'UPDATE campaign_schedule_batches SET summary=? WHERE id=?',
                (canonical(saved), active['id']),
            )
        with self.assertRaisesRegex(Invalid, 'summary integrity'):
            self.review(scope, active['id'])

        with connection(f.store.path) as db:
            db.execute(
                'UPDATE campaign_schedule_batches SET summary_hash=? WHERE id=?',
                (digest(saved), active['id']),
            )
        with self.assertRaisesRegex(Invalid, 'exceeds campaign authority'):
            self.review(scope, active['id'])


if __name__ == '__main__':
    unittest.main()
