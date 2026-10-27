"""Scoped agent discovery and actual CLI/official MCP read owner guidance."""
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.creative_taste import guidance
from mission_control.operation_catalog import catalog
from mission_control.operator_client import ClientError
from mission_control.db import connection
from tests import test_packaging_clients as fixtures
from tests import test_agent_mcp as sdk


class TasteClientTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.PackagingClientTests.setUp
    tearDown=fixtures.PackagingClientTests.tearDown
    body=fixtures.PackagingClientTests.body
    envelope=fixtures.PackagingClientTests.envelope
    grant=fixtures.PackagingClientTests.grant
    cli=fixtures.PackagingClientTests.cli
    session=fixtures.PackagingClientTests.session
    owner_call=fixtures.PackagingClientTests.owner_call

    def reviewed(self):
        return self.owner_call('taste-review',dict(id='taste-one',version=0,manifest_version=self.store.app('sample-one')['version'],
            policy_sha256=guidance()['policy_sha256'],data=dict(lens='product',voice='Use plain words.',visual='Show the real product.',examples=[],exclusions=['No fabricated proof.'])))

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required')
    async def test_owner_cli_mcp_read_history_and_discovery_parity(self):
        self.grant(['packaging.taste-read','packaging.taste-history'])
        self.assertEqual(self.cli(self.envelope('packaging.taste-history',{}))['items'],[])
        saved=self.reviewed();body=dict(id=saved['id'],version=saved['version'])
        expected=self.owner_call('taste-read',body);history=self.owner_call('taste-history',{})
        self.assertEqual(self.cli(self.envelope('packaging.taste-read',body)),expected)
        self.assertEqual(self.cli(self.envelope('packaging.taste-history',{})),history)
        async with self.session() as client:
            tools=await client.list_tools();names={tool.name for tool in tools.tools}
            self.assertTrue({'wmm_packaging_taste-read','wmm_packaging_taste-history'}<=names)
            self.assertNotIn('wmm_packaging_taste-review',names)
            for operation,value,answer in [('read',body,expected),('history',{},history)]:
                result=await client.call_tool('wmm_packaging_taste-'+operation,dict(app_id='sample-one',input=value))
                self.assertFalse(result.isError,result.content)
                self.assertEqual(result.structuredContent['data'],answer)
        self.assertEqual(history['items'][0]['hash'],saved['hash'])
        self.assertFalse(expected['execution_authority']);self.assertFalse(expected['reuse_authority'])
        self.assertNotIn('data',history['items'][0])
        self.assertEqual(self.owner_call('taste-history',dict(offset=1))['items'],[])
        for operation in ['packaging.taste-read','packaging.taste-history']:
            self.assertEqual(catalog()['operations'][operation]['effect'],'READ_PRIVATE_LOCAL_DATA')

    def test_foreign_forged_ungranted_and_revoked_agent_access_reject(self):
        agent=self.grant(['packaging.taste-read','packaging.taste-history'])
        saved=self.reviewed();body=dict(id=saved['id'])
        for operation,value in [('packaging.taste-read',dict(body,approved=True)),('packaging.taste-read',dict(body,version=999)),
                                ('packaging.taste-history',dict(offset=True)),('packaging.taste-review',{})]:
            with self.subTest(operation=operation),self.assertRaises((ClientError,Invalid)):agent.call(self.envelope(operation,value))
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.taste-read',body,app_id='sample-two'))
        self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.taste-read',body))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM creative_taste_reviews').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_current_agent_read_exposes_stale_guidance_without_approving_it(self):
        agent=self.grant(['packaging.taste-read'])
        saved=self.reviewed()
        with patch('mission_control.creative_taste_store.guidance',return_value=dict(guidance(),policy_sha256='f'*64)):
            value=agent.call(self.envelope('packaging.taste-read',dict(id=saved['id'])))
        self.assertEqual(value['source_status'],'STALE_OWNER_REVIEW')
        self.assertFalse(value['execution_authority'])
