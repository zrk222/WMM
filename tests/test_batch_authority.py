"""Retained creative authority is exact, finite and rechecked after admission."""
from datetime import datetime,timedelta,timezone
import unittest
import json
from mission_control.agent_grants import Grants,batch_authority_pending,capture_batch_authority,check_batch_authority
from mission_control.common import digest,canonical,now,uid
from mission_control.db import connection
from mission_control.operation_authority import bound_agent,protected
from mission_control.review_access import Access
from mission_control.agent_checkpoints import Checkpoints
from mission_control.agent_review_dispatch import ReviewedDispatch
from mission_control.worker import claim,enqueue_db
from tests import test_agent_grants as fixture
from tests import test_verified_review as identities


class BatchAuthorityTests(unittest.TestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown
    body=fixture.GrantTests.body
    issue=fixture.GrantTests.issue
    envelope=fixture.GrantTests.envelope

    def test_exact_plan_binding_and_grant_revocation(self):
        issued=self.issue(['creative.batch.create'])
        expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()
        plan={'expires':expires,'synthetic':'fixed'};plan_hash=digest(plan)
        request=self.envelope('creative.batch.create',dict(plan=canonical(plan),plan_hash=plan_hash,request_key='same-key'))
        admission=Grants(self.store).admit(issued['token'],request)
        with bound_agent(self.store,request,admission),protected(self.store,request):
            with connection(self.store.path) as db:
                with self.assertRaises(PermissionError):capture_batch_authority(db,self.store,'sample-one','creative.batch.create','f'*64,expires)
                reference=capture_batch_authority(db,self.store,'sample-one','creative.batch.create',plan_hash,expires)
        self.assertNotIn(issued['token'],str(reference))
        with connection(self.store.path) as db:check_batch_authority(db,self.store,'sample-one',reference,plan_hash)
        expired=dict(reference,expires=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
        with connection(self.store.path) as db:
            with self.assertRaises(PermissionError):check_batch_authority(db,self.store,'sample-one',expired,plan_hash)
        self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',dict(id=issued['grant']['id'],version=1))
        with connection(self.store.path) as db:
            with self.assertRaises(PermissionError):check_batch_authority(db,self.store,'sample-one',reference,plan_hash)

    def test_completed_review_is_retained_and_cancelled_review_denied(self):
        Access(self.store).save('sample-one',identities.OWNER,identities.CHECKER,
            dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        issued=self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',
            dict(self.body(['creative.batch.create']),review_operations=['creative.batch.create']))
        expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()
        plan={'expires':expires,'synthetic':'fixed'};plan_hash=digest(plan)
        envelope=self.envelope('creative.batch.create',dict(plan=canonical(plan),plan_hash=plan_hash,request_key='key'))
        saved=[]
        def execute(service,request):
            with protected(service.store,request):
                with connection(service.store.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    saved.append(capture_batch_authority(db,service.store,'sample-one','creative.batch.create',plan_hash,expires))
                    self.assertTrue(batch_authority_pending(db,saved[0]))
                    expired=dict(saved[0],expires=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())
                    self.assertFalse(batch_authority_pending(db,expired))
                    self.assertFalse(batch_authority_pending(db,dict(saved[0],expires='invalid')))
                    db.execute("UPDATE agent_grants SET status='REVOKED' WHERE id=?",(saved[0]['grant_id'],))
                    self.assertFalse(batch_authority_pending(db,saved[0]))
                    db.execute("UPDATE agent_grants SET status='ACTIVE' WHERE id=?",(saved[0]['grant_id'],))
                    child=enqueue_db(db,service.store,'sample-one','render',{'synthetic':True},'review-child-key')
                    batch_id=uid();enclosed=dict(plan=plan,authority=saved[0],binding_hash=digest([plan_hash,saved[0]]))
                    db.execute('INSERT INTO creative_batches VALUES(?,?,?,?,?,?,?,?,?,?)',
                        ('sample-one',batch_id,'review-batch-key','request-hash',canonical(enclosed),plan_hash,'ACTIVE',1,now(),now()))
                    db.execute('INSERT INTO creative_batch_variants(app_id,batch_id,ordinal,request_key,request,request_hash,job_id,inspection,inspection_hash) VALUES(?,?,?,?,?,?,?,?,?)',
                        ('sample-one',batch_id,0,'review-child-key','{}','child-hash',child['id'],None,None))
            self.assertIsNone(claim(service.store))
            return {'status':'captured'}
        dispatch=ReviewedDispatch(self.server.service,executor=execute);checkpoints=Checkpoints(self.store)
        waiting=dispatch.prepare(issued['token'],'batch-review',envelope)['checkpoint']
        approved=checkpoints.approve('sample-one','batch-review',identities.CHECKER['principal'],waiting['revision'],waiting['hash'])
        done=dispatch.resume(issued['token'],'sample-one','batch-review',approved['revision'],approved['hash'])
        self.assertEqual(done['checkpoint']['state'],'SUCCEEDED')
        self.assertEqual(claim(self.store)['request_key'],'review-child-key')
        with connection(self.store.path) as db:
            self.assertFalse(batch_authority_pending(db,saved[0]))
            check_batch_authority(db,self.store,'sample-one',saved[0],plan_hash)
        with connection(self.store.path) as db:
            stored=db.execute('SELECT data FROM agent_checkpoints WHERE app_id=? AND id=?',('sample-one','batch-review')).fetchone()
            row=json.loads(stored['data']);row['state']='CANCEL_REQUESTED'
            db.execute('UPDATE agent_checkpoints SET data=? WHERE app_id=? AND id=?',(json.dumps(row),'sample-one','batch-review'))
        with connection(self.store.path) as db:
            with self.assertRaises(PermissionError):check_batch_authority(db,self.store,'sample-one',saved[0],plan_hash)

    def test_noncanonical_wire_plan_cannot_capture_authority(self):
        issued=self.issue(['creative.batch.create'])
        expires=(datetime.now(timezone.utc)+timedelta(minutes=20)).isoformat()
        plan={'expires':expires,'value':0.0};plan_hash=digest(plan)
        request=self.envelope('creative.batch.create',dict(plan=json.dumps(plan),plan_hash=plan_hash,request_key='key'))
        admission=Grants(self.store).admit(issued['token'],request)
        with bound_agent(self.store,request,admission),protected(self.store,request):
            with connection(self.store.path) as db:
                with self.assertRaises(PermissionError):capture_batch_authority(db,self.store,'sample-one','creative.batch.create',plan_hash,expires)


if __name__=='__main__':unittest.main()
