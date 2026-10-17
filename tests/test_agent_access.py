"""Isolated access profiles, secret lifecycle, modes and bounded provider responses."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid,canonical
from mission_control.agent_contract import profile,prompt,draft,model_id,profile_endpoint,charge_consent,profile_identity,profile_secret,bounded_text
from mission_control.agent_registry import REGISTRY
from mission_control.agent_access import AgentAccess,target
from mission_control.agent_registry import catalog
from mission_control.agent_api import message,request
from mission_control.store import Store
from tests.test_measurement_connectors import FakeVault


def body(provider='compatible_api'):
    return dict(provider=provider,label='Synthetic connection',model='synthetic-model',
        endpoint='https://synthetic.example/v1' if provider=='compatible_api' else '',
        api_key='synthetic-key-0123456789' if provider.endswith('_api') or provider=='glm_coding' else '',
        allow_api_charges=provider.endswith('_api'),id=None,version=None)


def answer():return dict(summary='Synthetic draft',items=[dict(title='Try a bounded test',detail='Hypothesis only',source_ids=['app_manifest'])],unknowns=['No measured outcomes'])


def connection_test_fixture():return dict(summary='Connection test completed',items=[],unknowns=['Quota and price are not independently verified'])


class ContractTests(unittest.TestCase):
    def test_model_id_rejects_option_fragments(self):
        self.assertEqual(model_id('model/version'),'model/version')
        with self.assertRaises(Invalid):model_id('--command')

    def test_profile_endpoint_and_charge_consent_require_official_paid_route(self):
        value=body('openai_api')
        self.assertEqual(profile_endpoint(value,REGISTRY['openai_api']),'https://api.openai.com/v1')
        with self.assertRaises(Invalid):charge_consent({**value,'allow_api_charges':False},REGISTRY['openai_api'])

    def test_profile_identity_and_profile_secret_reject_misbound_access(self):
        with self.assertRaises(Invalid):profile_identity({**body(),'id':'not-an-id','version':1})
        with self.assertRaises(Invalid):profile_secret('codex','secret-not-allowed')

    def test_bounded_text_and_draft_item_reject_overflow(self):
        self.assertEqual(bounded_text('ok','test',2),'ok')
        with self.assertRaises(Invalid):bounded_text('bad','test',2)
        with self.assertRaises(Invalid):draft(dict(summary='x',items=[dict(title='x',detail='x',source_ids=['stage_1']*18)],unknowns=[]))

    def test_profile_modes_charge_consent_and_endpoint_authority(self):
        self.assertEqual(profile(body())['endpoint'],'https://synthetic.example/v1')
        self.assertEqual(profile(body('codex'))['provider'],'codex')
        for change in ({'endpoint':'http://synthetic.example'},{'endpoint':'https://user:secret@synthetic.example'},
                       {'endpoint':'https://synthetic.example/?token=private'},{'allow_api_charges':False},
                       {'model':'--dangerously-run'},{'api_key':'space key'},{'command':'evil'}):
            with self.subTest(change=change),self.assertRaises(Invalid):profile({**body(),**change})
        with self.assertRaises(Invalid):profile({**body('codex'),'endpoint':'https://other.example'})
        with self.assertRaises(Invalid):profile({**body('openai_api'),'endpoint':'https://other.example'})
        with self.assertRaises(Invalid):profile({**body('codex'),'api_key':'synthetic-key-123456'})

    def test_prompt_has_only_reviewed_facts_and_no_private_history(self):
        app=dict(data=dict(name='Synthetic',job='Synthetic job',conversation='PRIVATE HISTORY',api_key='PRIVATE KEY'))
        text=prompt(app,'campaign_plan')
        self.assertIn('Synthetic job',text);self.assertNotIn('PRIVATE',text)
        self.assertIn('hypotheses',text);self.assertIn('Use no tools',text)
        with self.assertRaises(Invalid):prompt(app,'arbitrary-command')
        with self.assertRaises(Invalid):prompt(app,'campaign_plan','x'*1001)

    def test_draft_shape_source_scope_and_size(self):
        self.assertEqual(draft(answer()),answer())
        for change in ({'summary':'x'*1201},{'items':[dict(title='x',detail='x',source_ids=['other-app'])]},
                       {'unknowns':['x']*9},{'command':'publish'},{'items':'bad'}):
            with self.subTest(change=change),self.assertRaises(Invalid):draft({**answer(),**change})

    def test_complete_plain_provider_responses_only(self):
        text=canonical(answer());reply=dict(choices=[dict(finish_reason='stop',message={'content':text})])
        self.assertEqual(message(reply,False),text)
        reply['choices'][0]['finish_reason']='length'
        with self.assertRaises(Invalid):message(reply,False)
        self.assertEqual(message({'stop_reason':'end_turn','content':[{'type':'text','text':text}]},True),text)
        for reply in ({'stop_reason':'max_tokens','content':[]},{'stop_reason':'end_turn','content':[{'type':'tool_use'}]},{}):
            with self.assertRaises(Invalid):message(reply,True)

    def test_private_dns_stops_before_authorized_socket(self):
        from mission_control.aeo_transport import ReadError
        p=profile(body())
        with patch('mission_control.agent_api.address',side_effect=ReadError('ADDRESS_BLOCKED')):
            with patch('mission_control.agent_api.PinnedHTTPS') as wire:
                with self.assertRaises(Invalid):request(p,'synthetic-secret',prompt({'data':{}},'campaign_plan'))
                wire.assert_not_called()


class AccessTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'test.sqlite3');self.flow=AgentAccess(self.store)
        FakeVault.values={};FakeVault.fail_delete=0;self.vault=patch('mission_control.agent_access.Vault',FakeVault);self.vault.start();self.addCleanup(self.vault.stop)

    def save(self):return self.flow.save('sample-one',body())['connection']

    def test_protected_key_view_reopen_and_portable_exclusion(self):
        identity=self.save();row=self.flow.get('sample-one',identity)
        self.assertEqual(self.flow.secret('sample-one',row),body()['api_key'])
        public=self.flow.view('sample-one');self.assertNotIn(body()['api_key'],canonical(public))
        self.assertNotIn('credential_ref',canonical(public));self.assertFalse(public['app_billing'])
        self.assertEqual(AgentAccess(Store(self.store.path)).view('sample-one'),public)
        snapshot=self.store.export('sample-one')
        self.assertNotIn('agent_connections',canonical(snapshot));self.assertNotIn(body()['api_key'],canonical(snapshot))
        self.assertNotIn('AgentGrowth/',canonical(snapshot))

    def test_scope_version_rotation_disconnect_and_no_cross_app_keys(self):
        identity=self.save();old=self.flow.get('sample-one',identity);old_target=target(self.store,'sample-one',old['data']['credential_ref'])
        with self.assertRaises(Invalid):self.flow.get('sample-two',identity)
        with self.assertRaises(Invalid):self.flow.save('sample-one',{**body(),'id':identity,'version':0})
        self.flow.save('sample-one',{**body(),'id':identity,'version':1,'api_key':'rotated-synthetic-key-123456'})
        self.assertNotIn(old_target,FakeVault.values)
        current=self.flow.get('sample-one',identity)
        self.assertEqual(current['version'],2)
        self.flow.disconnect('sample-one',identity,{'version':2})
        self.assertEqual(self.flow.get('sample-one',identity)['status'],'DISCONNECTED')
        self.assertFalse(FakeVault.values)

    def test_failed_commit_removes_only_new_stage(self):
        identity=self.save();prior=dict(FakeVault.values)
        with patch.object(self.flow,'commit',side_effect=Invalid('Synthetic optimistic conflict')):
            with self.assertRaises(Invalid):self.flow.save('sample-one',{**body(),'id':identity,'version':1})
        self.assertEqual(FakeVault.values,prior)

    def test_rotation_cleanup_failure_survives_restart_and_preserves_active_key(self):
        identity=self.save();FakeVault.fail_delete=1
        result=self.flow.save('sample-one',{**body(),'id':identity,'version':1,'api_key':'rotated-synthetic-key-123456'})
        self.assertEqual(result['cleanup'],'LOCAL_KEY_CLEANUP_REQUIRED')
        reopened=AgentAccess(Store(self.store.path));self.assertEqual(reopened.view('sample-one')['cleanup_pending'],1)
        self.assertEqual(reopened.secret('sample-one',reopened.get('sample-one',identity)),'rotated-synthetic-key-123456')
        self.assertEqual(reopened.cleanup('sample-one')['remaining'],0);self.assertEqual(len(FakeVault.values),1)
        self.assertEqual(reopened.cleanup('sample-two')['remaining'],0);self.assertEqual(len(FakeVault.values),1)

    def test_disconnected_cleanup_and_interrupted_staging_are_recoverable(self):
        from mission_control.db import connection
        identity=self.save();FakeVault.fail_delete=1
        self.flow.disconnect('sample-one',identity,{'version':1})
        self.assertEqual(self.flow.get('sample-one',identity)['status'],'DISCONNECTED')
        self.assertEqual(self.flow.view('sample-one')['cleanup_pending'],1)
        self.flow.cleanup('sample-one');self.assertFalse(FakeVault.values)
        reference=self.flow.stage('sample-one','nonworking-synthetic-staged-key')
        self.assertEqual(self.flow.cleanup('sample-one')['remaining'],1)
        with connection(self.store.path) as db:db.execute('UPDATE agent_retirements SET eligible=0 WHERE app_id=? AND reference=?',('sample-one',reference))
        reopened=AgentAccess(Store(self.store.path));self.assertEqual(reopened.cleanup('sample-one')['remaining'],0)
        self.assertFalse(FakeVault.values)
        with self.assertRaisesRegex(Invalid,'stage expired'):
            self.flow.commit('sample-one','synthetic-profile',{'credential_ref':reference},None)

    def test_cleanup_refuses_an_active_key_even_with_a_queued_reference(self):
        from mission_control.db import connection
        from mission_control.agent_access import queue_retirement
        identity=self.save();row=self.flow.get('sample-one',identity)
        with connection(self.store.path) as db:queue_retirement(db,'sample-one',row['data']['credential_ref'])
        with self.assertRaisesRegex(Invalid,'active provider key'):self.flow.cleanup('sample-one')
        self.assertEqual(self.flow.secret('sample-one',row),body()['api_key'])

    def test_route_modes_own_connections_and_optimistic_version(self):
        identity=self.save();request=dict(version=0,mode='mixed',routes={'campaign_plan':identity})
        self.assertEqual(self.flow.routes('sample-one',request)['version'],1)
        with self.assertRaises(Invalid):self.flow.routes('sample-one',request)
        with self.assertRaises(Invalid):self.flow.routes('sample-two',request)
        with self.assertRaises(Invalid):self.flow.routes('sample-one',dict(version=1,mode='subscription',routes={'campaign_plan':identity}))
        with self.assertRaises(Invalid):self.flow.routes('sample-one',dict(version=1,mode='mixed',routes={'shell':identity}))


if __name__=='__main__':unittest.main()
