"""Real owner HTTP, CLI and official SDK MCP packaging conformance."""
import json
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.operator_client import ClientError,OperatorClient
from mission_control.packaging_store import Packaging
from mission_control.packaging_access import dispatch,reconcile
from tests import test_agent_grants as grants
from tests import test_video_edit_clients as editing
from tests import test_agent_mcp as sdk
from tests.test_packaging import draft,ref

APP='sample-one'


class PackagingClientTests(unittest.IsolatedAsyncioTestCase):
    setUp=grants.GrantTests.setUp
    tearDown=grants.GrantTests.tearDown
    body=grants.GrantTests.body
    envelope=grants.GrantTests.envelope
    grant=editing.VideoClientsTests.grant
    cli=editing.VideoClientsTests.cli
    session=editing.VideoClientsTests.session

    def variant(self,**changes):
        return dict(dict(id='client-variant',version=0,kind='VARIANT',manifest_version=self.store.app(APP)['version'],data=draft()),**changes)

    def shotlist(self,variant):
        segment=dict(id='opening',text='Show an authentic app step')
        return self.variant(id='client-shots',kind='SHOTS',data=dict(variant=ref('VARIANT',variant),script=[segment],shots=[dict(id='opening-shot',segment_id=segment['id'],segment_sha256=digest(segment),kind='SCREEN_RECORDING',description='Capture the current app step',source=None,start_ms=None,end_ms=None,assets=[],claims=[],claim_text='')]))

    def owner_call(self,action,body):
        return self.owner.request('POST','/api/apps/'+APP+'/packaging/'+action,body)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for packaging transport acceptance')
    async def test_owner_cli_and_mcp_share_variant_shotlist_and_history(self):
        self.grant(['packaging.save','packaging.read','packaging.history','packaging.reconcile'])
        saved=self.cli(self.envelope('packaging.save',self.variant()))
        shots=self.owner_call('save',self.shotlist(saved))
        async with self.session() as client:
            tools=await client.list_tools()
            self.assertTrue({'wmm_packaging_save','wmm_packaging_read','wmm_packaging_history','wmm_packaging_reconcile'}<={t.name for t in tools.tools})
            for item in [saved,shots]:
                body=dict(id=item['id'],kind=item['kind'],version=item['version'])
                expected=self.owner_call('read',body)
                self.assertEqual(self.cli(self.envelope('packaging.read',body)),expected)
                result=await client.call_tool('wmm_packaging_read',dict(app_id=APP,input=body))
                self.assertFalse(result.isError,result.content);self.assertEqual(result.structuredContent['data'],expected)
                self.assertFalse(expected['execution_authority']);self.assertEqual(expected['state'],'DRAFT')
            result=await client.call_tool('wmm_packaging_save',dict(app_id=APP,input=self.variant(version=1,data=dict(draft(),title='Second original candidate'))))
            self.assertFalse(result.isError,result.content);self.assertEqual(result.structuredContent['data']['version'],2)
            page=await client.call_tool('wmm_packaging_history',dict(app_id=APP,input={}))
            self.assertEqual(page.structuredContent['data'],self.owner_call('history',{}))
        self.assertEqual(Packaging(self.store).list(APP)['total'],3)
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        self.assertNotIn(self.token,json.dumps(saved))

    def test_reconcile_observes_without_retry_or_caller_commit_claim(self):
        agent=self.grant(['packaging.save','packaging.reconcile'])
        request=self.variant()
        empty=agent.call(self.envelope('packaging.reconcile',request));self.assertEqual(empty['status'],'NO_REVISION_OBSERVED')
        saved=agent.call(self.envelope('packaging.save',request))
        same=self.owner_call('reconcile',request);self.assertEqual(same['status'],'MATCHING_REVISION_OBSERVED')
        self.assertEqual(same['document']['hash'],saved['hash']);self.assertEqual(same['caller_commit_identity'],'NOT_PROVEN')
        self.assertFalse(same['automatic_retry']);self.assertFalse(same['execution_authority'])
        different=agent.call(self.envelope('packaging.reconcile',self.variant(data=dict(draft(),title='Another input'))))
        self.assertEqual(different['status'],'DIFFERENT_REVISION_OBSERVED')
        app=self.store.app(APP);self.store.save_app(APP,dict(app['data'],name='Changed app'),app['version'])
        stale=self.owner_call('reconcile',request)
        self.assertEqual(stale['status'],'MATCHING_REVISION_OBSERVED');self.assertEqual(stale['document']['source_status'],'STALE')
        self.assertEqual(Packaging(self.store).list(APP)['total'],1)

    def test_wrong_scope_stale_revisions_revoked_grants_and_forged_approval_are_denied(self):
        agent=self.grant(['packaging.history'])
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.save',self.variant()))
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.history',{},app_id='sample-two'))
        for body in [self.variant(manifest_version=999),dict(self.variant(),approved=True)]:
            with self.assertRaises(ClientError):self.owner_call('save',body)
        saved=self.owner_call('save',self.variant())
        with self.assertRaises(ClientError):self.owner_call('save',self.variant())
        with self.assertRaises(ClientError):self.owner_call('read',dict(id=saved['id'],kind='VARIANT',version=True))
        with self.assertRaises(ClientError):self.owner_call('read',dict(id=saved['id'],kind='SHOTS'))
        self.owner.request('POST','/api/apps/'+APP+'/agent-grants/revoke',dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.history'))
        self.assertEqual(Packaging(self.store).list(APP)['total'],1)

    def test_exact_paths_duplicate_json_and_csrf_are_required(self):
        for suffix in ['save/','save?extra=1','save%2f','unknown']:
            with self.subTest(suffix=suffix),self.assertRaises(ClientError):self.owner_call(suffix,self.variant())
        raw=json.dumps(self.variant()).replace('"version": 0','"version": 0,"version": 1')
        for payload,csrf in [(raw,self.owner.csrf),(json.dumps(self.variant()),None)]:
            headers={'Origin':self.origin,'Content-Type':'application/json','Cookie':'; '.join(c.name+'='+c.value for c in self.owner.cookies)}
            if csrf:headers['X-CSRF-Token']=csrf
            request=Request(self.origin+'/api/apps/'+APP+'/packaging/save',data=payload.encode(),method='POST',headers=headers)
            with self.assertRaises(HTTPError):self.owner.opener.open(request)
        self.assertEqual(Packaging(self.store).list(APP)['total'],0)

    def test_owner_revocation_before_business_transaction_prevents_commit(self):
        import threading
        from mission_control.packaging_contract import variant as original
        def revoke(value):
            result=original(value)
            def change():
                with connection(self.store.path) as db:db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",(APP,))
            thread=threading.Thread(target=change);thread.start();thread.join(timeout=5);self.assertFalse(thread.is_alive());return result
        with patch('mission_control.packaging_store.contract.variant',side_effect=revoke),self.assertRaises(ClientError):self.owner_call('save',self.variant())
        self.assertEqual(Packaging(self.store).list(APP)['total'],0)

    def test_owner_selected_review_requires_distinct_checker_and_exact_single_resume(self):
        from mission_control.review_access import Access
        from tests import test_verified_review as identities
        Access(self.store).save(APP,identities.OWNER,identities.CHECKER,dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        checker=OperatorClient(self.origin);checker.bootstrap();checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        body=dict(self.body(['packaging.save','packaging.read'],100),manifest_version=self.store.app(APP)['version'],review_operations=['packaging.save'])
        issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',body);agent=OperatorClient(self.origin,grant_token=issued['token'])
        envelope=self.envelope('packaging.save',self.variant())
        with self.assertRaises(ClientError):agent.call(envelope)
        prepared=agent.review('prepare',dict(id='review-packaging-save',envelope=envelope))
        self.assertEqual(Packaging(self.store).list(APP)['total'],0)
        packet=dict(id=prepared['id'],revision=prepared['checkpoint']['revision'],packet_hash=prepared['checkpoint']['hash'])
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/agent-reviews/approve',packet)
        approved=checker.request('POST','/api/apps/'+APP+'/agent-reviews/approve',packet)
        result=agent.review('resume',dict(app_id=APP,id=prepared['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(result['checkpoint']['state'],'SUCCEEDED');self.assertEqual(result['result']['data']['id'],'client-variant')
        with self.assertRaises(ClientError):agent.review('resume',dict(app_id=APP,id=prepared['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(Packaging(self.store).list(APP)['total'],1)

    def test_catalog_and_automation_expose_preparation_only(self):
        from mission_control.operation_catalog import catalog
        from mission_control.automation_requirements import workflow_catalog
        contract=catalog()['domain_contracts']['content_packaging'];self.assertEqual(set(contract['variant_fields']),set(draft()))
        self.assertFalse(contract['execution_authority']);self.assertEqual(contract['render'],'NOT_RUN')
        self.assertTrue(set(contract['operations'])<=set(workflow_catalog()['workflows']['local_evidence']['operations']))
        self.assertEqual(set(contract['uncertain_write']['statuses']),{'MATCHING_REVISION_OBSERVED','DIFFERENT_REVISION_OBSERVED','NO_REVISION_OBSERVED'})

    def test_closed_access_fields_and_history_paging(self):
        for action,body in [('history',dict(offset=True)),('read',dict(id='missing',kind='VARIANT',approved=True)),('reconcile',dict(self.variant(),version=True)),('unknown',{})]:
            with self.subTest(action=action),self.assertRaises(Invalid):dispatch(self.store,APP,action,body)
        service=Packaging(self.store)
        for i in range(101):service.save(APP,self.variant(id='history-'+str(i)))
        first=self.owner_call('history',{});last=self.owner_call('history',dict(offset=100))
        self.assertEqual((len(first['items']),first['next_offset'],len(last['items']),last['next_offset']),(100,100,1,None))
        self.assertNotIn('Original test title',json.dumps(first));self.assertNotIn('data',first['items'][0])
        self.assertEqual(first['source_status'],'NOT_CHECKED')


    def test_owner_domain_post_fixed_lazy_handlers(self):
        from mission_control.server import owner_domain_post
        from importlib import import_module
        for name,module in [('drive','drive_http'),('media','managed_media_http'),('funnels','funnel_http'),('discovery','discovery_http'),('packaging','packaging_http')]:
            self.assertIs(owner_domain_post(['api','apps',APP,name,'read']),import_module('mission_control.'+module).post)
        for parts in [[],['api'],['api','other',APP,'packaging'],['api','apps',APP,'../drive'],['api','apps',APP,'unregistered']]:
            self.assertIsNone(owner_domain_post(parts))
