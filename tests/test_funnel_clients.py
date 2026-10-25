"""Actual owner HTTP, grant CLI and official MCP share immutable funnel evidence."""
import json
import unittest
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.common import Invalid
from mission_control.operator_client import ClientError
from mission_control.ledger import Ledger
from mission_control.funnel_store import Funnels
from tests import test_agent_grants as grants
from tests import test_video_edit_clients as editing
from tests import test_agent_mcp as sdk
from tests.test_creative_rendering import prepared_render
from tests.test_funnel_contract import fixture,observed
from tests.test_ledger import cohort

APP='sample-one'


class FunnelClientsTests(unittest.IsolatedAsyncioTestCase):
    body=grants.GrantTests.body
    envelope=grants.GrantTests.envelope
    grant=editing.VideoClientsTests.grant
    cli=editing.VideoClientsTests.cli
    session=editing.VideoClientsTests.session
    tearDown=grants.GrantTests.tearDown

    def setUp(self):
        grants.GrantTests.setUp(self)
        app=self.store.app(APP)
        self.store.save_app(APP,dict(app['data'],job='Synthetic job',audience='Synthetic audience',activation='Saved fictional action'),app['version'])
        brief,_=prepared_render(self.store,APP);app=self.store.app(APP);self.version=app['version']
        self.plan=fixture()
        for key in ('release','locale','currency'):self.plan[key]=app['data'][key]
        self.plan['creative_refs']=[dict(kind='CREATIVE_BRIEF',id=brief['id'],version=brief['version'],sha256=brief['hash'])]
        Ledger(self.store.path).define(APP,cohort(cohort_id=self.plan['cohort_id'],release=self.plan['release'],locale=self.plan['locale'],currency=self.plan['currency'],starts_at=self.plan['attribution']['starts_at'],ends_at=self.plan['attribution']['ends_at'],matures_at='2026-11-01T00:00:00+00:00'))

    def payload(self):
        return dict(id='funnel-client',manifest_version=self.version,data=self.plan)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for funnel client acceptance')
    async def test_owner_cli_mcp_share_saved_funnel_and_observation_history(self):
        self.grant(['funnel.save','funnel.list','funnel.read','funnel.import','funnel.observations','funnel.report'])
        saved=self.cli(self.envelope('funnel.save',self.payload()))
        self.assertEqual(self.owner.request('POST','/api/apps/'+APP+'/funnels',self.payload()),saved)
        self.assertEqual(self.cli(self.envelope('funnel.list')),self.owner.request('GET','/api/apps/'+APP+'/funnels'))
        async with self.session() as client:
            tools={t.name for t in (await client.list_tools()).tools}
            self.assertTrue({'wmm_funnel_save','wmm_funnel_import','wmm_funnel_report'}<=tools)
            self.assertNotIn('wmm_human_approve',tools)
            data=dict(funnel_hash=saved['hash'],manifest_version=self.version,observations=[observed(self.plan)])
            result=await client.call_tool('wmm_funnel_import',dict(app_id=APP,resource_id=saved['id'],input=data))
            self.assertFalse(result.isError,result.content)
            self.assertEqual(result.structuredContent['data']['inserted'],1)
            repeated=self.owner.request('POST','/api/apps/'+APP+'/funnels/'+saved['id']+'/observations',data)
            self.assertEqual(repeated['duplicates'],1)
            read=await client.call_tool('wmm_funnel_observations',dict(app_id=APP,resource_id=saved['id'],input={}))
            self.assertFalse(read.isError,read.content)
            self.assertEqual(read.structuredContent['data'],self.owner.request('GET','/api/apps/'+APP+'/funnels/'+saved['id']+'/observations'))
            report=await client.call_tool('wmm_funnel_report',dict(app_id=APP,resource_id=saved['id'],input={}))
            self.assertFalse(report.isError,report.content)
            self.assertEqual(report.structuredContent['data']['definition_hash'],saved['hash'])
            self.assertEqual(report.structuredContent['data']['stages'][0]['count'],0)
            self.assertNotIn(self.token,json.dumps(report.structuredContent))

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for funnel pagination acceptance')
    async def test_paging_and_single_read_are_identical_in_owner_cli_and_mcp(self):
        agent=self.grant(['funnel.list','funnel.read','funnel.observations'])
        flow=Funnels(self.store);saved=flow.save(APP,self.payload())
        values=[dict(observed(self.plan),event_id='page-'+str(i).zfill(3))for i in range(101)]
        flow.ingest(APP,dict(funnel_id=saved['id'],funnel_hash=saved['hash'],manifest_version=self.version,observations=values))
        path='/api/apps/'+APP+'/funnels/'+saved['id']
        expected=self.owner.request('GET',path+'/observations?offset=100')
        self.assertEqual((len(expected['items']),expected['total'],expected['next_offset']),(1,101,None))
        self.assertEqual(self.cli(dict(self.envelope('funnel.observations',dict(offset=100)),resource_id=saved['id'])),expected)
        self.assertEqual(self.cli(dict(self.envelope('funnel.read'),resource_id=saved['id'])),self.owner.request('GET',path))
        async with self.session() as client:
            page=await client.call_tool('wmm_funnel_observations',dict(app_id=APP,resource_id=saved['id'],input=dict(offset=100)))
            self.assertFalse(page.isError,page.content)
            self.assertEqual(page.structuredContent['data'],expected)
            full=await client.call_tool('wmm_funnel_read',dict(app_id=APP,resource_id=saved['id'],input={}))
            self.assertFalse(full.isError,full.content)
            self.assertEqual(full.structuredContent['data']['data']['definition'],self.plan)
        for query in ('offset=-1','offset=01','offset=10001','offset=true','offset=1&offset=2'):
            with self.subTest(query=query),self.assertRaises(ClientError):self.owner.request('GET',path+'/observations?'+query)
        for value in (-1,True,10001):
            with self.subTest(value=value),self.assertRaises((ClientError,ValueError)):
                agent.call(self.envelope('funnel.list',dict(offset=value)))

    def test_current_grant_foreign_scope_unknown_inputs_and_stale_manifest_are_denied(self):
        agent=self.grant(['funnel.list'])
        with self.assertRaises(ClientError):agent.call(self.envelope('funnel.save',self.payload()))
        with self.assertRaises(ClientError):agent.call(self.envelope('funnel.list',app_id='sample-two'))
        with self.assertRaises((ClientError,ValueError)):agent.call(self.envelope('funnel.list',dict(approved=True)))
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/funnels',dict(self.payload(),manifest_version=self.version+1))
        self.assertEqual(Funnels(self.store).list(APP)['items'],[])

    def test_raw_routes_framing_duplicate_json_and_no_csrf_create_no_funnel(self):
        for path in ('/api/apps/'+APP+'/funnels?extra=1','/api/apps/'+APP+'/funnels/','/api/apps/'+APP+'/funnels/unknown/extra','/api/apps/'+APP+'/funnels%2f'):
            with self.subTest(path=path),self.assertRaises(ClientError):self.owner.request('GET',path)
        raw=json.dumps(self.payload()).replace('"manifest_version": '+str(self.version),'"manifest_version": '+str(self.version)+',"manifest_version": '+str(self.version))
        request=Request(self.origin+'/api/apps/'+APP+'/funnels',data=raw.encode(),method='POST',headers={'Origin':self.origin,'Content-Type':'application/json','X-CSRF-Token':self.owner.csrf})
        request.add_header('Cookie','; '.join(c.name+'='+c.value for c in self.owner.cookies))
        with self.assertRaises(HTTPError) as error:self.owner.opener.open(request)
        self.assertEqual(error.exception.code,400)
        request=Request(self.origin+'/api/apps/'+APP+'/funnels',data=json.dumps(self.payload()).encode(),method='POST',headers={'Origin':self.origin,'Content-Type':'application/json'})
        request.add_header('Cookie','; '.join(c.name+'='+c.value for c in self.owner.cookies))
        with self.assertRaises(HTTPError) as error:self.owner.opener.open(request)
        self.assertEqual(error.exception.code,403)
        self.assertEqual(Funnels(self.store).list(APP)['items'],[])

    def test_automation_map_classifies_all_new_operations_without_loosening_blockers(self):
        from mission_control.automation_requirements import workflow_catalog
        catalog=workflow_catalog()
        self.assertTrue({'funnel.list','funnel.read','funnel.save','funnel.import','funnel.observations','funnel.report'}<=set(catalog['workflows']['local_evidence']['operations']))
        self.assertTrue(catalog['workflows']['complete_analytics']['blockers'])
        self.assertEqual({name for row in catalog['workflows'].values()for name in row['operations']},set(catalog['operations']))

    def test_owner_role_revoked_before_write_transaction_cannot_commit(self):
        import threading
        from unittest.mock import patch
        from mission_control.db import connection
        from mission_control.funnel_contract import definition as original
        def revoke(value):
            result=original(value)
            def change():
                with connection(self.store.path) as db:
                    db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",(APP,))
            thread=threading.Thread(target=change);thread.start();thread.join(timeout=5)
            self.assertFalse(thread.is_alive())
            return result
        with patch('mission_control.funnel_store.definition',side_effect=revoke):
            with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/funnels',self.payload())
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM growth_funnels').fetchone()[0],0)

    def test_funnel_save_owner_selected_review_requires_distinct_checker(self):
        from mission_control.review_access import Access
        from mission_control.operator_client import OperatorClient
        from tests import test_verified_review as identities
        Access(self.store).save(APP,identities.OWNER,identities.CHECKER,dict(login=identities.CHECKER['login'],role='CHECKER',status='ACTIVE',version=None))
        checker=OperatorClient(self.origin);checker.bootstrap()
        checker.request('POST','/api/identity/login',dict(token=identities.CHECKER_TOKEN))
        body=dict(self.body(['funnel.save','funnel.list'],100),manifest_version=self.version,review_operations=['funnel.save'])
        issued=self.owner.request('POST','/api/apps/'+APP+'/agent-grants/issue',body)
        agent=OperatorClient(self.origin,grant_token=issued['token'])
        envelope=self.envelope('funnel.save',self.payload())
        with self.assertRaises(ClientError):agent.call(envelope)
        prepared=agent.review('prepare',dict(id='review-funnel-save',envelope=envelope))
        self.assertEqual(Funnels(self.store).list(APP)['items'],[])
        packet=dict(id=prepared['id'],revision=prepared['checkpoint']['revision'],packet_hash=prepared['checkpoint']['hash'])
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/agent-reviews/approve',packet)
        approved=checker.request('POST','/api/apps/'+APP+'/agent-reviews/approve',packet)
        result=agent.review('resume',dict(app_id=APP,id=prepared['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(result['checkpoint']['state'],'SUCCEEDED')
        self.assertEqual(result['result']['data']['id'],'funnel-client')
        self.assertEqual(len(Funnels(self.store).list(APP)['items']),1)


class FunnelBodyTests(unittest.TestCase):
    def test_json_body_bounds_duplicates_transfer_framing_and_closed_route(self):
        from email.message import Message
        from types import SimpleNamespace
        from unittest.mock import Mock
        from io import BytesIO
        from mission_control.funnel_http import json_body,route
        headers=Message();headers['Content-Type']='application/json';headers['Content-Length']='2'
        handler=SimpleNamespace(headers=headers,rfile=BytesIO(b'{}'),connection=Mock(),path='/api/apps/sample-one/funnels')
        handler.connection.gettimeout.return_value=None
        self.assertEqual(json_body(handler),{})
        route(handler,['api','apps','sample-one','funnels'])
        headers['Content-Length']='2'
        with self.assertRaises(Invalid):json_body(handler)
        del headers['Content-Length'];headers['Content-Length']='1048577'
        with self.assertRaises(Invalid):json_body(handler)
        del headers['Content-Length'];headers['Content-Length']='2';headers['Transfer-Encoding']='chunked'
        with self.assertRaises(Invalid):json_body(handler)
        handler.path+='?extra=1'
        with self.assertRaises(Invalid):route(handler,['api','apps','sample-one','funnels'])

    def test_agent_contract_matches_implemented_definition_and_observation_fields(self):
        from mission_control.operation_catalog import catalog
        from tests.test_funnel_contract import fixture,observed
        value=catalog()['domain_contracts']['app_sales_funnel'];plan=fixture()
        self.assertEqual(set(value['definition_fields']),set(plan))
        self.assertEqual(set(value['outcome_fields']),set(plan['outcome']))
        self.assertEqual(set(value['observation_fields']),set(observed(plan)))
        self.assertEqual(set(value['source_fields']),set(plan['creative_refs'][0]))
        self.assertEqual(set(value['stage_fields']),set(plan['stages'][0]))
        self.assertNotIn('WEBINAR',value['routes'])
        self.assertIn('No automatic retry',value['authority'])
