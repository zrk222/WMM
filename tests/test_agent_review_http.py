"""Actual HTTP agent/maker/checker sessions; synthetic provider identity is explicit."""
import json
import unittest
from unittest.mock import patch
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.operator_client import OperatorClient,ClientError
from mission_control.review_access import Access
from mission_control.agent_review_protocol import PATHS,validate,tools
from tests import test_agent_review_policy as fixture
from tests import test_verified_review as identities


class ReviewHTTPTests(unittest.TestCase):
    setUp_base=fixture.ReviewPolicyTests.setUp
    tearDown=fixture.ReviewPolicyTests.tearDown
    body=fixture.ReviewPolicyTests.body
    envelope=fixture.ReviewPolicyTests.envelope
    listing_body=fixture.ReviewPolicyTests.listing_body
    issue_reviewed=fixture.ReviewPolicyTests.issue_reviewed

    def setUp(self):
        self.setUp_base()
        Access(self.store).save('sample-one',identities.OWNER,identities.CHECKER,dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        self.checker=OperatorClient(self.origin);self.checker.bootstrap()
        self.checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        self.issued=self.issue_reviewed();self.token=self.issued['token']
        self.agent=OperatorClient(self.origin,grant_token=self.token)
        self.input=self.envelope('growth.save',self.listing_body())

    def prepare(self,identity='review-one'):
        return self.agent.review('prepare',dict(id=identity,envelope=self.input))

    def human(self,action,body=None,client=None,app='sample-one'):
        return (client or self.checker).request('POST','/api/apps/'+app+'/agent-reviews/'+action,body or {})

    def approve(self,view):
        checkpoint=view['checkpoint']
        return self.human('approve',dict(id=view['id'],revision=checkpoint['revision'],packet_hash=checkpoint['hash']))

    def resume(self,approved):
        return self.agent.review('resume',dict(app_id='sample-one',id='review-one',revision=approved['revision'],packet_hash=approved['hash']))

    def test_exact_human_approval_and_agent_resume_use_separate_sessions(self):
        sessions=len(self.server.sessions);view=self.prepare()
        detail=self.human('inspect',dict(id='review-one'))
        self.assertEqual(detail['input_hash'],view['input_hash']);self.assertEqual(detail['envelope'],self.input)
        rows=self.human('list');self.assertEqual(rows['total'],1);self.assertIsNone(rows['next_offset'])
        self.assertNotIn('envelope',rows['items'][0]);self.assertNotIn(self.token,json.dumps(rows))
        approved=self.approve(view);done=self.resume(approved)
        self.assertEqual(done['checkpoint']['state'],'SUCCEEDED')
        self.assertEqual(done['result']['data']['hash'],self.owner.call(self.envelope())['history'][0]['hash'])
        with self.assertRaises(ClientError):self.resume(approved)
        self.assertEqual(self.agent.review('status',dict(app_id='sample-one',id='review-one'))['result'],done['result'])
        self.assertEqual(len(self.server.sessions),sessions)

    def test_unsigned_self_forged_and_bearer_approval_are_denied(self):
        view=self.prepare();row=view['checkpoint'];body=dict(id='review-one',revision=row['revision'],packet_hash=row['hash'])
        anonymous=OperatorClient(self.origin);anonymous.bootstrap()
        for client in (anonymous,self.owner):
            with self.assertRaises(ClientError):self.human('approve',body,client)
        with self.assertRaises(ClientError):self.human('approve',dict(body,principal=identities.CHECKER['principal']))
        with self.assertRaises(Invalid):self.agent.review('approve',body)
        with self.assertRaises(Invalid):self.agent.request('POST','/api/apps/sample-one/agent-reviews/approve',body)
        # This address rejects before body parsing; do not race an unread body
        # against Windows socket closure. Still prove the exact route denial.
        raw=Request(self.origin+'/api/agent-operations/reviews/approve',data=b'',headers={'Origin':self.origin,'Content-Type':'application/json','Authorization':'Bearer '+self.token},method='POST')
        with self.assertRaises(HTTPError) as denied:urlopen(raw,timeout=15)
        self.assertEqual(denied.exception.code,400)
        self.assertEqual(json.load(denied.exception)['error'],'Unknown exact agent review address')
        with self.assertRaises(ClientError):self.resume(row)
        self.assertEqual(self.owner.call(self.envelope())['history'],[])

    def test_stale_hash_changed_role_identity_failure_and_cross_app_deny(self):
        view=self.prepare();row=view['checkpoint']
        with self.assertRaises(ClientError):self.human('approve',dict(id='review-one',revision=row['revision'],packet_hash='0'*64))
        with self.assertRaises(ClientError):self.human('inspect',dict(id='review-one'),app='sample-two')
        with self.assertRaises(ClientError):self.agent.review('status',dict(app_id='sample-two',id='review-one'))
        with patch('mission_control.operator_identity.github_read',side_effect=Invalid('Synthetic identity unavailable')):
            with self.assertRaises(ClientError):self.approve(view)
        self.checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        approved=self.approve(view)
        with connection(self.store.path) as db:db.execute('UPDATE operator_roles SET version=version+1 WHERE principal=?',(identities.CHECKER['principal'],))
        with self.assertRaises(ClientError):self.resume(approved)

    def test_cancel_unknown_receipt_and_authenticated_reconcile(self):
        waiting=self.prepare();row=waiting['checkpoint']
        cancelled=self.human('cancel',dict(id='review-one',revision=row['revision']),self.owner)
        with self.assertRaises(ClientError):self.resume(cancelled)
        self.assertEqual(self.agent.review('status',dict(app_id='sample-one',id='review-one'))['checkpoint']['state'],'CANCELLED')
        self.input['input']['id']='unknown-listing'
        view=self.prepare('review-two');approved=self.approve(view)
        with patch('mission_control.agent_review_dispatch.execute',side_effect=RuntimeError('PRIVATE_SENTINEL')):
            result=self.agent.review('resume',dict(app_id='sample-one',id='review-two',revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(result['checkpoint']['state'],'UNKNOWN');self.assertNotIn('PRIVATE_SENTINEL',str(result))
        body=dict(id='review-two',revision=result['checkpoint']['revision'],outcome='FAILED',evidence_hash=digest('Synthetic reconciliation receipt'))
        with self.assertRaises(ClientError):self.human('reconcile',body,self.owner)
        reconciled=self.human('reconcile',body)
        self.assertEqual(reconciled['state'],'FAILED')

    def test_closed_protocol_invalid_framing_and_missing_grant_fail_before_session(self):
        sessions=len(self.server.sessions)
        bodies=[('prepare',dict(id='request',envelope=self.input,principal='fake')),('status',dict(app_id='../sample',id='request')),('resume',dict(app_id='sample-one',id='request',revision=True,packet_hash='0'*64))]
        for action,body in bodies:
            with self.assertRaises(Invalid):self.agent.review(action,body)
        with self.assertRaises(Invalid):OperatorClient(self.origin).review('status',dict(app_id='sample-one',id='request'))
        for suffix,payload in (('?x=1',b'{}'),('',b'{"id":"a","id":"b"}')):
            request=Request(self.origin+PATHS['prepare']+suffix,data=payload,headers={'Origin':self.origin,'Content-Type':'application/json','Authorization':'Bearer '+self.token},method='POST')
            with self.assertRaises(HTTPError):urlopen(request,timeout=15)
        self.assertEqual(len(self.server.sessions),sessions)
        self.assertEqual({row['name'] for row in tools()},{'wmm_review_prepare','wmm_review_status','wmm_review_resume'})

    def test_human_queue_pagination_has_all_requests_and_bounded_metadata(self):
        self.prepare()
        with connection(self.store.path) as db:
            request=dict(db.execute('SELECT * FROM agent_review_requests').fetchone())
            checkpoint=dict(db.execute('SELECT * FROM agent_checkpoints').fetchone())
            for index in range(101):
                identity='queue-'+str(index).zfill(3)
                data=json.loads(checkpoint['data']);data['packet']['id']=identity
                data['hash']=digest(data['packet'])
                db.execute('INSERT INTO agent_checkpoints VALUES(?,?,?,?)',('sample-one',identity,json.dumps(data),checkpoint['revision']))
                db.execute('INSERT INTO agent_review_requests VALUES(?,?,?,?,?,?)',('sample-one',identity,request['grant_id'],request['envelope'],request['input_hash'],None))
        first=self.human('list');second=self.human('list',dict(offset=first['next_offset']))
        self.assertEqual(first['total'],102);self.assertEqual(len(first['items']),100);self.assertEqual(len(second['items']),2)
        self.assertIsNone(second['next_offset']);self.assertEqual(len({row['id'] for row in first['items']+second['items']}),102)
        for offset in (-1,True,10**100):
            with self.assertRaises(ClientError):self.human('list',dict(offset=offset))

    def test_wrong_tokens_and_replacement_grants_cannot_probe_request_existence(self):
        self.prepare();replacement=self.issue_reviewed()
        for token in ('wmmg_'+'x'*43,replacement['token']):
            client=OperatorClient(self.origin,grant_token=token)
            for identity in ('review-one','missing-request'):
                for action in ('status','resume'):
                    body=dict(app_id='sample-one',id=identity)
                    if action=='resume':body.update(revision=1,packet_hash='0'*64)
                    with self.assertRaises(ClientError) as error:client.review(action,body)
                    self.assertEqual(error.exception.status,403)
        self.assertEqual(self.agent.review('status',dict(app_id='sample-one',id='review-one'))['checkpoint']['state'],'WAITING_REVIEW')
