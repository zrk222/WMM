"""Real CLI and official SDK MCP reviewed lifecycle with distinct authenticated checker HTTP."""
from contextlib import asynccontextmanager
from pathlib import Path
import json,os,subprocess,sys,unittest
from tests import test_agent_review_http as fixture
from tests import test_agent_mcp as sdk
from mission_control.operator_client import ClientError
from mission_control.operation_catalog import OPERATIONS


class ReviewClientTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixture.ReviewHTTPTests.setUp
    setUp_base=fixture.ReviewHTTPTests.setUp_base
    tearDown=fixture.ReviewHTTPTests.tearDown
    body=fixture.ReviewHTTPTests.body
    envelope=fixture.ReviewHTTPTests.envelope
    listing_body=fixture.ReviewHTTPTests.listing_body
    issue_reviewed=fixture.ReviewHTTPTests.issue_reviewed
    human=fixture.ReviewHTTPTests.human
    approve=fixture.ReviewHTTPTests.approve

    def cli(self,action,body,grant=True):
        args=[sys.executable,'-m','mission_control.agent_cli','review-'+action,'--origin',self.origin]
        env=dict(os.environ);env.pop('WMM_AGENT_GRANT',None)
        if grant:args+=['--use-grant'];env['WMM_AGENT_GRANT']=self.token
        result=subprocess.run(args,input=json.dumps(body).encode(),capture_output=True,env=env,timeout=30)
        return result,json.loads(result.stdout or result.stderr)

    @asynccontextmanager
    async def session(self,grant=True):
        args=['-m','mission_control.agent_mcp','--origin',self.origin]
        if grant:args+=['--use-grant']
        params=sdk.StdioServerParameters(command=sys.executable,args=args,env=dict(WMM_AGENT_GRANT=self.token) if grant else {},cwd=str(Path.cwd()))
        with sdk.anyio.fail_after(45):
            async with sdk.stdio_client(params) as (reader,writer):
                async with sdk.ClientSession(reader,writer) as client:
                    await client.initialize();yield client

    @unittest.skipUnless(sdk.HAS_MCP,'Optional MCP SDK required for two-client conformance')
    async def test_cli_prepare_human_approval_mcp_resume_and_shared_receipt(self):
        sessions=len(self.server.sessions)
        result,prepared=self.cli('prepare',dict(id='review-one',envelope=self.input))
        self.assertEqual(result.returncode,0,prepared)
        approved=self.approve(prepared)
        async with self.session() as client:
            listed=(await client.list_tools()).tools
            names={row.name for row in listed}
            self.assertEqual(len(names),len(OPERATIONS)+4);self.assertNotIn('wmm_review_approve',names)
            status=await client.call_tool('wmm_review_status',dict(app_id='sample-one',id='review-one'))
            self.assertEqual(status.structuredContent['data']['checkpoint']['hash'],prepared['checkpoint']['hash'])
            done=await client.call_tool('wmm_review_resume',dict(app_id='sample-one',id='review-one',revision=approved['revision'],packet_hash=approved['hash']))
            self.assertFalse(done.isError,done.content)
            self.assertEqual(done.structuredContent['data']['checkpoint']['state'],'SUCCEEDED')
            denied=await client.call_tool('wmm_review_approve',dict(id='review-one',revision=approved['revision'],packet_hash=approved['hash']))
            self.assertTrue(denied.isError)
        result,readback=self.cli('status',dict(app_id='sample-one',id='review-one'))
        self.assertEqual(result.returncode,0)
        self.assertEqual(readback['result'],done.structuredContent['data']['result'])
        self.assertNotIn(self.token,str(readback));self.assertEqual(len(self.server.sessions),sessions)

    @unittest.skipUnless(sdk.HAS_MCP,'Optional MCP SDK required for two-client conformance')
    async def test_mcp_prepare_denied_early_resume_then_human_approval_cli_resume(self):
        async with self.session() as client:
            result=await client.call_tool('wmm_review_prepare',dict(id='review-one',envelope=self.input))
            self.assertFalse(result.isError,result.content);prepared=result.structuredContent['data'];row=prepared['checkpoint']
            early,value=self.cli('resume',dict(app_id='sample-one',id='review-one',revision=row['revision'],packet_hash=row['hash']))
            self.assertEqual(early.returncode,3)
            approved=self.approve(prepared)
            completed,value=self.cli('resume',dict(app_id='sample-one',id='review-one',revision=approved['revision'],packet_hash=approved['hash']))
            self.assertEqual(completed.returncode,0,value)
            read=await client.call_tool('wmm_review_status',dict(app_id='sample-one',id='review-one'))
            self.assertEqual(read.structuredContent['data']['result'],value['result'])
            repeated=await client.call_tool('wmm_review_resume',dict(app_id='sample-one',id='review-one',revision=approved['revision'],packet_hash=approved['hash']))
            self.assertTrue(repeated.isError)

    @unittest.skipUnless(sdk.HAS_MCP,'Optional MCP SDK required for schema conformance')
    async def test_no_grant_exposes_no_review_tools_or_implicit_session_fallback(self):
        sessions=len(self.server.sessions)
        result,value=self.cli('prepare',dict(id='review-one',envelope=self.input),grant=False)
        self.assertEqual(result.returncode,2)
        self.assertEqual(value['error']['code'],'INVALID_INPUT')
        async with self.session(grant=False) as client:
            names={row.name for row in (await client.list_tools()).tools}
            self.assertEqual(len(names),len(OPERATIONS)+1)
            self.assertFalse(any(name.startswith('wmm_review_') for name in names))
            result=await client.call_tool('wmm_review_status',dict(app_id='sample-one',id='review-one'))
            self.assertTrue(result.isError)
        self.assertEqual(len(self.server.sessions),sessions)

    async def test_cli_rejects_edited_resume_fields_and_reports_cancelled_history(self):
        result,prepared=self.cli('prepare',dict(id='review-one',envelope=self.input))
        self.assertEqual(result.returncode,0)
        row=prepared['checkpoint']
        result,rejected=self.cli('resume',dict(app_id='sample-one',id='review-one',revision=row['revision'],packet_hash=row['hash'],envelope=self.input))
        self.assertEqual(result.returncode,2)
        self.human('cancel',dict(id='review-one',revision=row['revision']),self.owner)
        result,status=self.cli('status',dict(app_id='sample-one',id='review-one'))
        self.assertEqual(result.returncode,0);self.assertEqual(status['checkpoint']['state'],'CANCELLED')
