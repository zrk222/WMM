"""Actual owner HTTP, scoped CLI and official MCP share exact research documents."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.common import Invalid,canonical,digest
from mission_control.operator_client import ClientError
from mission_control.discovery_store import Discovery
from mission_control.discovery_access import read,history
from mission_control.creative_library import Library
from mission_control.db import connection
from tests import test_agent_grants as grants
from tests import test_video_edit_clients as editing
from tests import test_agent_mcp as sdk
from tests.test_discovery_intelligence import filters,reviewed
from tests.test_creative_library import reference
from tests.test_viral_policy import candidate,AS_OF

APP='sample-one'


class DiscoveryClientTests(unittest.IsolatedAsyncioTestCase):
    body=grants.GrantTests.body
    envelope=grants.GrantTests.envelope
    grant=editing.VideoClientsTests.grant
    cli=editing.VideoClientsTests.cli
    session=editing.VideoClientsTests.session
    tearDown=grants.GrantTests.tearDown

    def setUp(self):
        grants.GrantTests.setUp(self);self.version=self.store.app(APP)['version'];v=candidate()
        data=reference(platform=v['platform'],post_id=v['post_id'],creator_id=v['creator_id'],format=v['format'],url=v['url'],metric_kind='VIEWS',metric_value=v['views'],metric_at=AS_OF,captured_at=AS_OF,published_at=v['published_at'])
        saved=Library(self.store).save(APP,dict(data=data));self.source=next(r['current'] for r in Library(self.store).list(APP) if r['id']==saved['id'])

    def review_body(self):
        return dict(id='client-review',version=0,manifest_version=self.version,reference_id=self.source['reference_id'],source_hash=self.source['hash'],data=reviewed())

    def collection_body(self):
        return dict(id='client-collection',version=0,manifest_version=self.version,query=filters(freshness_seconds=31536000),attempted_sources=1,failed_sources=0)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for research transport acceptance')
    async def test_owner_cli_and_mcp_read_the_same_immutable_research(self):
        self.grant(['discovery.review','discovery.collect','discovery.read','discovery.history'])
        saved=self.cli(self.envelope('discovery.review',self.review_body()));self.assertEqual(saved['data']['source_hash'],self.source['hash'])
        collection=self.owner.request('POST','/api/apps/'+APP+'/discovery/collect',self.collection_body())
        body=dict(id=collection['id'],kind='COLLECTION')
        expected=self.owner.request('POST','/api/apps/'+APP+'/discovery/read',body)
        self.assertEqual(self.cli(self.envelope('discovery.read',body)),expected)
        async with self.session() as client:
            result=await client.call_tool('wmm_discovery_read',dict(app_id=APP,input=body));self.assertFalse(result.isError,result.content);self.assertEqual(result.structuredContent['data'],expected)
            page=await client.call_tool('wmm_discovery_history',dict(app_id=APP,input=dict(kind='REVIEW')));self.assertFalse(page.isError,page.content)
            self.assertEqual(page.structuredContent['data'],self.owner.request('POST','/api/apps/'+APP+'/discovery/history',dict(kind='REVIEW')))
        self.assertEqual(expected['data']['boundaries']['production_execution'],'NOT_RUN');self.assertIsNone(expected['data']['boundaries']['measured_app_sales'])
        self.assertNotIn(self.token,json.dumps(expected))

    def test_paged_history_summaries_do_not_leak_private_prose(self):
        d=dict(manifest_version=self.version,app_hash=digest(self.store.app(APP)['data']),private_note='PRIVATE_RESEARCH_SENTINEL')
        with connection(self.store.path) as db:
            db.executemany('INSERT INTO discovery_documents VALUES(?,?,?,?,?,?,?)',[(APP,'history-'+str(i),1,'WATCH',canonical(d),digest(d),AS_OF) for i in range(101)])
        first=history(self.store,APP,dict(kind='WATCH'));last=history(self.store,APP,dict(kind='WATCH',offset=100))
        self.assertEqual((len(first['items']),first['next_offset'],len(last['items']),last['next_offset']),(100,100,1,None))
        self.assertNotIn('PRIVATE_RESEARCH_SENTINEL',json.dumps(first));self.assertNotIn('data',first['items'][0])
        for bad in (True,-1,2001,'100'):
            with self.assertRaises(Invalid):history(self.store,APP,dict(kind='WATCH',offset=bad))

    def test_historical_status_and_currentness_are_separate(self):
        service=Discovery(self.store);review=service.save_review(APP,self.review_body());collection=service.collect(APP,self.collection_body())
        value=read(self.store,APP,dict(id=collection['id'],kind='COLLECTION'))
        self.assertTrue(value['currentness']['all_checked_sources_current'])
        current=dict(self.source['data'],title='Changed synthetic source')
        Library(self.store).save(APP,dict(id=self.source['reference_id'],version=1,data=current))
        value=read(self.store,APP,dict(id=collection['id'],kind='COLLECTION',version=1))
        self.assertFalse(value['currentness']['all_checked_sources_current']);self.assertEqual(value['data'],collection['data'])
        app=self.store.app(APP);self.store.save_app(APP,dict(app['data'],name='Changed context'),app['version'])
        self.assertFalse(read(self.store,APP,dict(id=review['id'],kind='REVIEW'))['currentness']['current_app_context'])

    def test_grant_scope_revocation_foreign_and_stale_context_are_denied(self):
        agent=self.grant(['discovery.history'])
        with self.assertRaises(ClientError):agent.call(self.envelope('discovery.review',self.review_body()))
        with self.assertRaises(ClientError):agent.call(self.envelope('discovery.history',dict(kind='REVIEW'),app_id='sample-two'))
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/discovery/review',dict(self.review_body(),manifest_version=self.version+1))
        with self.assertRaises((Invalid,ValueError,ClientError)):agent.call(self.envelope('discovery.history',dict(kind='REVIEW',approved=True)))
        self.owner.request('POST','/api/apps/'+APP+'/agent-grants/revoke',dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(ClientError):agent.call(self.envelope('discovery.history',dict(kind='REVIEW')))
        self.assertEqual(history(self.store,APP,dict(kind='REVIEW'))['total'],0)

    def test_exact_path_json_duplicates_and_csrf_are_required(self):
        for path in ('/discovery/review/','/discovery/review?extra=1','/discovery/review%2f','/discovery/unknown'):
            with self.subTest(path=path),self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+path,self.review_body())
        raw=json.dumps(self.review_body()).replace('"manifest_version": '+str(self.version),'"manifest_version": '+str(self.version)+',"manifest_version": '+str(self.version))
        for payload,csrf in [(raw,self.owner.csrf),(json.dumps(self.review_body()),None)]:
            headers={'Origin':self.origin,'Content-Type':'application/json','Cookie':'; '.join(c.name+'='+c.value for c in self.owner.cookies)}
            if csrf:headers['X-CSRF-Token']=csrf
            req=Request(self.origin+'/api/apps/'+APP+'/discovery/review',data=payload.encode(),method='POST',headers=headers)
            with self.assertRaises(HTTPError):self.owner.opener.open(req)
        self.assertEqual(history(self.store,APP,dict(kind='REVIEW'))['total'],0)

    def test_machine_readable_contract_and_automation_preserve_all_boundaries(self):
        from mission_control.operation_catalog import catalog
        from mission_control.automation_requirements import workflow_catalog
        c=catalog()['domain_contracts']['discovery_research'];value=reviewed()
        self.assertEqual(set(c['review_fields']),set(value));self.assertEqual(set(c['card_fields']),set(value['card']))
        self.assertEqual(set(c['taxonomy_fields']),set(value['taxonomy']));self.assertEqual(set(c['query_fields']),set(filters()))
        self.assertEqual((c['viral_policy']['minimum_views'],c['viral_policy']['creator_multiplier'],c['viral_policy']['combination']),(100000,10,'AND'))
        self.assertEqual(c['viral_policy']['ugc_intake'],'EXEMPT');w=workflow_catalog()
        self.assertTrue(w['workflows']['viral_discovery']['blockers']);self.assertTrue(w['workflows']['social_publish']['blockers'])
        self.assertTrue({'discovery.review','discovery.collect','discovery.handoff'}<=set(w['workflows']['local_evidence']['operations']))

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for watch/attempt acceptance')
    async def test_watch_attempt_clients_retain_failures_and_cannot_execute_handoff(self):
        agent=self.grant(['discovery.watch','discovery.attempt','discovery.handoff','discovery.read'])
        service=Discovery(self.store);review=service.save_review(APP,self.review_body());collection=service.collect(APP,self.collection_body())
        value=dict(kind='CREATOR',subjects=['creator'],query=self.collection_body()['query'],source='Synthetic permitted operator export',interval_seconds=86400,confirm_authorized_reads=True)
        saved=self.cli(self.envelope('discovery.watch',dict(id='client-watch',version=0,manifest_version=self.version,data=value)))
        self.assertEqual(saved['data']['schedule'],'NOT_ACTIVATED')
        body=dict(id='client-attempt',manifest_version=self.version,watch_id=saved['id'],watch_hash=saved['hash'],collection_id=collection['id'],collection_hash=collection['hash'],source_results=[dict(source='creator',status='FAILED',detail='Synthetic unavailable read')])
        async with self.session() as client:
            result=await client.call_tool('wmm_discovery_attempt',dict(app_id=APP,input=body));self.assertFalse(result.isError,result.content)
            self.assertEqual(result.structuredContent['data']['data']['source_results'],body['source_results'])
        before=history(self.store,APP,dict(kind='ATTEMPT'))['total']
        with self.assertRaises(ClientError):agent.call(self.envelope('discovery.handoff',dict(manifest_version=self.version,collection_id=collection['id'],collection_hash=collection['hash'],reference_id=self.source['reference_id'],review_hash=review['hash'])))
        self.assertEqual(history(self.store,APP,dict(kind='ATTEMPT'))['total'],before)

    def test_current_source_detects_changed_review_and_tampered_capture(self):
        from mission_control.discovery_access import current_source
        from mission_control.funnel_store import app_context
        service=Discovery(self.store);saved=service.save_review(APP,self.review_body());collection=service.collect(APP,self.collection_body())
        row=collection['data']['results'][0]
        with connection(self.store.path) as db:self.assertTrue(current_source(db,APP,app_context(db,APP),row))
        service.save_review(APP,dict(self.review_body(),version=1,data=reviewed(baseline=[])))
        with connection(self.store.path) as db:self.assertFalse(current_source(db,APP,app_context(db,APP),row))
        with connection(self.store.path) as db:self.assertFalse(current_source(db,APP,app_context(db,APP),dict(row,source_hash='0'*64)))

    def test_owner_revocation_before_business_transaction_rolls_back(self):
        import threading
        from mission_control.discovery_contract import review as original
        def revoke(value):
            result=original(value)
            def change():
                with connection(self.store.path) as db:db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",(APP,))
            t=threading.Thread(target=change);t.start();t.join(timeout=5);self.assertFalse(t.is_alive());return result
        with patch('mission_control.discovery_store.contract.review',side_effect=revoke),self.assertRaises(ClientError):
            self.owner.request('POST','/api/apps/'+APP+'/discovery/review',self.review_body())
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM discovery_documents').fetchone()[0],0)

    def test_owner_selected_review_requires_separate_human_checker(self):
        from mission_control.review_access import Access
        from mission_control.operator_client import OperatorClient
        from tests import test_verified_review as identities
        Access(self.store).save(APP,identities.OWNER,identities.CHECKER,dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        checker=OperatorClient(self.origin);checker.bootstrap();checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        body=dict(self.body(['discovery.review','discovery.read'],100),manifest_version=self.version,review_operations=['discovery.review'])
        issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',body);agent=OperatorClient(self.origin,grant_token=issued['token'])
        envelope=self.envelope('discovery.review',self.review_body())
        with self.assertRaises(ClientError):agent.call(envelope)
        prepared=agent.review('prepare',dict(id='review-research-save',envelope=envelope))
        self.assertEqual(history(self.store,APP,dict(kind='REVIEW'))['total'],0)
        packet=dict(id=prepared['id'],revision=prepared['checkpoint']['revision'],packet_hash=prepared['checkpoint']['hash'])
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/agent-reviews/approve',packet)
        approved=checker.request('POST','/api/apps/'+APP+'/agent-reviews/approve',packet)
        result=agent.review('resume',dict(app_id=APP,id=prepared['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(result['checkpoint']['state'],'SUCCEEDED');self.assertEqual(result['result']['data']['id'],'client-review')
        with self.assertRaises(ClientError):agent.review('resume',dict(app_id=APP,id=prepared['id'],revision=approved['revision'],packet_hash=approved['hash']))

    def test_json_body_bounds_and_route_reject_before_domain_access(self):
        from email.message import Message
        from types import SimpleNamespace
        from unittest.mock import Mock
        from io import BytesIO
        from mission_control.discovery_http import route,json_body
        headers=Message();headers['Content-Type']='application/json';headers['Content-Length']='2'
        handler=SimpleNamespace(command='POST',headers=headers,rfile=BytesIO(b'{}'),connection=Mock(),path='/api/apps/sample-one/discovery/history')
        handler.connection.gettimeout.return_value=None
        self.assertEqual(route(handler,['api','apps','sample-one','discovery','history']),'history');self.assertEqual(json_body(handler),{})
        headers['Content-Length']='2'
        with self.assertRaises(Invalid):json_body(handler)
        del headers['Content-Length'];headers['Content-Length']='1048577'
        with self.assertRaises(Invalid):json_body(handler)
        del headers['Content-Length'];headers['Content-Length']='2';headers['Transfer-Encoding']='chunked'
        with self.assertRaises(Invalid):json_body(handler)
        for body in (None,[],{},dict(kind='INVALID'),dict(kind='WATCH',approved=True)):
            with self.subTest(body=body),self.assertRaises(Invalid):history(self.store,APP,body)
        for body in (None,[],{},dict(id='missing',kind='INVALID'),dict(id='missing',kind='REVIEW',version=0)):
            with self.subTest(body=body),self.assertRaises(Invalid):read(self.store,APP,body)
