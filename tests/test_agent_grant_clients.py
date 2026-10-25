"""Real CLI and official SDK MCP clients use scoped credentials without cookie fallback."""
from contextlib import asynccontextmanager
from pathlib import Path
import json
import os
import subprocess
import sys
import unittest
from tests import test_agent_grants as fixture
from tests import test_agent_mcp as sdk


class GrantClientTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixture.GrantTests.setUp
    tearDown=fixture.GrantTests.tearDown
    body=fixture.GrantTests.body
    issue=fixture.GrantTests.issue
    envelope=fixture.GrantTests.envelope
    listing_body=fixture.GrantTests.listing_body

    def cli(self,envelope,token=None):
        env=dict(os.environ);env.pop('WMM_AGENT_GRANT',None)
        if token is not None:env['WMM_AGENT_GRANT']=token
        result=subprocess.run([sys.executable,'-m','mission_control.agent_cli','call','--origin',self.origin,'--use-grant'],
            input=json.dumps(envelope).encode(),capture_output=True,env=env,timeout=30)
        return result,json.loads(result.stdout or result.stderr)

    @asynccontextmanager
    async def session(self,token):
        params=sdk.StdioServerParameters(command=sys.executable,args=['-m','mission_control.agent_mcp','--origin',self.origin,'--use-grant'],
            env=dict(WMM_AGENT_GRANT=token),cwd=str(Path.cwd()))
        with sdk.anyio.fail_after(45):
            async with sdk.stdio_client(params) as (reader,writer):
                async with sdk.ClientSession(reader,writer) as client:
                    await client.initialize()
                    yield client

    @unittest.skipUnless(sdk.HAS_MCP,'Optional MCP SDK required for cross-client acceptance')
    async def test_both_transports_share_granted_history_and_revocation_without_sessions(self):
        issued=self.issue();token=issued['token'];sessions=len(self.server.sessions)
        result,saved=self.cli(self.envelope('growth.save',self.listing_body()),token)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn(token,result.stdout.decode())
        async with self.session(token) as client:
            rows=await client.call_tool('wmm_growth_history',dict(app_id='sample-one',input={}))
            self.assertFalse(rows.isError,rows.content)
            self.assertEqual(rows.structuredContent['data']['history'][0]['hash'],saved['hash'])
            second=dict(self.listing_body(),id='second-granted-listing')
            written=await client.call_tool('wmm_growth_save',dict(app_id='sample-one',input=second))
            self.assertFalse(written.isError,written.content)
            result,history=self.cli(self.envelope(),token)
            self.assertEqual(result.returncode,0)
            self.assertEqual({row['id'] for row in history['history']},{'grant-listing','second-granted-listing'})
            denied=await client.call_tool('wmm_growth_history',dict(app_id='sample-two',input={}))
            self.assertTrue(denied.isError)
            result,_=self.cli(self.envelope(app_id='sample-two'),token)
            self.assertEqual(result.returncode,3)
            self.owner.request('POST','/api/apps/sample-one/agent-grants/revoke',dict(id=issued['grant']['id'],version=1))
            denied=await client.call_tool('wmm_growth_history',dict(app_id='sample-one',input={}))
            self.assertTrue(denied.isError)
            result,_=self.cli(self.envelope(),token)
            self.assertEqual(result.returncode,3)
        self.assertEqual(len(self.server.sessions),sessions)

    async def test_missing_or_malformed_environment_fails_before_network(self):
        sessions=len(self.server.sessions)
        for token in (None,'synthetic-invalid-grant'):
            result,value=self.cli(self.envelope(),token)
            self.assertEqual(result.returncode,2)
            self.assertEqual(value['error']['code'],'INVALID_INPUT')
            self.assertEqual(result.stdout,b'')
        env=dict(os.environ);env.pop('WMM_AGENT_GRANT',None)
        result=subprocess.run([sys.executable,'-m','mission_control.agent_mcp','--origin',self.origin,'--use-grant'],env=env,capture_output=True,timeout=30)
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
        self.assertEqual(len(self.server.sessions),sessions)

    async def test_cli_quota_failure_has_no_session_fallback_or_token_echo(self):
        token=self.issue(['growth.history'],max_calls=1)['token'];sessions=len(self.server.sessions)
        result,_=self.cli(self.envelope(),token);self.assertEqual(result.returncode,0)
        result,value=self.cli(self.envelope(),token)
        self.assertEqual(result.returncode,3);self.assertEqual(value['error']['http_status'],403)
        self.assertNotIn(token,(result.stdout+result.stderr).decode())
        self.assertEqual(len(self.server.sessions),sessions)
