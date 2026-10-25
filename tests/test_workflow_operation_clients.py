"""CLI and official MCP stdio conformance for real app evidence and pipeline jobs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from tests import test_workflow_operations as fixture
from tests import test_agent_review_clients as review_clients
from tests import test_agent_mcp as sdk
from mission_control.worker import run_once


@unittest.skipUnless(sdk.HAS_MCP,'Optional official SDK required for two-client acceptance')
class WorkflowClientTests(unittest.IsolatedAsyncioTestCase):
    setUp_base=fixture.WorkflowOperationTests.setUp_base
    tearDown=fixture.WorkflowOperationTests.tearDown
    body=fixture.WorkflowOperationTests.body
    envelope=fixture.WorkflowOperationTests.envelope
    listing_body=fixture.WorkflowOperationTests.listing_body
    issue_reviewed=fixture.WorkflowOperationTests.issue_reviewed
    human=fixture.WorkflowOperationTests.human
    approve=fixture.WorkflowOperationTests.approve
    workflow_grant=fixture.WorkflowOperationTests.workflow_grant
    evidence=fixture.WorkflowOperationTests.evidence
    pipeline=fixture.WorkflowOperationTests.pipeline
    session=review_clients.ReviewClientTests.session
    review_cli=review_clients.ReviewClientTests.cli

    def setUp(self):
        fixture.WorkflowOperationTests.setUp(self)
        self.agent,self.issued=self.workflow_grant(review=True)
        self.token=self.issued['token']

    def cli(self,envelope):
        env=dict(os.environ,WMM_AGENT_GRANT=self.token)
        result=subprocess.run([sys.executable,'-m','mission_control.agent_cli','call','--origin',self.origin,'--use-grant'],input=json.dumps(envelope).encode(),capture_output=True,env=env,timeout=30)
        self.assertNotIn(self.token,result.stdout.decode());self.assertNotIn(self.token,result.stderr.decode())
        return result,json.loads(result.stdout or result.stderr)

    async def test_cli_prepare_checker_approve_mcp_resume_and_actual_worker_receipt(self):
        count=len(self.server.sessions)
        process,error=self.cli(self.pipeline());self.assertEqual(process.returncode,3)
        self.assertEqual(error['error']['http_status'],403)
        process,view=self.review_cli('prepare',dict(id='cli-pipeline',envelope=self.pipeline()))
        self.assertEqual(process.returncode,0)
        approved=self.approve(view)
        async with self.session() as client:
            resumed=await client.call_tool('wmm_review_resume',dict(app_id='sample-one',id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
            self.assertFalse(resumed.isError,resumed.content)
            result=resumed.structuredContent['data'];queued=result['result']['data']
            self.assertEqual(result['checkpoint']['state'],'SUCCEEDED');self.assertEqual(queued['status'],'QUEUED')
            self.assertTrue(run_once(self.store))
            rows=await client.call_tool('wmm_jobs_read',dict(app_id='sample-one',input={}))
            self.assertFalse(rows.isError,rows.content)
            saved=rows.structuredContent['data'][0]
            self.assertEqual(saved['id'],queued['id']);self.assertEqual(saved['status'],'SUCCEEDED')
            self.assertEqual(len(saved['result']['outputs']),12)
            self.assertEqual(saved['result']['external_execution'],'NOT_RUN');self.assertEqual(saved['result']['spend_minor'],0)
            denied=await client.call_tool('wmm_jobs_read',dict(app_id='sample-two',input={}))
            self.assertTrue(denied.isError)
        process,rows=self.cli(self.envelope('jobs.read'));self.assertEqual(process.returncode,0)
        self.assertEqual(rows[0]['result'],saved['result']);self.assertEqual(len(self.server.sessions),count)

    async def test_mcp_prepare_cli_resume_evidence_persistence_and_reviewed_cancel(self):
        async with self.session() as client:
            prepared=await client.call_tool('wmm_review_prepare',dict(id='mcp-evidence',envelope=self.envelope('evidence.save',self.evidence())))
            self.assertFalse(prepared.isError,prepared.content)
            view=prepared.structuredContent['data'];approved=self.approve(view)
            process,result=self.review_cli('resume',dict(app_id='sample-one',id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
            self.assertEqual(process.returncode,0)
            saved=result['result']['data'];self.assertEqual(saved['kind'],'measurement')
            workspace=await client.call_tool('wmm_workspace_read',dict(app_id='sample-one',input={}))
            self.assertFalse(workspace.isError,workspace.content)
            found=next(r for r in workspace.structuredContent['data']['records'] if r['id']==saved['id'])
            self.assertEqual(found['hash'],saved['hash'])
            # Queue through the trusted local owner, then cancel through reviewed agent transport.
            queued=self.owner.call(self.pipeline())
            envelope=dict(self.envelope('job.cancel'),resource_id=queued['id'])
            denied=await client.call_tool('wmm_job_cancel',dict(app_id='sample-one',input={},resource_id=queued['id']))
            self.assertTrue(denied.isError)
            prepared=await client.call_tool('wmm_review_prepare',dict(id='mcp-cancel',envelope=envelope))
            self.assertFalse(prepared.isError,prepared.content)
            view=prepared.structuredContent['data'];approved=self.approve(view)
            process,result=self.review_cli('resume',dict(app_id='sample-one',id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
            self.assertEqual(process.returncode,0);self.assertEqual(result['result']['data']['status'],'CANCELLED')
            self.assertFalse(run_once(self.store))
            rows=await client.call_tool('wmm_jobs_read',dict(app_id='sample-one',input={}))
            self.assertEqual(rows.structuredContent['data'][0]['status'],'CANCELLED')
            self.assertIsNone(rows.structuredContent['data'][0]['result'])
