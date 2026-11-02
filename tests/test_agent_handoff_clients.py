"""CLI and MCP share the retained handoff and original worker identity."""
import json
import unittest
from mission_control.worker import enqueue
from tests import test_agent_handoffs as fixture
from tests import test_agent_grant_clients as clients
from tests import test_agent_mcp as sdk


class HandoffClientTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixture.HandoffTests.setUp
    tearDown=fixture.HandoffTests.tearDown
    body=fixture.HandoffTests.body
    issue=fixture.HandoffTests.issue
    envelope=fixture.HandoffTests.envelope
    grant=fixture.HandoffTests.grant
    create=fixture.HandoffTests.create
    cli=clients.GrantClientTests.cli
    session=clients.GrantClientTests.session

    @unittest.skipUnless(sdk.HAS_MCP,'Optional MCP SDK required for cross-client acceptance')
    async def test_cli_and_mcp_resume_same_record_without_requeue(self):
        job=enqueue(self.store,'sample-one','pipeline',dict(stage=1),'private-original-key')
        saved=self.create(job);issued=self.grant('replacement',['handoff.resume','jobs.read'])
        envelope=dict(app_id='sample-one',operation='handoff.resume',resource_id=saved['id'],
                      input=dict(version=saved['version'],payload_hash=saved['payload_hash']))
        process,result=self.cli(envelope,issued['token'])
        self.assertEqual(process.returncode,0,process.stderr)
        self.assertEqual(result['job_id'],job['id'])
        async with self.session(issued['token']) as client:
            value=await client.call_tool('wmm_handoff_resume',dict(app_id='sample-one',resource_id=saved['id'],input=envelope['input']))
            self.assertFalse(value.isError,value.content)
            self.assertEqual(value.structuredContent['data']['job_id'],job['id'])
            self.assertNotIn('private-original-key',json.dumps(value.structuredContent))


if __name__=='__main__':unittest.main()
