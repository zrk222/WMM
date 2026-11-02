"""Synthetic Page execution, durable uncertainty and fixed HTTP boundary tests."""
import tempfile
import json
import os
import subprocess
import sys
import time
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from mission_control.campaign_contract import post_data
from mission_control.campaign_execution import CampaignExecutionService
from mission_control.campaign_transport import MetaTransport, Unconfirmed
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.store import Store


class FakeTransport:
    def __init__(self):self.posts=0;self.fail=False;self.before_return=None
    def publish(self,page,message,link,token,secret,alive):
        alive();self.posts+=1
        if self.before_return:self.before_return()
        if self.fail:raise TimeoutError('synthetic credential should never appear')
        return page+'_777'
    def read_post(self,page,identity,content_hash,token,secret,alive):
        alive();return {'id':identity,'permalink_url':'https://www.facebook.com/post'}


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name+'/test.db',seed=False)
        self.store.save_app('sample',{'name':'Example'})
        stamp=now()
        with connection(self.store.path) as db:
            db.execute('INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)',('sample','owner','owner','OWNER','ACTIVE',1,stamp,'owner'))
            db.execute('INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)',('sample','facebook',1,canonical({'provider':'facebook'}),'cfg','CONFIGURED_UNTESTED',stamp,stamp))
            data={'destination':{'id':'123'}}
            db.execute('INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('sample','11111111-1111-4111-8111-111111111111','facebook',1,1,'subject',canonical(data),'grant','CONNECTED_READ_TESTED',None,None,0,None,0,stamp,stamp))
        self.transport=FakeTransport();self.denied=set()
        def policy(app,actor,scope,action):
            if action in self.denied:raise PermissionError('denied')
        self.service=CampaignExecutionService(self.store,policy,self.transport)
        self.message='A synthetic Page update';self.content=digest({'message':self.message,'link':None});self.rights='b'*64
        self.body=dict(connection_id='11111111-1111-4111-8111-111111111111',page_id='123',ad_account_id=None,currency='CAD',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_posts=2,max_calls=50,
            max_campaigns=0,max_campaign_minor=0,max_total_minor=0,approved_content_hashes=[self.content],
            approved_rights_hashes=[self.rights],approved_targeting_hashes=[],billing_acknowledged=False,ordinary_ad_attestation=False)
        self.post=dict(request_id='22222222-2222-4222-8222-222222222222',message=self.message,link=None,content_hash=self.content,rights_hash=self.rights)
        self.preflight=patch.object(self.service,'_preflight',side_effect=lambda a,actor,i,action,active=True:(self.service.get_scope(a,i),'synthetic-secret','synthetic-token'))
        self.preflight.start();self.addCleanup(self.preflight.stop)
        draft=self.service.prepare_scope('sample','owner',self.body)
        self.scope=self.service.activate_scope('sample','owner',draft['scope_id'],draft['approval_hash'])

    def test_publish_is_exact_durable_and_not_replayed(self):
        result=self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        self.assertEqual(result['status'],'VERIFIED');self.assertEqual(result['remote_id'],'123_777')
        self.assertEqual(self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)['id'],result['id'])
        self.assertEqual(self.transport.posts,1)
        self.assertNotIn('synthetic-token',canonical(result));self.assertNotIn('synthetic-secret',canonical(result))
        with self.assertRaises(Invalid):self.service.run_post('sample','grant:example',self.scope['scope_id'],{**self.post,'message':'altered'})

    def test_lost_response_is_unknown_across_restart_and_not_replayed(self):
        self.transport.fail=True
        with self.assertRaises(Unconfirmed):self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        restarted=CampaignExecutionService(self.store,lambda *args:None,self.transport)
        rows=restarted.list_intents('sample',self.scope['scope_id'])
        self.assertEqual(rows[0]['status'],'UNKNOWN');self.assertIsNone(rows[0]['remote_id'])
        self.assertEqual(restarted.reconcile('sample','owner',self.scope['scope_id'],rows[0]['id'])['status'],'UNKNOWN')
        self.assertEqual(self.transport.posts,1)

    def test_revocation_during_dispatch_preserves_remote_id(self):
        self.transport.before_return=lambda:self.service.revoke_scope('sample','owner',self.scope['scope_id'])
        result=self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        self.assertEqual(result['status'],'VERIFYING');self.assertEqual(result['remote_id'],'123_777')
        with self.assertRaises(PermissionError):self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        self.assertEqual(self.transport.posts,1)

    def test_guard_loss_after_response_does_not_discard_remote_id(self):
        from mission_control.operation_authority import PROTECTED
        invalidated={'value':False}
        def check(db,context):
            if invalidated['value']:raise PermissionError('identity revoked')
            return 'grant:example'
        self.transport.before_return=lambda:invalidated.update(value=True)
        token=PROTECTED.set({'store':str(self.store.path.resolve())})
        try:
            with patch('mission_control.operation_authority.check',side_effect=check):
                result=self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        finally:PROTECTED.reset(token)
        self.assertEqual(result['status'],'VERIFYING')
        self.assertEqual(result['remote_id'],'123_777')
        self.assertEqual(self.service.list_intents('sample',self.scope['scope_id'])[0]['remote_id'],'123_777')

    def test_unknown_post_reconcile_requires_scope_policy(self):
        self.transport.fail=True
        with self.assertRaises(Unconfirmed):self.service.run_post('sample','owner',self.scope['scope_id'],self.post)
        intent=self.service.list_intents('sample',self.scope['scope_id'])[0]
        def policy(app,actor,scope,action):
            if actor=='grant:other-owner':raise PermissionError('scope owner mismatch')
        self.service.policy_checker=policy
        with patch.object(self.service,'_preflight',side_effect=AssertionError('provider access')):
            with self.assertRaises(PermissionError):
                self.service.reconcile('sample','grant:other-owner',self.scope['scope_id'],intent['id'])

    def test_history_is_owner_scoped(self):
        self.assertEqual(len(self.service.list_scopes('sample','owner')),1)
        self.assertEqual(self.service.list_scopes('sample','different'),[])

    def test_policy_change_and_scope_content_block_dispatch(self):
        self.denied.add('RUN_POST')
        with self.assertRaises(PermissionError):self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        self.assertEqual(self.transport.posts,0)
        self.denied.clear()
        with self.assertRaises(PermissionError):self.service.run_post('sample','grant:example',self.scope['scope_id'],{**self.post,'rights_hash':'c'*64})
        self.assertEqual(self.transport.posts,0)

    def test_duplicate_concurrency_dispatches_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post),range(2)))
        self.assertEqual(self.transport.posts,1)
        self.assertEqual(results[0]['id'],results[1]['id'])

    def test_fresh_permissions_and_saved_subject_required(self):
        self.preflight.stop()
        from types import SimpleNamespace
        facts=SimpleNamespace(subject_id='subject',permissions=['pages_manage_posts','pages_show_list','pages_read_engagement'],
            destinations=[{'id':'123','tasks':['CREATE_CONTENT']}])
        credentials=({'provider':'facebook'},'synthetic-secret',{'access_token':'user-token','page_token':'page-token'})
        with patch.object(self.service,'_credentials',return_value=credentials), patch('mission_control.campaign_execution.facebook',return_value=facts), patch('mission_control.campaign_execution.selected_page',return_value=({'tasks':['CREATE_CONTENT']},'page-token')):
            self.service._preflight('sample','owner',self.scope['scope_id'],'RUN_POST')
            facts.permissions.remove('pages_manage_posts')
            with self.assertRaises(PermissionError):self.service._preflight('sample','owner',self.scope['scope_id'],'RUN_POST')
            facts.permissions.append('pages_manage_posts');facts.subject_id='different'
            with self.assertRaises(PermissionError):self.service._preflight('sample','owner',self.scope['scope_id'],'RUN_POST')

    def test_changed_connection_version_blocks_dispatch(self):
        with connection(self.store.path) as db:
            db.execute('UPDATE social_connections SET version=version+1 WHERE app_id=?',('sample',))
        with self.assertRaises(PermissionError):self.service.run_post('sample','grant:example',self.scope['scope_id'],self.post)
        self.assertEqual(self.transport.posts,0)

    def test_paid_execution_is_explicitly_blocked(self):
        with patch('mission_control.campaign_execution.PAID_EXECUTION_READY',False),self.assertRaisesRegex(Invalid,'verification is incomplete'):
            self.service.run_ad('sample','grant:example',self.scope['scope_id'],{})
        self.assertEqual(self.transport.posts,0)


