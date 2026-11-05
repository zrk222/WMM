"""Bounded, private projection over actual reviewed-dispatch SQLite records."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import json
import unittest
from unittest.mock import patch

from mission_control.agent_checkpoints import Checkpoints
from mission_control.agent_review_dispatch import ReviewedDispatch
from mission_control.common import canonical, digest
from mission_control.db import connection
from mission_control.review_access import Access
from mission_control.weekly_inbox import operation_exceptions, review
from tests import test_agent_review_policy as fixture
from tests import test_verified_review as ids


class WeeklyReviewActionsTests(unittest.TestCase):
    setUp_base = fixture.ReviewPolicyTests.setUp
    tearDown = fixture.ReviewPolicyTests.tearDown
    body = fixture.ReviewPolicyTests.body
    envelope = fixture.ReviewPolicyTests.envelope
    listing_body = fixture.ReviewPolicyTests.listing_body
    issue_reviewed = fixture.ReviewPolicyTests.issue_reviewed

    def setUp(self):
        self.setUp_base()
        self.access = Access(self.store)
        self.access.save('sample-one', ids.OWNER, ids.CHECKER,
                         dict(login=ids.CHECKER['login'], role='CHECKER', status='ACTIVE', version=None))
        self.access.save('sample-one', ids.OWNER, ids.STRANGER,
                         dict(login=ids.STRANGER['login'], role='MAKER', status='ACTIVE', version=None))
        self.issued = self.issue_reviewed()
        self.dispatch = ReviewedDispatch(self.server.service)
        self.checkpoints = Checkpoints(self.store)
        self.waiting = self.dispatch.prepare(self.issued['token'], 'review-one',
                                             self.envelope('growth.save', self.listing_body()))['checkpoint']

    def cards(self, user=ids.OWNER, app='sample-one'):
        return [c for c in operation_exceptions(self.store, self.store.app(app), user)
                if c['category'] == 'agent_review']

    def approve(self):
        return self.checkpoints.approve('sample-one', 'review-one', ids.CHECKER['principal'],
                                        self.waiting['revision'], self.waiting['hash'])

    def test_scope_no_campaign_and_private_read_only(self):
        with connection(self.store.path) as db:
            db.execute('DROP TABLE IF EXISTS campaign_scopes')
            before = canonical(list(db.iterdump()))
        owner, checker = self.cards(), self.cards(ids.CHECKER)
        self.assertEqual(len(owner), 1)
        self.assertEqual(owner[0]['title'], 'Review agent proposal')
        self.assertEqual(checker[0]['owner'], 'App checker')
        self.assertEqual(checker[0]['private_principal'], ids.CHECKER['principal'])
        self.assertFalse(checker[0]['owner_only'])
        self.assertEqual(checker[0]['action']['resource_id'], 'review-one')
        self.assertEqual(checker[0]['resolution_route'], 'agent_review')
        self.assertEqual(self.cards(ids.STRANGER), [])
        self.assertEqual(self.cards(None), [])
        self.assertEqual(self.cards(ids.OWNER, 'sample-two'), [])
        self.assertEqual(owner[0]['id'], self.cards()[0]['id'])
        self.assertEqual(owner[0]['source_receipt']['source_hash'], self.cards()[0]['source_receipt']['source_hash'])
        result = review(self.server.service, user=ids.CHECKER)
        self.assertEqual(result['owner_operations_principal'], ids.CHECKER['principal'])
        self.assertTrue(any(c['category'] == 'agent_review' for c in result['exceptions']))
        with connection(self.store.path) as db:
            self.assertEqual(before, canonical(list(db.iterdump())))
            db.execute("UPDATE operator_roles SET status='REVOKED' WHERE principal=?", (ids.CHECKER['principal'],))
        self.assertEqual(self.cards(ids.CHECKER), [])

    def test_maker_self_other_and_role_drift(self):
        # A former owner retains visibility only over their own request after role change.
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET role='MAKER',version=version+1 WHERE principal=?", (ids.OWNER['principal'],))
        self.assertEqual(self.cards()[0]['state'], 'CHECKPOINT_CONTEXT_CHANGED')
        self.assertEqual(self.cards()[0]['owner'], 'App maker')
        self.assertEqual(self.cards(ids.STRANGER), [])
        self.assertEqual(self.cards(ids.CHECKER)[0]['state'], 'CHECKPOINT_CONTEXT_CHANGED')
        # A corrupt packet must not spoof another maker into seeing a request.
        with connection(self.store.path) as db:
            row = json.loads(db.execute('SELECT data FROM agent_checkpoints').fetchone()[0])
            row['packet']['maker'] = ids.STRANGER['principal']
            db.execute('UPDATE agent_checkpoints SET data=?', (canonical(row),))
        self.assertEqual(self.cards(ids.STRANGER), [])
        self.assertEqual(self.cards()[0]['state'], 'SOURCE_UNAVAILABLE')

    def test_cancel_waiting_and_checker_role_change(self):
        approved = self.approve()
        with connection(self.store.path) as db:
            db.execute('UPDATE operator_roles SET version=version+1 WHERE principal=?', (ids.CHECKER['principal'],))
        self.assertEqual(self.cards()[0]['state'], 'CHECKPOINT_CONTEXT_CHANGED')
        self.checkpoints.cancel('sample-one', 'review-one', ids.OWNER['principal'], approved['revision'])
        self.assertEqual(self.cards(), [])

    def test_transitions_and_reconciliation_keep_history(self):
        approved = self.approve()
        self.assertEqual(self.cards(), [])
        running = self.checkpoints.claim('sample-one', 'review-one', 'generic-agent', approved['revision'], approved['hash'])
        self.assertEqual(self.cards(), [])
        uncertain = self.checkpoints.finish('sample-one', 'review-one', 'generic-agent', running['revision'], 'UNKNOWN', 'a'*64)
        self.assertEqual(self.cards()[0]['state'], 'UNKNOWN')
        self.checkpoints.reconcile('sample-one', 'review-one', ids.CHECKER['principal'], uncertain['revision'], 'FAILED', 'b'*64)
        self.assertEqual(self.cards(), [])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_review_requests').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT revision FROM agent_checkpoints').fetchone()[0], 5)

    def test_cancel_pending_and_running_expiry(self):
        approved = self.approve()
        running = self.checkpoints.claim('sample-one', 'review-one', 'generic-agent', approved['revision'], approved['hash'])
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_grants SET expires=?", ((datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat(),))
        card = self.cards()[0]
        self.assertEqual(card['state'], 'EXPIRED')
        self.assertIn('does not establish', card['next_action'])
        self.checkpoints.cancel('sample-one', 'review-one', ids.OWNER['principal'], running['revision'])
        card = self.cards()[0]
        self.assertIn('reconciliation', card['reason'])
        self.assertEqual(card['evidence']['state'], 'CANCEL_REQUESTED')

    def test_app_grant_drift_and_redacted_malformed_metadata(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_grants SET status='REVOKED'")
        self.assertEqual(self.cards()[0]['state'], 'GRANT_CONTEXT_CHANGED')
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_grants SET status='ACTIVE'")
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', dict(app['data'], name='Changed'), app['version'])
        self.assertEqual(self.cards()[0]['state'], 'CHECKPOINT_CONTEXT_CHANGED')
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_checkpoints SET data=?", ('PRIVATE_CORRUPT_SENTINEL',))
            db.execute("UPDATE agent_review_requests SET envelope=?,result=?", ('PRIVATE_ENVELOPE_SENTINEL', 'PRIVATE_RESULT_SENTINEL'))
        card = self.cards()[0]
        self.assertEqual(card['state'], 'SOURCE_UNAVAILABLE')
        for secret in ('PRIVATE_CORRUPT_SENTINEL', 'PRIVATE_ENVELOPE_SENTINEL', 'PRIVATE_RESULT_SENTINEL', self.issued['token']):
            self.assertNotIn(secret, canonical(card))
        with connection(self.store.path) as db:
            db.execute('UPDATE agent_checkpoints SET data=?', ('é' * 33000,))
        self.assertEqual(self.cards()[0]['state'], 'SOURCE_UNAVAILABLE')

    def test_missing_grants_show_one_unattributed_source_health_card(self):
        with connection(self.store.path) as db:
            # Deliberately damage the fixture as a legacy/corrupt source. Normal writes retain FK enforcement.
            db.execute('PRAGMA foreign_keys=OFF')
            request = db.execute('SELECT * FROM agent_review_requests').fetchone()
            db.execute('INSERT INTO agent_review_requests VALUES(?,?,?,?,?,?)',
                       (request['app_id'], 'other-damaged-request', request['grant_id'],
                        'SECRET_ENVELOPE', request['input_hash'], 'SECRET_RESULT'))
            db.execute('DELETE FROM agent_grants')
            db.execute("UPDATE operator_roles SET role='MAKER',version=version+1 WHERE principal=?", (ids.OWNER['principal'],))
        for user in (ids.OWNER, ids.STRANGER):
            cards = self.cards(user)
            self.assertEqual(len(cards), 1)
            card = cards[0]
            self.assertEqual(card['action']['resource_id'], 'review-source')
            self.assertEqual(card['title'], 'Review source unavailable')
            self.assertEqual(card['evidence'], dict(status='SOURCE_UNAVAILABLE', request_id='review-source'))
            self.assertEqual(card['private_principal'], user['principal'])
            for private in ('review-one', 'other-damaged-request', request['grant_id'], request['input_hash'], 'SECRET_'):
                self.assertNotIn(private, canonical(card))
        self.assertEqual(self.cards(None), [])
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED' WHERE principal=?", (ids.STRANGER['principal'],))
        self.assertEqual(self.cards(ids.STRANGER), [])

    def test_sql_limit_and_secret_columns_not_selected(self):
        with connection(self.store.path) as db:
            request = db.execute('SELECT * FROM agent_review_requests').fetchone()
            checkpoint = db.execute('SELECT * FROM agent_checkpoints').fetchone()
            for i in range(105):
                identity = 'a-%03d' % i
                saved = json.loads(checkpoint['data'])
                saved['packet']['id'] = identity
                saved['hash'] = digest(saved['packet'])
                db.execute('INSERT INTO agent_review_requests VALUES(?,?,?,?,?,?)',
                           (request['app_id'], identity, request['grant_id'], 'SECRET_ENVELOPE', request['input_hash'], 'SECRET_RESULT'))
                db.execute('INSERT INTO agent_checkpoints VALUES(?,?,?,?)',
                           (checkpoint['app_id'], identity, canonical(saved), checkpoint['revision']))
        statements = []

        @contextmanager
        def traced(path):
            with connection(path) as db:
                db.set_trace_callback(statements.append)
                yield db

        with patch('mission_control.db.connection', traced):
            cards = self.cards()
        self.assertEqual(len(cards), 100)
        self.assertTrue(all(c['state'] == 'WAITING_REVIEW' for c in cards))
        self.assertNotIn('SECRET_', canonical(cards))
        query = next(s for s in statements if 'FROM agent_review_requests r' in s)
        self.assertIn('LIMIT 100', query)
        self.assertNotIn('envelope', query.lower())
        self.assertNotIn('result', query.lower())
        self.assertNotIn('token_hash', query.lower())


if __name__ == '__main__':
    unittest.main()
