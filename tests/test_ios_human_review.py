"""Native owner and independently verified checker against real SQLite."""
from datetime import datetime, timedelta, timezone
import json
import sqlite3
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_agent_access import NativeAgentAccess
from mission_control.ios_human_review import NativeHumanReview
from tests import test_ios_host as fixture
from tests.test_aso_validation import listing


TOKEN = 'synthetic_token_for_checker_123456789'
OWNER_TOKEN = 'synthetic_token_for_owner_12345678901'
CHECKER = {'principal': 'github:202', 'login': 'synthetic-checker', 'provider': 'GITHUB', 'verified_at': '2026-01-01T00:00:00Z'}
HUMAN_OWNER = dict(CHECKER, principal='github:101', login='synthetic-owner')


class NativeHumanReviewTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def start(self):
        self.runtime.create_workspace(self.session, self.creation())
        self.gateway = NativeHumanReview(self.runtime.service, self.runtime.identities)
        self.reader = patch('mission_control.operator_identity.github_read', side_effect=lambda path, token: HUMAN_OWNER if token == OWNER_TOKEN else CHECKER)
        self.reader.start(); self.addCleanup(self.reader.stop)
        self.call('owner_identity_login', {'token': OWNER_TOKEN})

    def call(self, action, body=None, app='new-app'):
        return json.loads(self.gateway.call(self.session, app, action, json.dumps(body or {}).encode()))

    def sign_in(self):
        return self.call('reviewer_login', {'token': TOKEN})

    def enroll(self):
        self.sign_in()
        return self.call('member_save', {'role': 'CHECKER', 'status': 'ACTIVE', 'version': None})

    def prepare_agent(self):
        grant = dict(agent_id='agent-one', manifest_version=1, operations=['growth.save'],
                     review_operations=['growth.save'], expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_calls=5)
        issued = json.loads(NativeAgentAccess(self.runtime.service, self.runtime.identities).manage(
            self.session, 'new-app', 'issue', json.dumps({'confirm_scope': True, 'grant': grant}).encode()))
        envelope = dict(app_id='new-app', operation='growth.save', input=dict(
            id='example-listing', manifest_version=1, kind='ASO_LISTING', data=dict(release='build-1', listing=listing())))
        adapter = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        waiting = json.loads(adapter.review(self.session, issued['token'], 'prepare',
                                            json.dumps({'id':'review-one','envelope':envelope}).encode()))
        return adapter, issued['token'], envelope, waiting

    def test_reviewer_sees_exact_request_and_approves_real_agent_dispatch(self):
        self.start(); self.enroll()
        adapter, token, envelope, waiting = self.prepare_agent()
        self.assertEqual(self.call('agent_list')['items'][0]['id'], 'review-one')
        detail = self.call('agent_inspect', {'id': 'review-one'})
        self.assertEqual(detail['envelope'], envelope)
        checkpoint = detail['checkpoint']
        with self.assertRaises(Invalid):
            self.call('agent_approve', dict(id='review-one', revision=checkpoint['revision'], packet_hash='0'*64))
        approved = self.call('agent_approve', dict(id='review-one', revision=checkpoint['revision'], packet_hash=checkpoint['hash']))
        self.assertEqual(approved['checker'], CHECKER['principal'])
        done = json.loads(adapter.review(self.session, token, 'resume', json.dumps(dict(
            id='review-one', app_id='new-app', revision=approved['revision'], packet_hash=approved['hash'])).encode()))
        self.assertEqual(done['result']['outcome'], 'SUCCEEDED')
        with self.assertRaises(Invalid):
            self.call('agent_approve', dict(id='review-one', revision=checkpoint['revision'], packet_hash=checkpoint['hash']))
        self.assertNotIn(TOKEN, json.dumps(detail) + json.dumps(approved))
        for file in self.path.parent.glob(self.path.name + '*'):
            for token_value in (TOKEN, OWNER_TOKEN):self.assertNotIn(token_value.encode(), file.read_bytes())

    def test_verified_review_exact_source_and_distinct_human(self):
        self.start(); self.enroll()
        record = self.runtime.service.store.save_record('new-app', dict(kind='store', title='Synthetic', source='Fixture', data={'description':'Review exact copy'}))
        self.runtime.service.store.save_record('new-app', dict(kind='measurement', title='Excluded', source='Fixture', data={}))
        self.assertEqual(self.call('review_sources')['items'], [{'id':record['id'], 'title':'Synthetic', 'kind':'store'}])
        with self.assertRaises(PermissionError):self.call('review_sources', app='other')
        review = self.call('review_prepare', {'record_id': record['id']})
        self.assertEqual(self.call('review_list')['items'][0]['hash'], review['hash'])
        with self.assertRaises(Invalid):self.call('review_approve', {'id': review['id'], 'hash': '0'*64})
        approved = self.call('review_approve', {'id': review['id'], 'hash': review['hash']})
        self.assertEqual(approved['checker'], CHECKER['principal'])
        self.assertEqual(approved['status'], 'VERIFIED_REVIEW_RECORDED')

    def test_scope_revocation_logout_and_native_generation(self):
        self.start(); self.enroll(); self.prepare_agent()
        with self.assertRaises(PermissionError):self.call('agent_list', app='other')
        self.call('member_save', {'role':'CHECKER', 'status':'REVOKED', 'version':1})
        with self.assertRaises(PermissionError):self.call('agent_list')
        self.call('member_save', {'role':'CHECKER', 'status':'ACTIVE', 'version':2})
        self.call('reviewer_logout')
        with self.assertRaises(PermissionError):self.call('agent_list')
        self.sign_in(); self.generation = str(uuid4())
        self.assertEqual(self.call('reviewer_status')['status'], 'SIGNED_OUT')
        with self.assertRaises(PermissionError):self.call('agent_list')
        self.call('owner_identity_login', {'token': OWNER_TOKEN})
        self.sign_in(); self.available = False
        with self.assertRaises(PermissionError):self.call('reviewer_status')
        self.available = True
        self.assertEqual(self.call('reviewer_status')['status'], 'SIGNED_OUT')
        self.call('owner_identity_login', {'token': OWNER_TOKEN})
        self.sign_in(); self.gateway.logout()
        self.assertEqual(self.call('reviewer_status')['status'], 'SIGNED_OUT')

    def test_owner_lock_during_approval_rolls_back_checkpoint(self):
        import mission_control.agent_checkpoints as checkpoints
        self.start(); self.enroll(); self.prepare_agent()
        checkpoint = self.call('agent_inspect', {'id':'review-one'})['checkpoint']
        persist = checkpoints.persist
        def lock_after_persist(*args, **kwargs):
            result = persist(*args, **kwargs); self.available = False
            return result
        with patch.object(checkpoints, 'persist', side_effect=lock_after_persist):
            with self.assertRaises(PermissionError):
                self.call('agent_approve', dict(id='review-one', revision=checkpoint['revision'], packet_hash=checkpoint['hash']))
        self.available = True; self.call('owner_identity_login', {'token': OWNER_TOKEN}); self.sign_in()
        self.assertEqual(self.call('agent_inspect', {'id':'review-one'})['checkpoint']['state'], 'WAITING_REVIEW')

    def test_stale_manifest_or_revoked_provider_cannot_approve(self):
        self.start(); self.enroll(); self.prepare_agent()
        checkpoint = self.call('agent_inspect', {'id':'review-one'})['checkpoint']
        body = dict(id='review-one', revision=checkpoint['revision'], packet_hash=checkpoint['hash'])
        with connection(self.path) as db:
            db.execute("UPDATE apps SET version=version+1 WHERE id='new-app'")
        with self.assertRaises(Invalid):self.call('agent_approve', body)
        with patch('mission_control.operator_identity.github_read', side_effect=Invalid('Identity revoked')):
            with self.assertRaises(Invalid):self.call('agent_approve', body)
        self.assertEqual(self.call('reviewer_status')['status'], 'SIGNED_OUT')

    def test_owner_lock_during_membership_save_rolls_back(self):
        from mission_control.review_access import Access
        self.start(); self.sign_in()
        write = Access.write
        def lock_after_write(instance, *args):
            write(instance, *args); self.available = False
        with patch.object(Access, 'write', lock_after_write):
            with self.assertRaises(PermissionError):
                self.call('member_save', {'role':'CHECKER','status':'ACTIVE','version':None})
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM operator_roles WHERE principal=?", (CHECKER['principal'],)).fetchone()[0], 0)

    def test_owner_can_revoke_saved_checker_after_reviewer_logout(self):
        self.start(); self.enroll(); self.prepare_agent(); self.call('reviewer_logout')
        with self.assertRaises(Invalid):
            self.call('member_revoke', {'principal': CHECKER['principal'], 'version': 2})
        self.call('member_revoke', {'principal': CHECKER['principal'], 'version': 1})
        self.sign_in()
        with self.assertRaises(PermissionError):self.call('agent_list')
        with self.assertRaises(Invalid):
            self.call('member_revoke', {'principal': 'github:999', 'version': 1})

    def test_owner_account_binding_is_persistent_and_checker_must_be_distinct(self):
        self.start()
        with self.assertRaises(PermissionError):self.call('reviewer_login', {'token': OWNER_TOKEN})
        self.assertEqual(self.call('reviewer_status')['status'], 'SIGNED_OUT')
        with self.assertRaises(PermissionError):self.call('owner_identity_login', {'token': TOKEN})
        self.assertEqual(self.call('owner_identity_status')['status'], 'SIGNED_OUT')
        self.call('owner_identity_login', {'token': OWNER_TOKEN}); self.sign_in()
        self.call('owner_identity_logout')
        self.assertEqual(self.call('reviewer_status')['status'], 'SIGNED_OUT')
        with self.assertRaises(PermissionError):self.sign_in()
        reopened = NativeHumanReview(self.runtime.service, self.runtime.identities)
        with self.assertRaises(PermissionError):
            reopened.call(self.session, 'new-app', 'owner_identity_login', json.dumps({'token':TOKEN}).encode())
        with connection(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE native_owner_review_identity SET github_principal='github:202'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("INSERT OR REPLACE INTO native_owner_review_identity VALUES('new-app','native:fake','github:202','fake')")

    def test_revoking_checker_after_approval_blocks_resume(self):
        self.start(); self.enroll()
        adapter, token, _, _ = self.prepare_agent()
        checkpoint = self.call('agent_inspect', {'id':'review-one'})['checkpoint']
        approved = self.call('agent_approve', dict(id='review-one', revision=checkpoint['revision'], packet_hash=checkpoint['hash']))
        self.call('member_revoke', {'principal':CHECKER['principal'], 'version':1})
        with self.assertRaises(PermissionError):
            adapter.review(self.session, token, 'resume', json.dumps(dict(id='review-one', app_id='new-app',
                revision=approved['revision'], packet_hash=approved['hash'])).encode())

    def test_unknown_agent_result_requires_exact_evidence_and_cannot_resume_after_reconciliation(self):
        from mission_control.operation_outcome import EffectUncertain
        self.start(); self.enroll()
        adapter, token, _, _ = self.prepare_agent()
        checkpoint = self.call('agent_inspect', {'id':'review-one'})['checkpoint']
        evidence = 'a' * 64
        with self.assertRaises(Invalid):
            self.call('agent_reconcile', dict(id='review-one', revision=checkpoint['revision'], outcome='FAILED', evidence_hash=evidence))
        approved = self.call('agent_approve', dict(id='review-one', revision=checkpoint['revision'], packet_hash=checkpoint['hash']))
        resume = dict(id='review-one', app_id='new-app', revision=approved['revision'], packet_hash=approved['hash'])
        with patch('mission_control.ios_operation_adapter.guarded_execute', side_effect=EffectUncertain()):
            uncertain = json.loads(adapter.review(self.session, token, 'resume', json.dumps(resume).encode()))
        self.assertEqual(uncertain['checkpoint']['state'], 'UNKNOWN')
        self.assertTrue(uncertain['reconciliation_required'])
        revision = uncertain['checkpoint']['revision']
        for changes in ({'evidence_hash':'a'*63}, {'outcome':'UNKNOWN'}, {'revision':revision-1}):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                self.call('agent_reconcile', dict(dict(id='review-one', revision=revision, outcome='FAILED', evidence_hash=evidence), **changes))
        result = self.call('agent_reconcile', dict(id='review-one', revision=revision, outcome='FAILED', evidence_hash=evidence))
        self.assertEqual(result['state'], 'FAILED')
        self.assertEqual(result['history'][-1]['evidence_hash'], evidence)
        with self.assertRaises(Invalid):
            adapter.review(self.session, token, 'resume', json.dumps(dict(resume, revision=result['revision'])).encode())

    def test_fixed_actions_and_no_caller_supplied_principal(self):
        self.start(); self.sign_in()
        for action, body in [('member_save', {'role':'CHECKER','status':'ACTIVE','version':None,'principal':'native:fake'}),
                             ('reviewer_login', {'token':TOKEN,'principal':'fake'}), ('dispatch', {})]:
            with self.subTest(action=action), self.assertRaises(Invalid):self.call(action, body)
        with self.assertRaises(PermissionError):self.call('agent_list')


if __name__ == '__main__': unittest.main()