class TransportTests(unittest.TestCase):
    def test_paid_lock_rejects_linked_storage_if_supported(self):
        from pathlib import Path
        from types import SimpleNamespace
        from mission_control.campaign_locks import paid_lock
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);target=base/'elsewhere';target.mkdir()
            try:(base/'.campaign-locks').symlink_to(target,target_is_directory=True)
            except OSError:self.skipTest('Directory symlink creation unavailable')
            with self.assertRaises(Invalid):
                with paid_lock(SimpleNamespace(path=base/'state.sqlite'),'sample','intent'):pass

    def test_paid_lock_rejects_linked_file_if_supported(self):
        from pathlib import Path
        from types import SimpleNamespace
        from mission_control.campaign_locks import _lock_file, paid_lock
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder);store=SimpleNamespace(path=base/'state.sqlite')
            _,path=_lock_file(store,'sample','intent');target=base/'target';target.write_bytes(b'0')
            try:path.symlink_to(target)
            except OSError:self.skipTest('File symlink creation unavailable')
            with self.assertRaises(Invalid):
                with paid_lock(store,'sample','intent'):pass

    def test_readback_requires_exact_page_and_content(self):
        transport=MetaTransport();expected=digest({'message':'hello','link':None})
        response={'id':'123_777','message':'hello','from':{'id':'123'},'permalink_url':'https://www.facebook.com/post'}
        with patch.object(transport,'request',return_value=response):
            self.assertEqual(transport.read_post('123','123_777',expected,'token','secret',lambda:None)['id'],'123_777')
            response['message']='different'
            with self.assertRaises(Unconfirmed):transport.read_post('123','123_777',expected,'token','secret',lambda:None)
            response['message']='hello';response['from']={'id':'999'}
            with self.assertRaises(Unconfirmed):transport.read_post('123','123_777',expected,'token','secret',lambda:None)

    def test_paid_transport_fixed_edges_and_paused_creation(self):
        calls=[]
        class Response:status=200
        class Conn:
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):calls.append((args,kwargs))
            def getresponse(self):return Response()
            def close(self):pass
        with patch('mission_control.campaign_transport.PinnedHTTPS',Conn), patch('mission_control.campaign_transport.address',return_value='127.0.0.1'), patch('mission_control.campaign_transport.trust_context',return_value=None), patch('mission_control.campaign_transport.response_headers',return_value={}), patch('mission_control.campaign_transport.response_body',side_effect=[b'{"id":"1001"}',b'{"success":true}']):
            transport=MetaTransport();fields=dict(name='Synthetic',objective='OUTCOME_ENGAGEMENT',status='PAUSED',special_ad_categories=[])
            identity=transport.create_paid('campaign','456',fields,'token-value','secret-value',lambda:None)
            transport.set_paid_status('campaign',identity,'ACTIVE','token-value','secret-value',lambda:None)
        self.assertTrue(calls[0][0][1].endswith('/act_456/campaigns'))
        self.assertIn(b'status=PAUSED',calls[0][1]['body'])
        self.assertTrue(calls[1][0][1].endswith('/1001'))
        self.assertIn(b'status=ACTIVE',calls[1][1]['body'])
        with self.assertRaises(Invalid):MetaTransport().create_paid('campaign','456',{**fields,'status':'ACTIVE'},'token','secret',lambda:None)

    def test_fixed_post_request_and_response(self):
        calls=[]
        class Response:status=200
        class Conn:
            def __init__(self,*args):pass
            def request(self,*args,**kwargs):calls.append((args,kwargs))
            def getresponse(self):return Response()
            def close(self):pass
        with patch('mission_control.campaign_transport.PinnedHTTPS',Conn), patch('mission_control.campaign_transport.address',return_value='127.0.0.1'), patch('mission_control.campaign_transport.trust_context',return_value=None), patch('mission_control.campaign_transport.response_headers',return_value={}), patch('mission_control.campaign_transport.response_body',return_value=b'{"id":"123_777"}'):
            result=MetaTransport().publish('123','hello',None,'token-value','secret-value',lambda:None)
        self.assertEqual(result,'123_777');self.assertEqual(calls[0][0][0],'POST')
        self.assertTrue(calls[0][0][1].endswith('/123/feed'))
        self.assertNotIn('token-value',calls[0][0][1]);self.assertNotIn('secret-value',str(calls[0][1]['body']))


