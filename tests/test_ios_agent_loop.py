"""Real SQLite native proposal turns with synthetic provider and scoped tools."""
from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_agent_access import NativeAgentAccess
from mission_control.ios_agent_loop import NativeAgentLoop, parse_turn
from tests import test_ios_inference as inference_fixture


class NativeAgentLoopTests(unittest.TestCase):
    setUp=inference_fixture.NativeInferenceTests.setUp
    verify=inference_fixture.NativeInferenceTests.verify
    creation=inference_fixture.NativeInferenceTests.creation
    vault=inference_fixture.NativeInferenceTests.vault
    setup_access=inference_fixture.NativeInferenceTests.setup_access
    setup_inference=inference_fixture.NativeInferenceTests.setup_inference
    transport=inference_fixture.NativeInferenceTests.transport

    def setup_loop(self,model=None):
        self.setup_inference()
        # Fixture marks the already configured synthetic profile as tested.
        with connection(self.path) as db:
            db.execute("UPDATE agent_connections SET status='TESTED' WHERE id=?",(self.profile_id,))
        self.inference.call(self.session,'new-app','mode',json.dumps({'version':0,'confirm_api_mode':True}).encode())
        access=NativeAgentAccess(self.runtime.service,self.runtime.identities)
        grant=dict(agent_id='native-agent',manifest_version=1,operations=['growth.history','workspace.read'],
                   expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=10)
        issued=json.loads(access.manage(self.session,'new-app','issue',json.dumps({'confirm_scope':True,'grant':grant}).encode()))
        self.grant=issued['grant'];self.token=issued['token'];self.model_calls=0
        self.loop=NativeAgentLoop(self.runtime.service,self.runtime.identities,self.vault,model or self.model)

    def model(self,profile,key,prompt,max_tokens,alive):
        self.model_calls+=1;self.assertEqual(key,'synthetic-key-0123456789');self.assertEqual(max_tokens,1024);alive()
        if self.model_calls==1:return {'kind':'tool','envelope':{'app_id':'new-app','operation':'growth.history','input':{}}}, {'prompt_tokens':12,'completion_tokens':8,'total_tokens':20}
        return {'kind':'final','summary':'Synthetic summary','unknowns':['No production outcome verified']}, None

    def call(self,action,body=None,app='new-app'):
        return json.loads(self.loop.call(self.session,app,action,json.dumps(body or {}).encode()))

    def request(self,previous=None,feedback=None):
        return dict(task='campaign_plan',focus='Synthetic task',connection_id=self.profile_id,grant_id=self.grant['id'],
                    operations=['growth.history'],previous_turn_id=previous,feedback=feedback)

    def approve(self,request,key=None):
        prepared=self.call('prepare',request)
        body=dict(request=request,source_hash=prepared['source_hash'],request_key=key or str(uuid4()),confirm_transmission=True)
        return prepared,self.call('start',body),body

    def test_one_tool_then_explicit_reviewed_feedback_then_final(self):
        self.setup_loop();request=self.request();preview,ready,start=self.approve(request)
        self.assertEqual(ready['status'],'READY');self.assertEqual(self.model_calls,0)
        first=self.call('run',{'id':ready['id']});self.assertEqual(first['status'],'SUCCEEDED')
        self.assertEqual(first['result']['turn']['kind'],'tool');self.assertEqual(first['result']['usage']['total_tokens'],20)
        self.assertEqual(first['result']['tool_execution'],'NOT_PERFORMED')
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT used FROM agent_grants WHERE id=?',(self.grant['id'],)).fetchone()[0],0)
        envelope=first['result']['turn']['envelope']
        reservation=self.call('reserve_tool',{'id':ready['id']})
        self.assertEqual(reservation['envelope'],envelope)
        tool=json.loads(NativeAgentAccess(self.runtime.service,self.runtime.identities).call(self.session,self.token,json.dumps(reservation['envelope']).encode()))
        next_request=self.request(ready['id'],{'summary':'Tool returned app-scoped growth history','count':len(tool['history'])})
        next_preview,queued,_=self.approve(next_request)
        self.assertEqual(next_preview['feedback_provenance'],'UNVERIFIED_CALLER_SUPPLIED')
        self.assertIn('Tool returned app-scoped growth history',next_preview['proposal']['prompt'])
        final=self.call('run',{'id':queued['id']})
        self.assertEqual(final['result']['turn']['kind'],'final');self.assertEqual(final['result']['usage_status'],'UNAVAILABLE')
        self.assertEqual(self.call('run',{'id':ready['id']})['result'],first['result']);self.assertEqual(self.model_calls,2)
        self.assertEqual(self.call('start',start)['id'],ready['id'])
        self.assertNotIn(self.token,json.dumps(first)+json.dumps(final))
        self.assertNotIn('synthetic-key-0123456789',json.dumps(first)+json.dumps(final))
        for file in self.path.parent.glob(self.path.name+'*'):
            for secret in (self.token,'synthetic-key-0123456789'):self.assertNotIn(secret.encode(),file.read_bytes())

    def test_foreign_extra_ungranted_and_unsupported_proposals_fail_closed(self):
        self.setup_loop()
        for value in ({'kind':'tool','envelope':{'app_id':'new-app','operation':'shell','input':{}}},
                      {'kind':'tool','envelope':{'app_id':'new-app','operation':'growth.history','input':{}},'role':'OWNER'},
                      {'kind':'final','summary':'x','unknowns':[],'commands':[]}, {'kind':'tool','envelope':[]},
                      {'kind':'final','summary':'C:\\Users\\someone\\private','unknowns':[]}):
            with self.subTest(value=value),self.assertRaises(Invalid):parse_turn(value)
        for envelope in (dict(app_id='other',operation='growth.history',input={}),
                         dict(app_id='new-app',operation='workspace.read',input={})):
            self.loop.transport=lambda *args:({'kind':'tool','envelope':envelope},None)
            _,job,_=self.approve(self.request());result=self.call('run',{'id':job['id']})
            self.assertEqual(result['status'],'UNKNOWN');self.assertEqual(result['result']['tool_execution'],'NOT_PERFORMED')

    def test_recovery_is_unknown_without_replaying_and_cancel_is_terminal(self):
        def fail(*args):self.model_calls+=1;raise RuntimeError('private provider detail')
        self.setup_loop(fail);_,job,_=self.approve(self.request())
        result=self.call('run',{'id':job['id']});self.assertEqual(result['status'],'UNKNOWN')
        self.assertNotIn('private provider detail',json.dumps(result))
        self.call('run',{'id':job['id']});self.assertEqual(self.model_calls,1)
        _,other,_=self.approve(self.request())
        with connection(self.path) as db:db.execute("UPDATE jobs SET status='IOS_TURN_RUNNING',attempts=1,lease=0 WHERE id=?",(other['id'],))
        self.assertEqual(self.call('run',{'id':other['id']})['status'],'UNKNOWN');self.assertEqual(self.model_calls,1)
        _,cancelled,_=self.approve(self.request())
        self.assertEqual(self.call('cancel',{'id':cancelled['id']})['status'],'CANCELLED')
        self.assertEqual(self.call('run',{'id':cancelled['id']})['status'],'CANCELLED');self.assertEqual(self.model_calls,1)

    def test_stale_grant_owner_and_source_do_not_transmit(self):
        self.setup_loop();preview,job,_=self.approve(self.request())
        NativeAgentAccess(self.runtime.service,self.runtime.identities).manage(self.session,'new-app','revoke',json.dumps(
            {'id':self.grant['id'],'version':1,'confirm_revoke':True}).encode())
        with self.assertRaises(PermissionError):self.call('run',{'id':job['id']})
        self.assertEqual(self.model_calls,0)
        with self.assertRaises(PermissionError):self.call('prepare',self.request())
        self.principal=str(uuid4())
        with self.assertRaises(PermissionError):self.call('read',{'id':job['id']})

    def test_lock_after_request_does_not_commit_and_no_replay(self):
        def lock(profile,key,prompt,maximum,alive):
            self.model_calls+=1;self.available=False
            return {'kind':'final','summary':'unconfirmed','unknowns':[]},None
        self.setup_loop(lock);_,job,_=self.approve(self.request())
        with self.assertRaises(PermissionError):self.call('run',{'id':job['id']})
        self.available=True
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'IOS_TURN_RUNNING')
            db.execute('UPDATE jobs SET lease=0 WHERE id=?',(job['id'],))
        self.assertEqual(self.call('run',{'id':job['id']})['status'],'UNKNOWN');self.assertEqual(self.model_calls,1)

    def test_approved_feedback_only_and_continuation_cannot_fork(self):
        self.setup_loop();_,job,_=self.approve(self.request());self.call('run',{'id':job['id']})
        with self.assertRaises(Invalid):self.call('prepare',self.request(job['id'],{'summary':'not reserved'}))
        self.call('reserve_tool',{'id':job['id']})
        with self.assertRaises(Invalid):self.call('prepare',self.request(job['id'],{'api_key':'private'}))
        with self.assertRaises(Invalid):self.call('prepare',self.request(job['id'],{'summary':'C:\\Users\\someone\\private'}))
        request=self.request(job['id'],{'summary':'confirmed by owner'})
        _,next_job,_=self.approve(request)
        with self.assertRaises(Invalid):self.approve(request)
        self.assertEqual(self.model_calls,1);self.assertEqual(next_job['status'],'READY')

    def test_tool_reservation_survives_restart_and_cannot_be_repeated(self):
        self.setup_loop();_,job,_=self.approve(self.request());self.call('run',{'id':job['id']})
        self.assertEqual(self.call('read',{'id':job['id']})['tool_dispatch'],'NOT_RESERVED')
        reserved=self.call('reserve_tool',{'id':job['id']})
        self.assertEqual(reserved['tool_dispatch'],'RESERVED_RECONCILE_REQUIRED')
        self.loop=NativeAgentLoop(self.runtime.service,self.runtime.identities,self.vault,self.model)
        self.assertEqual(self.call('read',{'id':job['id']})['tool_dispatch'],'RESERVED_RECONCILE_REQUIRED')
        self.assertEqual(self.call('history')['items'][0]['tool_dispatch'],'RESERVED_RECONCILE_REQUIRED')
        with self.assertRaises(Invalid):self.call('reserve_tool',{'id':job['id']})
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='native.agent_turn.tool_reserved'").fetchone()[0],1)

    def test_concurrent_tool_reservation_has_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        self.setup_loop();_,job,_=self.approve(self.request());self.call('run',{'id':job['id']})
        def reserve(_):
            try:return self.call('reserve_tool',{'id':job['id']})['tool_dispatch']
            except Invalid:return 'DENIED'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(reserve,range(2)))
        self.assertEqual(sorted(results),['DENIED','RESERVED_RECONCILE_REQUIRED'])

    def test_turn_limit_and_global_worker_cannot_claim_native_jobs(self):
        from mission_control.worker import claim
        self.setup_loop(lambda *args:({'kind':'tool','envelope':{'app_id':'new-app','operation':'growth.history','input':{}}},None))
        request=self.request()
        for index in range(3):
            _,job,_=self.approve(request)
            self.assertIsNone(claim(self.runtime.service.store))
            self.call('run',{'id':job['id']});self.call('reserve_tool',{'id':job['id']})
            request=self.request(job['id'],{'summary':'Review this data'})
        with self.assertRaises(Invalid):self.call('prepare',request)

    def test_changed_source_after_approval_blocks_provider(self):
        self.setup_loop();_,job,_=self.approve(self.request())
        with connection(self.path) as db:db.execute("UPDATE apps SET version=version+1 WHERE id='new-app'")
        with self.assertRaises(PermissionError):self.call('run',{'id':job['id']})
        self.assertEqual(self.model_calls,0)

    def test_pinned_https_proposal_parser_retains_draft_transport_contract(self):
        from mission_control.agent_api import request,request_turn
        from tests.test_agent_access import body,answer
        profile=body();key=profile['api_key']
        proposal={'kind':'tool','envelope':{'app_id':'new-app','operation':'growth.history','input':{}}}
        def response(value):
            return json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value)}}],
                               'usage':{'total_tokens':7}}).encode()
        with patch('mission_control.agent_api.address',return_value='203.0.113.10'), \
             patch('mission_control.agent_api.trust_context'), patch('mission_control.agent_api.PinnedHTTPS') as wire, \
             patch('mission_control.agent_api.response_headers',return_value={}), \
             patch('mission_control.agent_api.response_body',side_effect=[response(proposal),response(answer())]):
            wire.return_value.getresponse.return_value.status=200
            output,usage=request_turn(profile,key,'Approved prompt')
            self.assertEqual(output,proposal);self.assertEqual(usage['total_tokens'],7)
            self.assertEqual(request(profile,key,'Approved draft')[0],answer())
            self.assertEqual(wire.return_value.request.call_count,2)

    def test_reserved_review_required_tool_uses_existing_separate_checker(self):
        from mission_control.agent_checkpoints import Checkpoints
        from mission_control.review_access import Access
        from tests.test_aso_validation import listing
        self.setup_loop()
        access=NativeAgentAccess(self.runtime.service,self.runtime.identities)
        grant=dict(agent_id='reviewed-agent',manifest_version=1,operations=['growth.save'],review_operations=['growth.save'],
                   expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=3)
        issued=json.loads(access.manage(self.session,'new-app','issue',json.dumps({'confirm_scope':True,'grant':grant}).encode()))
        self.grant=issued['grant'];self.token=issued['token']
        envelope=dict(app_id='new-app',operation='growth.save',input=dict(id='test-listing',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing())))
        self.loop.transport=lambda *args:({'kind':'tool','envelope':envelope},None)
        request=self.request();request['operations']=['growth.save']
        _,job,_=self.approve(request);self.call('run',{'id':job['id']})
        envelope=self.call('reserve_tool',{'id':job['id']})['envelope']
        with self.assertRaises(PermissionError):access.call(self.session,self.token,json.dumps(envelope).encode())
        owner=self.runtime.identities.fresh(self.session);checker={'principal':'github:202','login':'checker'}
        Access(self.runtime.service.store).save('new-app',owner,checker,dict(login='checker',role='CHECKER',status='ACTIVE',version=None))
        waiting=json.loads(access.review(self.session,self.token,'prepare',json.dumps({'id':'review-one','envelope':envelope}).encode()))
        row=waiting['checkpoint'];approved=Checkpoints(self.runtime.service.store).approve('new-app','review-one',checker['principal'],row['revision'],row['hash'])
        done=json.loads(access.review(self.session,self.token,'resume',json.dumps(dict(id='review-one',app_id='new-app',revision=approved['revision'],packet_hash=approved['hash'])).encode()))
        self.assertEqual(done['result']['outcome'],'SUCCEEDED')
        with self.assertRaises(Invalid):self.call('reserve_tool',{'id':job['id']})


if __name__=='__main__':unittest.main()
