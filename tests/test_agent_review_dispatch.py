"""Exact local reviewed effects with separate synthetic owner/checker and durable receipts."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import unittest
from unittest.mock import patch
from mission_control.agent_checkpoints import Checkpoints
from mission_control.agent_review_dispatch import ReviewedDispatch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.review_access import Access
from tests import test_agent_review_policy as fixture
from tests import test_verified_review as identities


class ReviewedDispatchTests(unittest.TestCase):
    setUp_base=fixture.ReviewPolicyTests.setUp
    tearDown=fixture.ReviewPolicyTests.tearDown
    body=fixture.ReviewPolicyTests.body
    envelope=fixture.ReviewPolicyTests.envelope
    listing_body=fixture.ReviewPolicyTests.listing_body
    issue_reviewed=fixture.ReviewPolicyTests.issue_reviewed

    def setUp(self):
        self.setUp_base()
        Access(self.store).save('sample-one',identities.OWNER,identities.CHECKER,dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        self.issued=self.issue_reviewed();self.token=self.issued['token']
        self.dispatch=ReviewedDispatch(self.server.service);self.checkpoints=Checkpoints(self.store)
        self.input=self.envelope('growth.save',self.listing_body())

    def prepare(self):return self.dispatch.prepare(self.token,'review-one',self.input)

    def approve(self,prepared):
        row=prepared['checkpoint']
        return self.checkpoints.approve('sample-one','review-one',identities.CHECKER['principal'],row['revision'],row['hash'])

    def resume(self,approved):return self.dispatch.resume(self.token,'sample-one','review-one',approved['revision'],approved['hash'])

    def test_exact_saved_effect_requires_distinct_review_and_executes_once(self):
        waiting=self.prepare();row=waiting['checkpoint']
        with self.assertRaises(Invalid):self.resume(row)
        with self.assertRaises(Invalid):self.checkpoints.approve('sample-one','review-one',identities.OWNER['principal'],row['revision'],row['hash'])
        approved=self.approve(waiting);done=self.resume(approved)
        self.assertEqual(done['checkpoint']['state'],'SUCCEEDED')
        self.assertEqual(done['result']['outcome'],'SUCCEEDED')
        saved=self.owner.call(self.envelope())['history'][0]
        self.assertEqual(saved['hash'],done['result']['data']['hash'])
        with self.assertRaises(Invalid):self.resume(approved)
        self.assertEqual(len(self.owner.call(self.envelope())['history']),1)
        self.assertEqual(ReviewedDispatch(self.server.service).inspect(self.token,'sample-one','review-one')['result'],done['result'])

    def test_frozen_input_and_grant_binding_reject_edits_or_same_agent_replacement(self):
        first=self.prepare()
        replay=self.prepare();self.assertEqual(replay['checkpoint']['hash'],first['checkpoint']['hash'])
        changed=dict(self.input,input=dict(self.input['input'],id='changed-listing'))
        with self.assertRaises(Invalid):self.dispatch.prepare(self.token,'review-one',changed)
        replacement=self.issue_reviewed()
        with self.assertRaises(PermissionError):self.dispatch.inspect(replacement['token'],'sample-one','review-one')
        with self.assertRaises(PermissionError):self.dispatch.inspect(self.token,'sample-two','review-one')
        self.assertEqual(self.dispatch.inspect(self.token,'sample-one','review-one')['envelope'],self.input)

    def test_revoked_grant_stale_checker_and_expiry_deny_before_effect(self):
        waiting=self.prepare();approved=self.approve(waiting)
        future=ReviewedDispatch(self.server.service,clock=lambda:datetime.now(timezone.utc)+timedelta(hours=2))
        with self.assertRaises(PermissionError):future.resume(self.token,'sample-one','review-one',approved['revision'],approved['hash'])
        with connection(self.store.path) as db:db.execute('UPDATE operator_roles SET version=version+1 WHERE principal=?',(identities.CHECKER['principal'],))
        with self.assertRaises(Invalid):self.resume(approved)
        self.grants.revoke('sample-one',identities.OWNER,dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(PermissionError):self.resume(approved)
        self.assertEqual(self.owner.call(self.envelope())['history'],[])

    def test_cancelled_request_never_dispatches_and_snapshot_carries_no_authority(self):
        waiting=self.prepare();row=waiting['checkpoint']
        cancelled=self.checkpoints.cancel('sample-one','review-one',identities.OWNER['principal'],row['revision'])
        with self.assertRaises(Invalid):self.resume(cancelled)
        replay=self.prepare();self.assertEqual(replay['checkpoint']['state'],'CANCELLED')
        snapshot=str(self.store.export('sample-one'))
        self.assertNotIn('review-one',snapshot);self.assertNotIn('agent_review_requests',snapshot)

    def test_racing_resume_claims_exactly_once(self):
        approved=self.approve(self.prepare())
        def attempt(_):
            try:return self.resume(approved)['checkpoint']['state']
            except Invalid:return 'DENIED'
        with ThreadPoolExecutor(max_workers=4) as pool:states=list(pool.map(attempt,range(4)))
        self.assertEqual(states.count('SUCCEEDED'),1);self.assertEqual(states.count('DENIED'),3)
        self.assertEqual(len(self.owner.call(self.envelope())['history']),1)

    def test_unknown_result_and_cancel_during_execution_keep_receipt_no_replay(self):
        approved=self.approve(self.prepare())
        def cancel_then_fail(service,envelope):
            row=self.checkpoints.inspect('sample-one','review-one')
            self.checkpoints.cancel('sample-one','review-one',identities.OWNER['principal'],row['revision'])
            raise RuntimeError('SYNTHETIC_PRIVATE_SENTINEL')
        with patch('mission_control.agent_review_dispatch.execute',side_effect=cancel_then_fail):done=self.resume(approved)
        self.assertEqual(done['checkpoint']['state'],'CANCEL_REQUESTED')
        self.assertEqual(done['result']['outcome'],'UNKNOWN');self.assertTrue(done['reconciliation_required'])
        self.assertNotIn('SYNTHETIC_PRIVATE_SENTINEL',str(done))
        with self.assertRaises(Invalid):self.resume(done['checkpoint'])

    def test_validation_failure_is_terminal_and_does_not_change_domain_history(self):
        self.input['input']['manifest_version']=99
        done=self.resume(self.approve(self.prepare()))
        self.assertEqual(done['checkpoint']['state'],'FAILED')
        self.assertEqual(done['result']['error'],'LOCAL_VALIDATION_REJECTED')
        self.assertEqual(self.owner.call(self.envelope())['history'],[])

    def test_committed_write_with_unserializable_response_stays_unknown(self):
        approved=self.approve(self.prepare())
        from mission_control.operation_runtime import execute
        def write_then_bad_response(service,envelope):
            execute(service,envelope)
            return {'unserializable':object()}
        with patch('mission_control.agent_review_dispatch.execute',side_effect=write_then_bad_response):done=self.resume(approved)
        self.assertEqual(done['checkpoint']['state'],'UNKNOWN')
        self.assertEqual(len(self.owner.call(self.envelope())['history']),1)
        self.assertTrue(done['reconciliation_required'])
        with self.assertRaises(Invalid):self.resume(done['checkpoint'])

    def test_saved_input_tamper_and_changed_app_are_rejected_before_claim(self):
        approved=self.approve(self.prepare())
        with connection(self.store.path) as db:
            original=db.execute('SELECT envelope FROM agent_review_requests').fetchone()[0]
            db.execute('UPDATE agent_review_requests SET envelope=?',(original.replace('grant-listing','edited-listing'),))
        with self.assertRaises(Invalid):self.resume(approved)
        with connection(self.store.path) as db:db.execute('UPDATE agent_review_requests SET envelope=?',(original,))
        self.store.save_app('sample-one',dict(name='Changed',release='build-2',locale='en-US',currency='USD'),1)
        with self.assertRaises(PermissionError):self.resume(approved)
