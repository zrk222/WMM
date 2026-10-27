"""Actual owner HTTP, subprocess CLI and official MCP inspect the same checklist."""
import unittest
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.operator_client import ClientError
from mission_control.packaging_contract import agent_contract
from mission_control.operation_catalog import catalog
from tests import test_packaging_clients as fixtures
from tests import test_agent_mcp as sdk


class HandoffClientsTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixtures.PackagingClientTests.setUp
    tearDown=fixtures.PackagingClientTests.tearDown
    body=fixtures.PackagingClientTests.body
    envelope=fixtures.PackagingClientTests.envelope
    grant=fixtures.PackagingClientTests.grant
    cli=fixtures.PackagingClientTests.cli
    session=fixtures.PackagingClientTests.session
    variant=fixtures.PackagingClientTests.variant
    shotlist=fixtures.PackagingClientTests.shotlist
    owner_call=fixtures.PackagingClientTests.owner_call

    def checklist(self):
        variant=self.owner_call('save',self.variant())
        shots=self.owner_call('save',self.shotlist(variant))
        return dict(manifest_version=shots['data']['manifest_version'],shots=dict(kind='SHOTS',id=shots['id'],version=shots['version'],sha256=shots['hash']))

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required')
    async def test_owner_cli_mcp_parity_and_read_only_effect(self):
        self.grant(['packaging.checklist'])
        body=self.checklist();expected=self.owner_call('checklist',body)
        self.assertEqual(self.cli(self.envelope('packaging.checklist',body)),expected)
        async with self.session() as client:
            tools=await client.list_tools()
            self.assertIn('wmm_packaging_checklist',{row.name for row in tools.tools})
            result=await client.call_tool('wmm_packaging_checklist',dict(app_id='sample-one',input=body))
            self.assertFalse(result.isError,result.content)
            self.assertEqual(result.structuredContent['data'],expected)
        self.assertFalse(expected['execution_authority'])
        self.assertIn('TIMED_ORIGINAL_MEDIA_REQUIRED',expected['rows'][0]['gaps'])
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        self.assertIn('packaging.checklist',agent_contract()['operations'])
        self.assertEqual(catalog()['operations']['packaging.checklist']['effect'],'READ_PRIVATE_LOCAL_DATA')

    def test_scopes_revisions_forged_fields_and_revocation_reject(self):
        agent=self.grant(['packaging.checklist']);body=self.checklist()
        for invalid in [dict(body,approved=True),dict(body,shots=dict(body['shots'],sha256='0'*64)),dict(body,manifest_version=999)]:
            with self.subTest(invalid=invalid),self.assertRaises((ClientError,Invalid)):
                agent.call(self.envelope('packaging.checklist',invalid))
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.checklist',body,app_id='sample-two'))
        self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',dict(id=self.issued['grant']['id'],version=1))
        with self.assertRaises(ClientError):agent.call(self.envelope('packaging.checklist',body))
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