if __name__=='__main__':unittest.main()


class FakePaidTransport(FakeTransport):
    def __init__(self):
        super().__init__();self.objects={};self.counter=1000;self.fail_kind=None
    def ad_account(self,account,token,secret,alive):
        alive();return {'id':'act_'+account,'currency':'CAD','account_status':1}
    def create_paid(self,kind,account,fields,token,secret,alive):
        alive()
        if kind==self.fail_kind:raise TimeoutError('lost provider response')
        self.counter+=1;identity=str(self.counter)
        obj={'id':identity,'account_id':account,**fields}
        if kind=='ad':obj['creative']={'id':fields['creative']['creative_id']}
        self.objects[identity]=obj;return identity
    def read_paid(self,kind,identity,token,secret,alive):
        alive();return self.objects[identity].copy()
    def set_paid_status(self,kind,identity,status,token,secret,alive):
        alive();self.objects[identity]['status']=status;return True
    def ad_insights(self,identity,token,secret,alive):
        alive();return {'reported_spend':'1.23','reporting':'PROVIDER_REPORTED_MAY_LAG'}


class PaidTests(unittest.TestCase):
    def setUp(self):
        CampaignTests.setUp(self);self.transport=FakePaidTransport();self.service.transport=self.transport
        self.service.run_post('sample','owner',self.scope['scope_id'],self.post)
        target={'countries':['CA']};self.adbody=dict(request_id='33333333-3333-4333-8333-333333333333',
          post_id='123_777',content_hash=self.content,rights_hash=self.rights,targeting_hash=digest(target),
          lifetime_budget_minor=80,end_time=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat(),
          targeting=target,name='Synthetic campaign')
        paid={**self.body,'ad_account_id':'456','max_campaigns':2,'max_campaign_minor':100,
              'max_total_minor':100,'approved_targeting_hashes':[digest(target)],'billing_acknowledged':True,'ordinary_ad_attestation':True}
        self.account_patch=patch.object(self.service,'_account_preflight',side_effect=lambda app,actor,scope_id,action,active=True:(self.service.get_scope(app,scope_id),'secret','user-token'))
        self.account_patch.start();self.addCleanup(self.account_patch.stop)
        self.credentials_patch=patch.object(self.service,'_credentials',return_value=({},'secret',{'access_token':'user-token'}))
        self.credentials_patch.start();self.addCleanup(self.credentials_patch.stop)
        self.ready=patch('mission_control.campaign_execution.PAID_EXECUTION_READY',True)
        self.ready.start();self.addCleanup(self.ready.stop)
        draft=self.service.prepare_scope('sample','owner',paid)
        self.paid_scope=self.service.activate_scope('sample','owner',draft['scope_id'],draft['approval_hash'])

    def test_paid_lifecycle_and_pause(self):
        result=self.service.run_ad('sample','grant:example',self.paid_scope['scope_id'],self.adbody)
        self.assertEqual(result['status'],'ACTIVE_campaign');self.assertEqual(result['commitment'],80)
        self.assertEqual(set(result['ids']),{'campaign','adset','creative','ad'})
        self.assertEqual(self.service.run_ad('sample','grant:example',self.paid_scope['scope_id'],self.adbody)['id'],result['id'])
        observed=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(observed['result']['reported_spend'],'1.23')
        stopped=self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(stopped['status'],'PAUSED_campaign');self.assertEqual(stopped['commitment'],80)

    def test_uncertain_creation_keeps_hold_and_rejects_second_campaign(self):
        self.transport.fail_kind='adset'
        with self.assertRaises(Unconfirmed):self.service.run_ad('sample','grant:example',self.paid_scope['scope_id'],self.adbody)
        row=self.service.list_intents('sample',self.paid_scope['scope_id'])[0]
        self.assertEqual(row['status'],'UNKNOWN');self.assertEqual(row['commitment'],80)
        second={**self.adbody,'request_id':'44444444-4444-4444-8444-444444444444'}
        with self.assertRaises(PermissionError):self.service.run_ad('sample','grant:example',self.paid_scope['scope_id'],second)
        self.assertEqual(len(self.transport.objects),1)

    def test_monitoring_flags_remote_budget_drift(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        self.transport.objects[result['ids']['adset']]['lifetime_budget']=999
        observed=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(observed['result']['configuration'],'CHANGED_OR_UNCONFIRMED_PAUSE_RECOMMENDED')
        self.assertEqual(observed['commitment'],80)

    def test_changed_budget_before_final_activation_blocks_campaign(self):
        original=self.transport.set_paid_status
        def change(kind,identity,status,token,secret,alive):
            value=original(kind,identity,status,token,secret,alive)
            if kind=='ad' and status=='ACTIVE':
                for obj in self.transport.objects.values():
                    if 'lifetime_budget' in obj:obj['lifetime_budget']=999
            return value
        self.transport.set_paid_status=change
        with self.assertRaises(Unconfirmed):self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        campaign=next(obj for obj in self.transport.objects.values() if 'objective' in obj)
        self.assertEqual(campaign['status'],'PAUSED')

    def test_uncertain_activation_is_never_replayed(self):
        original=self.transport.set_paid_status
        def change(kind,identity,status,token,secret,alive):
            if kind=='campaign' and status=='ACTIVE':
                alive();raise TimeoutError('synthetic lost activation response')
            return original(kind,identity,status,token,secret,alive)
        self.transport.set_paid_status=change
        with self.assertRaises(Unconfirmed):self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        saved=self.service.list_intents('sample',self.paid_scope['scope_id'])[0]
        self.assertEqual(saved['status'],'UNKNOWN');self.assertEqual(saved['commitment'],80)
        replay=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        self.assertEqual(replay['id'],saved['id']);self.assertEqual(replay['status'],'UNKNOWN')
        self.assertEqual(len(self.transport.objects),4)

    def test_currency_mismatch_blocks_account_preflight(self):
        self.account_patch.stop()
        with patch.object(self.service,'_credentials',return_value=({},'secret',{'access_token':'user-token'})):
            with patch.object(self.transport,'ad_account',return_value={'currency':'USD'}):
                with self.assertRaises(PermissionError):self.service._account_preflight('sample','owner',self.paid_scope['scope_id'],'RUN_AD')
        self.assertEqual(len(self.transport.objects),0)

    def test_revoke_pauses_saved_campaign_and_retains_commitment(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        revoked=self.service.revoke_scope('sample','owner',self.paid_scope['scope_id'])
        self.assertEqual(revoked['status'],'REVOKED')
        self.assertEqual(revoked['pause_results'][0]['status'],'PAUSED_campaign')
        self.assertEqual(self.transport.objects[result['ids']['campaign']]['status'],'PAUSED')
        self.assertEqual(self.service.list_intents('sample',self.paid_scope['scope_id'])[0]['commitment'],80)

    def test_stop_during_provider_call_blocks_following_steps(self):
        original=self.transport.create_paid
        def create(kind,account,fields,token,secret,alive):
            if kind=='campaign':
                with self.assertRaises(Invalid):
                    identity=self.service.list_intents('sample',self.paid_scope['scope_id'])[0]['id']
                    self.service.run_pause('sample','owner',self.paid_scope['scope_id'],identity)
            return original(kind,account,fields,token,secret,alive)
        self.transport.create_paid=create
        with self.assertRaises(PermissionError):
            self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        self.assertEqual(len(self.transport.objects),1)
        self.assertEqual(next(iter(self.transport.objects.values()))['status'],'PAUSED')

    def test_incorrect_targeting_blocks_activation(self):
        original=self.transport.read_paid
        def read(kind,identity,token,secret,alive):
            value=original(kind,identity,token,secret,alive)
            if kind=='adset':value['targeting']={'geo_locations':{'countries':['US']}}
            return value
        self.transport.read_paid=read
        with self.assertRaises(Unconfirmed):self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        self.assertTrue(all(obj.get('status','PAUSED')=='PAUSED' for obj in self.transport.objects.values()))

    def test_protective_pause_does_not_require_billing_or_currency_readiness(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with patch.object(self.service,'_account_preflight',side_effect=AssertionError('billing preflight')), \
             patch.object(self.transport,'ad_account',side_effect=AssertionError('billing read')):
            paused=self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(paused['status'],'PAUSED_campaign');self.assertEqual(paused['commitment'],80)

    def test_current_owner_can_recover_and_pause_after_app_change_agent_cannot(self):
        from mission_control.campaign_locks import paid_lock
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with connection(self.store.path) as db:db.execute("UPDATE campaign_paid_intents SET status='ACTIVE_ad' WHERE id=?",(result['id'],))
        with paid_lock(self.store,'sample',result['id']):
            self.service._mark_paid('sample','owner',self.paid_scope['scope_id'],result['id'],'ACTIVE_campaign','dead-owner')
        app=self.store.app('sample');self.store.save_app('sample',dict(app['data'],name='Changed name'),app['version'])
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id='sample' AND principal='owner'")
        with self.assertRaises(PermissionError):self.service.reconcile('sample','grant:example',self.paid_scope['scope_id'],result['id'])
        recovered=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(recovered['status'],'UNKNOWN')
        with self.assertRaises(PermissionError):self.service.run_pause('sample','grant:example',self.paid_scope['scope_id'],result['id'])
        paused=self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(paused['status'],'PAUSED_campaign')
        with self.assertRaises(PermissionError):self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)

    def test_owner_revocation_pauses_after_app_manifest_changes(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        app=self.store.app('sample');self.store.save_app('sample',dict(app['data'],name='Changed name'),app['version'])
        revoked=self.service.revoke_scope('sample','owner',self.paid_scope['scope_id'])
        self.assertEqual(revoked['status'],'REVOKED')
        self.assertEqual(revoked['pause_results'][0]['status'],'PAUSED_campaign')
        self.assertEqual(self.transport.objects[result['ids']['campaign']]['status'],'PAUSED')

    def test_protective_pause_rejects_a_different_returned_campaign(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        original=self.transport.read_paid
        def wrong(kind,identity,token,secret,alive):
            value=original(kind,identity,token,secret,alive);value['id']='9999';return value
        self.transport.read_paid=wrong
        with self.assertRaises(Unconfirmed):self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(self.transport.objects[result['ids']['campaign']]['status'],'ACTIVE')

    def test_protective_pause_rejects_wrong_account_and_changed_destination(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        campaign=self.transport.objects[result['ids']['campaign']];campaign['account_id']='999'
        with self.assertRaises(Unconfirmed):self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(campaign['status'],'ACTIVE');campaign['account_id']='456'
        with connection(self.store.path) as db:
            row=db.execute('SELECT data FROM social_connections WHERE app_id=?',('sample',)).fetchone()
            data=json.loads(row['data']);data['destination']['id']='999'
            db.execute('UPDATE social_connections SET data=? WHERE app_id=?',(canonical(data),'sample'))
        with self.assertRaises(PermissionError):self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(campaign['status'],'ACTIVE')

    def test_dead_process_pending_activation_recovers_then_pauses_without_replay(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='ACTIVE_ad' WHERE id=?",(result['id'],))
        ready=os.path.join(self.tmp.name,'owned-lock-ready')
        code=("import os,sys; from pathlib import Path; "
              "from mission_control.store import Store; "
              "from mission_control.campaign_execution import CampaignExecutionService; "
              "from mission_control.campaign_locks import paid_lock; "
              "store=Store(sys.argv[1],seed=False); service=CampaignExecutionService(store,lambda *a:None); "
              "lock=paid_lock(store,'sample',sys.argv[3]); lock.__enter__(); "
              "service._mark_paid('sample','owner',sys.argv[2],sys.argv[3],'ACTIVE_campaign','fixture-owner'); "
              "Path(sys.argv[4]).write_text('ready'); sys.stdin.read(1); os._exit(23)")
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        child=subprocess.Popen([sys.executable,'-c',code,str(self.store.path),self.paid_scope['scope_id'],result['id'],ready],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=flags)
        try:
            deadline=time.monotonic()+10
            while not os.path.exists(ready) and child.poll() is None and time.monotonic()<deadline:time.sleep(0.05)
            self.assertTrue(os.path.exists(ready),'child did not acquire lock')
            live=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
            self.assertEqual(live['recovery'],'IN_FLIGHT');self.assertEqual(live['status'],'PENDING_ACTIVE_campaign')
            child.stdin.write(b'x');child.stdin.flush();self.assertEqual(child.wait(timeout=10),23)
            restarted=CampaignExecutionService(self.store,lambda *args:None,self.transport)
            with patch.object(restarted,'_credentials',return_value=({},'secret',{'access_token':'token'})):
                recovered=restarted.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
                self.assertEqual(recovered['status'],'UNKNOWN');self.assertEqual(recovered['result']['recovery'],'ABANDONED_UNKNOWN')
                self.assertEqual(recovered['result']['objects']['campaign']['status'],'ACTIVE')
                self.assertEqual(recovered['commitment'],80)
                paused=restarted.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
            self.assertEqual(paused['status'],'PAUSED_campaign');self.assertEqual(paused['commitment'],80)
            self.assertEqual(len(self.transport.objects),4)
        finally:
            if child.poll() is None:child.kill();child.wait(timeout=10)
            for pipe in (child.stdin,child.stdout,child.stderr):
                if pipe:pipe.close()

    def test_missing_created_id_stays_unknown_and_is_not_replayed(self):
        original=self.service._receipt_paid
        def crash(app,identity,step,owner_token,status,*args,**kwargs):
            if step=='CREATE_campaign':raise SystemExit('synthetic crash before ID receipt')
            return original(app,identity,step,owner_token,status,*args,**kwargs)
        with patch.object(self.service,'_receipt_paid',side_effect=crash):
            with self.assertRaises(SystemExit):self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        intent=self.service.list_intents('sample',self.paid_scope['scope_id'])[0]
        self.assertEqual(intent['status'],'PENDING_CREATE_campaign');self.assertEqual(intent['ids'],{})
        observed=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],intent['id'])
        self.assertEqual(observed['status'],'UNKNOWN');self.assertEqual(observed['ids'],{})
        self.assertEqual(observed['commitment'],80)
        self.assertEqual(self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)['status'],'UNKNOWN')
        with self.assertRaises(Invalid):self.service.run_pause('sample','owner',self.paid_scope['scope_id'],intent['id'])
        self.assertEqual(len(self.transport.objects),1)

    def test_pending_without_owner_lease_is_not_stolen(self):
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='PENDING_ACTIVE_campaign' WHERE id=?",(result['id'],))
        observed=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(observed['status'],'PENDING_ACTIVE_campaign');self.assertEqual(observed['recovery'],'OWNER_UNVERIFIED')
        with self.assertRaises(Invalid):self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(observed['commitment'],80)

    def test_exhausted_ordinary_calls_do_not_block_bounded_protective_pause(self):
        from mission_control.campaign_execution import SAFETY_CALL_LIMIT
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with connection(self.store.path) as db:
            db.execute('UPDATE campaign_scopes SET calls=? WHERE app_id=? AND id=?',(self.paid_scope['max_calls'],'sample',self.paid_scope['scope_id']))
        with self.assertRaises(PermissionError):self.service._alive('sample','owner',self.paid_scope['scope_id'],'RUN_AD')
        self.account_patch.stop()
        with patch.object(self.service,'_credentials',return_value=({},'secret',{'access_token':'user-token'})):
            paused=self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(paused['status'],'PAUSED_campaign');self.assertEqual(paused['commitment'],80)
        with connection(self.store.path) as db:
            safety=db.execute("SELECT used FROM campaign_safety_calls WHERE app_id=? AND scope_id=? AND category='PAUSE'",('sample',self.paid_scope['scope_id'])).fetchone()['used']
            ordinary=db.execute('SELECT calls FROM campaign_scopes WHERE id=?',(self.paid_scope['scope_id'],)).fetchone()['calls']
        self.assertEqual(safety,3);self.assertEqual(ordinary,self.paid_scope['max_calls'])
        shown=self.service.get_scope('sample',self.paid_scope['scope_id'])['safety_allowance']
        self.assertEqual(shown['PAUSE'],{'used':3,'limit':SAFETY_CALL_LIMIT})
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_safety_calls SET used=? WHERE app_id=? AND scope_id=? AND category='PAUSE'",(SAFETY_CALL_LIMIT,'sample',self.paid_scope['scope_id']))
        with patch.object(self.service,'_credentials',return_value=({},'secret',{'access_token':'user-token'})):
            with self.assertRaises(PermissionError):self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])

    def test_exhausted_routine_reconciliation_preserves_emergency_recovery(self):
        from mission_control.campaign_execution import SAFETY_CALL_LIMIT
        from mission_control.campaign_locks import paid_lock
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_paid_intents SET status='ACTIVE_ad' WHERE id=?",(result['id'],))
            db.execute('INSERT INTO campaign_safety_calls VALUES(?,?,?,?)',('sample',self.paid_scope['scope_id'],'RECONCILE',SAFETY_CALL_LIMIT))
        with paid_lock(self.store,'sample',result['id']):
            self.service._mark_paid('sample','owner',self.paid_scope['scope_id'],result['id'],'ACTIVE_campaign','lost-owner')
        with self.assertRaises(PermissionError):self.service._alive('sample','owner',self.paid_scope['scope_id'],'RECONCILE',False)
        recovered=self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(recovered['status'],'UNKNOWN');self.assertEqual(recovered['commitment'],80)
        with connection(self.store.path) as db:
            used=db.execute("SELECT used FROM campaign_safety_calls WHERE app_id=? AND scope_id=? AND category='RECOVERY'",('sample',self.paid_scope['scope_id'])).fetchone()['used']
        self.assertGreater(used,0);self.assertLessEqual(used,SAFETY_CALL_LIMIT)
        paused=self.service.run_pause('sample','owner',self.paid_scope['scope_id'],result['id'])
        self.assertEqual(paused['status'],'PAUSED_campaign')

    def test_unknown_paid_reconcile_checks_current_scope_policy(self):
        self.transport.fail_kind='adset'
        with self.assertRaises(Unconfirmed):self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        saved=self.service.list_intents('sample',self.paid_scope['scope_id'])[0]
        def policy(app,actor,scope,action):
            if actor=='grant:other-owner':raise PermissionError('scope owner mismatch')
        self.service.policy_checker=policy
        with patch.object(self.service,'_account_preflight',side_effect=AssertionError('provider access')):
            with self.assertRaises(PermissionError):
                self.service.reconcile('sample','grant:other-owner',self.paid_scope['scope_id'],saved['id'])

    def test_recovery_cas_refuses_changed_owner_token(self):
        from mission_control.campaign_locks import paid_lock
        result=self.service.run_ad('sample','owner',self.paid_scope['scope_id'],self.adbody)
        with connection(self.store.path) as db:db.execute("UPDATE campaign_paid_intents SET status='ACTIVE_ad' WHERE id=?",(result['id'],))
        with paid_lock(self.store,'sample',result['id']):
            self.service._mark_paid('sample','owner',self.paid_scope['scope_id'],result['id'],'ACTIVE_campaign','owner-one')
        original=self.transport.read_paid;changed={'value':False}
        def race(kind,identity,token,secret,alive):
            found=original(kind,identity,token,secret,alive)
            if not changed['value']:
                with connection(self.store.path) as db:
                    db.execute('UPDATE campaign_paid_leases SET owner_token=? WHERE app_id=? AND intent_id=?',('owner-two','sample',result['id']))
                changed['value']=True
            return found
        self.transport.read_paid=race
        with self.assertRaises(Invalid):self.service.reconcile('sample','owner',self.paid_scope['scope_id'],result['id'])
        current=self.service.list_intents('sample',self.paid_scope['scope_id'])[0]
        self.assertEqual(current['status'],'PENDING_ACTIVE_campaign');self.assertEqual(current['commitment'],80)

    def test_paid_budget_atomic_across_concurrent_admissions(self):
        first=self.adbody;second={**first,'request_id':'55555555-5555-4555-8555-555555555555'}
        def admit(body):
            try:return self.service._reserve_ad('sample','grant:example',self.paid_scope['scope_id'],body)[0]['commitment']
            except PermissionError:return 'denied'
        with ThreadPoolExecutor(max_workers=2) as pool:values=list(pool.map(admit,[first,second]))
        self.assertCountEqual(values,[80,'denied'])
