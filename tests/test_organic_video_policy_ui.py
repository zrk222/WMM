"""Bounded policy GUI reads use the real owner-policy fixture and local SQLite."""
from datetime import datetime, timedelta, timezone
import json
import socket
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, canonical, digest, uid
from mission_control.operation_authority import bound_owner, protected
from mission_control.organic_video_policy_ui import context, history
from tests import test_organic_video_policy as policy_fixture


APP = policy_fixture.APP
OWNER = policy_fixture.OWNER


class OrganicPolicyOwnerReadTests(unittest.TestCase):
    def setUp(self):
        policy_fixture.OrganicPolicyTests.setUp(self)

    def call(self, operation, body, app_id=APP, actor=OWNER['principal']):
        if operation in {'create', 'read', 'revoke', 'reserve', 'admit'}:
            return policy_fixture.OrganicPolicyTests.call(self, operation, body)
        envelope = dict(app_id=app_id, operation='organic-video.' + operation, input=body)
        with bound_owner(self.store, envelope, self.sessions, 'fixture-session', OWNER):
            with protected(self.store, envelope):
                if operation == 'policy-context':
                    return context(self.store, app_id, actor, body)
                return history(self.store, app_id, actor, body)

    def create_policy(self):
        return policy_fixture.OrganicPolicyTests.create(self)

    def test_context_requires_exact_owner_envelope_and_returns_current_selections(self):
        self.create_policy()
        with patch.object(socket, 'create_connection', side_effect=AssertionError('network access')):
            value = self.call('policy-context', {})
        self.assertEqual(set(value), {'app', 'review', 'pages', 'eligible', 'approved_outputs', 'missing'})
        self.assertEqual(value['app']['id'], APP)
        self.assertEqual(value['pages'][0]['connection_id'], policy_fixture.CONNECTION)
        self.assertEqual(value['pages'][0]['binding']['version'], 1)
        self.assertEqual(value['eligible']['sources'], [dict(id=self.source['id'], title='demo.mp4',
            sha256=self.source['source_sha256'], review_version=1)])
        self.assertEqual(len(value['eligible']['claims']), len(self.claims))
        self.assertEqual(value['approved_outputs'], [])
        self.assertEqual(value['missing'], [])
        with self.assertRaises(Invalid):
            self.call('policy-context', {'app_id': APP})

    def test_history_exact_request_reconciliation_usage_and_paging_shape(self):
        saved = self.create_policy()
        request = dict(offset=0, request_id=self.creation['request_id'])
        page = self.call('policy-history', request)
        self.assertEqual(set(page), {'items', 'total', 'offset', 'limit', 'next_offset'})
        self.assertEqual((page['total'], page['offset'], page['limit'], page['next_offset']), (1, 0, 100, None))
        item = page['items'][0]
        self.assertEqual(set(item), {'id', 'hash', 'request_id', 'request_hash', 'created', 'snapshot',
                                     'currentness', 'revoked', 'expired', 'app_current', 'owner_current', 'usage', 'remaining'})
        self.assertEqual((item['id'], item['hash'], item['request_id'], item['request_hash']),
                         (saved['id'], saved['hash'], self.creation['request_id'], digest(self.creation)))
        self.assertEqual(item['snapshot'], saved['data'])
        self.assertEqual(item['currentness'], 'CURRENTNESS_NOT_REVALIDATED')
        self.assertFalse(item['revoked'] or item['expired'])
        self.assertTrue(item['app_current'] and item['owner_current'])
        self.assertEqual(item['usage'], dict(generations_held=0, artifact_slots_admitted=0,
            provider_calls_reserved=0, provider_calls_used=0, provider_phase_complete=0))
        self.assertEqual(item['remaining'], dict(generations=2, artifact_slots=2, provider_calls=8))
        self.assertEqual(self.call('policy-history', dict(offset=0, request_id='absent'))['items'], [])
        self.assertEqual(self.call('policy-history', dict(offset=0, request_id=None)), page | {'items': page['items']})
        for body in (dict(offset=True, request_id=None), dict(offset=2001, request_id=None),
                     dict(offset=0, request_id=''), dict(offset=0, request_id=None, owner=OWNER)):
            with self.subTest(body=body), self.assertRaises(Invalid):
                self.call('policy-history', body)

    def test_history_marks_revocation_expiry_and_app_or_owner_staleness_without_revalidating_rights(self):
        saved = self.create_policy()
        self.call('policy-history', dict(offset=0, request_id=None))
        self.call('revoke', dict(policy_id=saved['id'], policy_hash=saved['hash']))
        revoked = self.call('policy-history', dict(offset=0, request_id=None))['items'][0]
        self.assertTrue(revoked['revoked'])
        future = datetime.now(timezone.utc) + timedelta(days=2)
        class Clock:
            @staticmethod
            def now(tz=None):
                return future
        with patch('mission_control.organic_video_policy_ui.datetime', Clock):
            expired = self.call('policy-history', dict(offset=0, request_id=None))['items'][0]
        self.assertTrue(expired['expired'])
        self.assertTrue(expired['app_current'])
        self.assertEqual(expired['currentness'], 'CURRENTNESS_NOT_REVALIDATED')

    def test_policy_history_integrity_fails_closed_and_wrong_envelope_is_denied(self):
        saved = self.create_policy()
        with patch('socket.create_connection', side_effect=AssertionError('network access')):
            with self.assertRaises(PermissionError):
                self.call('policy-history', dict(offset=0, request_id=None), app_id='other-app')
        with policy_fixture.connection(self.store.path) as db:
            db.execute('DROP TRIGGER organic_video_policies_no_update')
            db.execute('UPDATE organic_video_policies SET data=? WHERE id=?', ('{}', saved['id']))
        with self.assertRaises(Invalid):
            self.call('policy-history', dict(offset=0, request_id=None))

    def test_history_pagination_is_stable_and_bounded_to_one_hundred(self):
        saved = self.create_policy()
        policy_data = saved['data']
        from mission_control.common import now
        with policy_fixture.connection(self.store.path) as db:
            for index in range(101):
                identity = uid()
                request_id = uid()
                snapshot = dict(policy_data, app_id=APP)
                db.execute('INSERT INTO organic_video_policies VALUES(?,?,?,?,?,?,?)',
                           (APP, identity, request_id, digest(dict(request_id=request_id, policy=snapshot['policy'])),
                            canonical(snapshot), digest(snapshot), now()))
        first = self.call('policy-history', dict(offset=0, request_id=None))
        second = self.call('policy-history', dict(offset=100, request_id=None))
        self.assertEqual((len(first['items']), first['limit'], first['next_offset']), (100, 100, 100))
        self.assertEqual((len(second['items']), second['next_offset']), (2, None))
        again = self.call('policy-history', dict(offset=0, request_id=None))
        self.assertEqual([r['id'] for r in first['items']], [r['id'] for r in again['items']])


if __name__ == '__main__':
    unittest.main()
