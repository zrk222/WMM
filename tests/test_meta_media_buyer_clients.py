"""Actual HTTP, CLI subprocess and official MCP SDK share the app-bound specialist."""
import json
import unittest
from mission_control.operator_client import ClientError
from tests import test_agent_grants as fixture
from tests import test_video_edit_clients as editing
from tests import test_agent_mcp as sdk

APP='sample-one'
INPUT=dict(profile='meta_media_buyer')


class MetaBuyerClientTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown
    body=fixture.GrantTests.body
    envelope=fixture.GrantTests.envelope
    grant=editing.VideoClientsTests.grant
    cli=editing.VideoClientsTests.cli
    session=editing.VideoClientsTests.session

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK is required for specialist conformance')
    async def test_http_cli_mcp_same_profile_with_no_added_tools_or_effects(self):
        agent=self.grant(['operations.read'])
        path='/api/apps/'+APP+'/agent-operations'
        before=self.store.export(APP)
        expected=self.owner.request('GET',path+'?profile=meta_media_buyer')
        def inspected(value, used):
            metadata=value.pop('agent_authority')
            self.assertEqual(value,expected)
            self.assertEqual(metadata['grant_id'],self.issued['grant']['id'])
            self.assertEqual(metadata['used'],used)
            self.assertEqual(metadata['max_calls'],100)
            self.assertEqual(metadata['remaining_calls'],100-used)
            self.assertEqual(metadata['consent_revision'],0)
            self.assertEqual(metadata['effective_expires'],self.issued['grant']['expires'])
        inspected(agent.call(self.envelope('operations.read',INPUT)),1)
        inspected(self.cli(self.envelope('operations.read',INPUT)),2)
        self.assertEqual(self.owner.call(self.envelope('operations.read',INPUT)),expected)
        async with self.session() as client:
            tools=(await client.list_tools()).tools
            from mission_control.operation_catalog import OPERATIONS
            self.assertEqual(len(tools),len(OPERATIONS)+4)  # Existing three review tools are enabled for grants.
            result=await client.call_tool('wmm_operations_read',dict(app_id=APP,input=INPUT))
            self.assertFalse(result.isError,result.content)
            inspected(result.structuredContent['data'],3)
            bad=await client.call_tool('wmm_operations_read',dict(app_id=APP,input=dict(profile='wrong')))
            self.assertTrue(bad.isError)
            foreign=await client.call_tool('wmm_operations_read',dict(app_id='sample-two',input=INPUT))
            self.assertTrue(foreign.isError)
        after=self.store.export(APP)
        self.assertEqual(before['payload'],after['payload'])
        self.assertNotIn(self.token,json.dumps(expected))
        self.assertNotIn('specialist',self.owner.request('GET',path))

    def test_exact_http_query_invalid_inputs_foreign_and_revoked_grant(self):
        agent=self.grant(['operations.read'])
        path='/api/apps/'+APP+'/agent-operations'
        for query in ('?profile=wrong','?profile=','?profile=meta_media_buyer&profile=meta_media_buyer',
                      '?profile=meta_media_buyer&approved=true','?profile=%6deta_media_buyer'):
            with self.subTest(query=query),self.assertRaises(ClientError):self.owner.request('GET',path+query)
        for value in (None,{},True,'wrong'):
            with self.assertRaises((ValueError,ClientError)):agent.call(self.envelope('operations.read',dict(profile=value)))
        with self.assertRaises(ClientError):agent.call(self.envelope('operations.read',INPUT,app_id='sample-two'))
        self.owner.request('POST','/api/apps/'+APP+'/agent-grants/revoke',dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(ClientError):agent.call(self.envelope('operations.read',INPUT))
        self.assertEqual(self.owner.request('GET',path+'?profile=meta_media_buyer')['specialist']['app_id'],APP)

    def test_changed_app_requires_current_grant_and_changes_contract(self):
        agent=self.grant(['operations.read'])
        first=agent.call(self.envelope('operations.read',INPUT))
        app=self.store.app(APP)
        self.store.save_app(APP,dict(app['data'],job='Changed synthetic outcome'),app['version'])
        with self.assertRaises(ClientError):agent.call(self.envelope('operations.read',INPUT))
        second=self.owner.request('GET','/api/apps/'+APP+'/agent-operations?profile=meta_media_buyer')
        self.assertNotEqual(first['specialist']['contract_sha256'],second['specialist']['contract_sha256'])
