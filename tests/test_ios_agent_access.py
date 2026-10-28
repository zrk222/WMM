"""Real native callback and SQLite grant boundaries; no device/inference claim."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4
from tests import test_ios_host as fixture
from mission_control.common import Invalid
from mission_control.db import connection


class NativeAgentAccessTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def manage(self, action, body=None, app='new-app'):
        return json.loads(self.runtime.native_agent_access(self.session, app, action, json.dumps(body or {}).encode()))

    def issue(self, operations=None, review=None, **changes):
        self.runtime.create_workspace(self.session, self.creation())
        grant = dict(agent_id='native-agent', manifest_version=1, operations=operations or ['workspace.read'],
                     expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), max_calls=10)
        if review is not None:grant['review_operations'] = review
        grant.update(changes)
        return self.manage('issue', dict(confirm_scope=True, grant=grant))

    def call(self, token, operation='workspace.read', app='new-app', data=None):
        envelope = dict(app_id=app, operation=operation, input=data or {})
        return json.loads(self.runtime.native_agent_call(self.session, token, json.dumps(envelope).encode()))

    def test_real_owner_issue_scoped_call_list_and_revocation(self):
        issued = self.issue(max_calls=2)
        self.assertEqual(issued['token_delivery'], 'ONCE_ONLY')
        self.assertEqual(self.call(issued['token'])['app']['id'], 'new-app')
        listing = self.manage('list')
        self.assertEqual(listing['grants'][0]['used'], 1)
        self.assertEqual(listing['native_execution_acceptance'], 'INCOMPLETE')
        self.assertNotIn(issued['token'], json.dumps(listing))
        self.assertNotIn('token_hash', json.dumps(listing))
        self.manage('revoke', dict(id=issued['grant']['id'], version=1, confirm_revoke=True))
        with self.assertRaises(PermissionError):self.call(issued['token'])

    def test_owner_confirmation_and_exact_body_cannot_be_supplied_by_agent(self):
        self.runtime.create_workspace(self.session, self.creation())
        for action, body in [('issue', {'confirm_scope':False,'grant':{}}),
                             ('issue', {'confirm_scope':True,'grant':{},'role':'OWNER'}),
                             ('revoke', {'id':'x','version':1}), ('list', {'principal':'owner'}),
                             ('shell', {})]:
            with self.subTest(action=action), self.assertRaises(Invalid):self.manage(action, body)
        issued = self.issue()
        with self.assertRaises(Invalid):self.call(issued['token'], 'native.agent-access.issue')
        self.assertEqual(self.manage('list')['grants'][0]['used'], 0)

    def test_native_lock_foreign_principal_scope_and_exhaustion_deny(self):
        issued = self.issue(max_calls=1)
        with self.assertRaises(PermissionError):self.call(issued['token'], app='other')
        with self.assertRaises(PermissionError):self.call(issued['token'], operation='growth.history')
        original = self.principal; self.principal = str(uuid4())
        with self.assertRaises(PermissionError):self.call(issued['token'])
        self.principal = original; self.available = False
        with self.assertRaises(PermissionError):self.call(issued['token'])
        self.available = True
        self.call(issued['token'])
        with self.assertRaises(PermissionError):self.call(issued['token'])

    def test_grant_issue_rolls_back_if_native_lock_occurs_before_commit(self):
        import mission_control.agent_grants as grants
        self.runtime.create_workspace(self.session, self.creation())
        original = grants.audit
        def lock_after_audit(db, app, event, data):
            original(db, app, event, data)
            if event == 'agent_grant.issued':self.available = False
        with patch.object(grants, 'audit', lock_after_audit):
            with self.assertRaises(PermissionError):self.issue()
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agent_grants').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='agent_grant.issued'").fetchone()[0], 0)

    def test_scoped_mutation_rolls_back_after_native_session_replacement(self):
        from mission_control.growth_review_store import GrowthReviews
        from tests.test_aso_validation import listing
        issued = self.issue(operations=['growth.save'])
        original = GrowthReviews.commit
        def replace_after_insert(reviews, *args):
            result = original(reviews, *args)
            self.generation = str(uuid4())
            return result
        data = dict(id='native-listing', manifest_version=1, kind='ASO_LISTING',
                    data=dict(release='build-1', listing=listing()))
        with patch.object(GrowthReviews, 'commit', replace_after_insert):
            with self.assertRaises(PermissionError):self.call(issued['token'], 'growth.save', data=data)
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_review_entries').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT used FROM agent_grants').fetchone()[0], 1)

    def test_required_review_cannot_be_bypassed_by_native_scoped_call(self):
        issued = self.issue(operations=['growth.save'], review=['growth.save'])
        with self.assertRaises(PermissionError):
            self.call(issued['token'], 'growth.save', data=dict(id='x',manifest_version=1,kind='ASO_LISTING',data={}))
        self.assertEqual(self.manage('list')['grants'][0]['used'], 0)


if __name__ == '__main__':unittest.main()
