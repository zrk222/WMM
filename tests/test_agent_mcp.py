"""Actual SDK/stdio subprocess and CLI conformance against an isolated WMM server."""
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
try:
    import anyio
    import jsonschema
    from mcp import ClientSession,StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP=True
except ImportError:
    HAS_MCP=False
from mission_control.agent_mcp import tool_definitions,execute_tool,main
from mission_control.operation_catalog import OPERATIONS
from mission_control.common import Invalid
from tests import test_agent_cli as fixtures
from tests.test_aso_validation import listing
from tests.test_ledger import cohort,event


class MCPDefinitionTests(unittest.TestCase):
    @unittest.skipUnless(HAS_MCP,'Optional MCP SDK is not installed')
    def test_catalog_schemas_effects_and_closed_boundary(self):
        rows=tool_definitions()
        self.assertEqual(len(rows),len(OPERATIONS)+1)
        self.assertEqual(len({row['name'] for row in rows}),len(rows))
        for name,rule in OPERATIONS.items():
            tool=next(row for row in rows if row['name']=='wmm_'+name.replace('.','_'))
            jsonschema.Draft202012Validator.check_schema(tool['inputSchema'])
            self.assertEqual(tool['annotations']['readOnlyHint'],rule['method']=='GET')
            self.assertEqual(tool['annotations']['idempotentHint'],rule['method']=='GET')
            self.assertFalse(tool['annotations']['openWorldHint'])
            self.assertFalse(tool['inputSchema']['additionalProperties'])
        with patch('mission_control.agent_mcp.OperatorClient') as client:
            self.assertFalse(execute_tool('unused','wmm_catalog',{})['full_agent_operation'])
            for name,args in [('human_approve',{}),('wmm_growth_history',dict(app_id='../app',input={})),
                    ('wmm_growth_history',dict(app_id='sample-one',input={},operation='snapshot.export')),
                    ('wmm_billing_save',dict(app_id='sample-one',input=dict(id='x',manifest_version=1,kind='credential',title='x',source='x',data={}))),
                    ('wmm_catalog',dict(approval=True))]:
                with self.assertRaises(Invalid):execute_tool('unused',name,args)
            client.assert_not_called()

    def test_invalid_origin_and_missing_optional_sdk_fail_without_install(self):
        import builtins
        original=builtins.__import__
        def missing(name,*args,**kwargs):
            if name=='anyio':raise ImportError('Synthetic missing optional SDK')
            return original(name,*args,**kwargs)
        self.assertEqual(main(['--origin','https://example.com']),2)
        with patch('builtins.__import__',side_effect=missing):
            self.assertEqual(main(['--origin','http://127.0.0.1:57599']),2)


@unittest.skipUnless(HAS_MCP,'Optional MCP SDK is not installed')
class MCPSubprocessTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.AgentCLITests.setUp
    tearDown=fixtures.AgentCLITests.tearDown
    cli=fixtures.AgentCLITests.cli
    call=fixtures.AgentCLITests.call

    @asynccontextmanager
    async def session(self,origin=None):
        params=StdioServerParameters(command=sys.executable,
            args=['-m','mission_control.agent_mcp','--origin',origin or self.origin],cwd=str(Path.cwd()))
        with anyio.fail_after(45):
            async with stdio_client(params) as (reader,writer):
                async with ClientSession(reader,writer) as client:
                    initialized=await client.initialize()
                    self.assertEqual(initialized.serverInfo.name,'wmm-local-operations')
                    yield client

    async def tool(self,client,name,body=None,app='sample-one',**extra):
        return await client.call_tool('wmm_'+name.replace('.','_'),dict(app_id=app,input=body or {},**extra))

    def data(self,result):
        self.assertFalse(result.isError,result.content)
        return result.structuredContent['data']

    async def test_stdio_initialize_discover_catalog_ping_without_wmm(self):
        async with self.session('http://127.0.0.1:1') as client:
            self.assertEqual(len((await client.list_tools()).tools),len(OPERATIONS)+1)
            await client.send_ping()
            value=self.data(await client.call_tool('wmm_catalog',{}))
            self.assertFalse(value['full_agent_operation'])
            failure=await self.tool(client,'workspace.read')
            self.assertTrue(failure.isError)
            self.assertIn('TRANSPORT_UNAVAILABLE',failure.content[0].text)
            self.assertEqual(self.data(await client.call_tool('wmm_catalog',{}))['catalog_sha256'],value['catalog_sha256'])

    async def test_mcp_and_cli_share_immutable_growth_history_and_app_scope(self):
        body=dict(id='mcp-listing',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))
        async with self.session() as client:
            saved=self.data(await self.tool(client,'growth.save',body))
            result,history=self.call('growth.history')
            self.assertEqual(result.returncode,0)
            self.assertEqual(history['history'][0]['hash'],saved['hash'])
            body['id']='cli-listing'
            result,other=self.call('growth.save',body)
            self.assertEqual(result.returncode,0)
            rows=self.data(await self.tool(client,'growth.history'))['history']
            self.assertEqual({row['hash'] for row in rows},{saved['hash'],other['hash']})
            self.assertEqual(self.data(await self.tool(client,'growth.history',app='sample-two'))['history'],[])
            self.assertEqual(self.data(await self.tool(client,'workspace.read'))['app']['data']['name'],'Synthetic Café 東京')

    async def test_invalid_arguments_stale_source_and_unknown_tools_leave_history_intact(self):
        async with self.session() as client:
            cases=[('wmm_growth_history',dict(app_id='sample-one',input={},extra=True)),
                ('wmm_growth_history',dict(app_id='../sample-two',input={})),
                ('wmm_human_approve',dict(app_id='sample-one',input={})),
                ('wmm_billing_save',dict(app_id='sample-one',input=dict(id='bad',manifest_version=1,kind='credential',title='x',source='x',data={}))),
                ('wmm_growth_save',dict(app_id='sample-one',input=dict(id='stale',manifest_version=99,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))))]
            for name,args in cases:
                result=await client.call_tool(name,args)
                self.assertTrue(result.isError,(name,result))
            self.assertEqual(self.data(await self.tool(client,'growth.history'))['history'],[])
            self.assertEqual(list(Path(self.tmp.name).glob('*session*')),[])

    async def test_mcp_ledger_write_cli_measurement_readback(self):
        async with self.session() as client:
            self.data(await self.tool(client,'cohort.define',cohort()))
            result=self.data(await self.tool(client,'events.import',dict(cohort_id='pilot-1',events=[event('mcp-install','INSTALL')])))
            self.assertEqual(result['inserted'],1)
            status,value=self.call('measurement.read')
            self.assertEqual(status.returncode,0)
            self.assertEqual(value[0]['cohort']['cohort_id'],'pilot-1')
            replay=self.data(await self.tool(client,'events.import',dict(cohort_id='pilot-1',events=[event('mcp-install','INSTALL')])))
            self.assertEqual(replay['inserted'],0)


if __name__=='__main__':unittest.main()
