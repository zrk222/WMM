"""Real loopback access API; fixtures never call a paid inference endpoint."""
import json,unittest,uuid
from unittest.mock import patch
from tests import test_http as fixtures
from tests.test_measurement_connectors import FakeVault
from tests.test_agent_access import body,answer
from mission_control.worker import run_once


class AgentHTTPTests(unittest.TestCase):
    setUp=fixtures.HTTPTests.setUp
    tearDown=fixtures.HTTPTests.tearDown

    def request(self,path,body=None,headers=None,raw=None):
        return fixtures.HTTPTests.request(self,path,body,{'Content-Type':'application/json',**(headers or {})},raw)

    def test_setup_scope_secret_redaction_exact_requests_and_disconnect(self):
        FakeVault.values={};base='/api/apps/sample-one/agent-access'
        with patch('mission_control.agent_access.Vault',FakeVault):
            self.assertEqual(self.request(base+'/save',body(),{'X-CSRF-Token':'wrong'})[0],403)
            self.assertEqual(self.request(base+'/save?extra=true',body())[0],400)
            self.assertEqual(self.request(base+'/save',{**body(),'command':'bad'})[0],400)
            duplicate=json.dumps(body())[:-1]+',"label":"duplicate"}'
            self.assertEqual(self.request(base+'/save',raw=duplicate.encode())[0],400)
            self.assertEqual(self.request(base+'/save',body(),{'Content-Type':'text/plain'})[0],400)
            code,saved,_=self.request(base+'/save',body());self.assertEqual(code,200)
            identity=saved['connection'];workspace=self.request('/api/apps/sample-one')[1]
            self.assertNotIn(body()['api_key'],json.dumps(workspace))
            self.assertNotIn('credential_ref',json.dumps(workspace['agent_access']))
            self.assertEqual(self.request('/api/apps/sample-two/agent-access/'+identity+'/disconnect',{'version':1})[0],400)
            self.assertEqual(self.request(base+'/'+identity+'/disconnect',{'version':1})[0],200)
            self.assertEqual(self.request(base+'/cleanup',{})[0],200)
            self.assertEqual(self.request(base+'/cleanup',{'reference':'foreign'})[0],400)
            self.assertFalse(FakeVault.values)

    def test_detect_is_explicit_and_never_returns_native_paths(self):
        found=dict(version='0.162.1',fingerprint='synthetic',login_state='SIGNED_IN',quota='UNKNOWN',
                   account_identity='NOT_INDEPENDENTLY_VERIFIED',executable='PRIVATE PATH')
        with patch('mission_control.agent_native.identity',return_value=found) as detect:
            self.request('/api/apps/sample-one');detect.assert_not_called()
            code,result,_=self.request('/api/apps/sample-one/agent-access/detect',{'provider':'codex'})
            self.assertEqual(code,200);self.assertNotIn('PRIVATE',json.dumps(result));detect.assert_called_once_with('codex')
        self.assertEqual(self.request('/api/apps/sample-one/agent-access/run-arbitrary',{})[0],404)

    def test_proposal_approval_durable_result_and_no_publication(self):
        FakeVault.values={};base='/api/apps/sample-one/agent-access'
        with patch('mission_control.agent_access.Vault',FakeVault):
            saved=self.request(base+'/save',body())[1]
            data=dict(task='connection_test',focus='',connection_id=saved['connection'])
            preview=self.request(base+'/proposal',data)[1]
            request={**data,'source_hash':preview['source_hash'],'request_key':str(uuid.uuid4())}
            self.assertEqual(self.request('/api/apps/sample-two/agent-access/approve',request)[0],400)
            job=self.request(base+'/approve',request)[1]
            with patch('mission_control.agent_tasks.api_run',return_value=(dict(summary='Connection test',items=[],unknowns=[]),{})):
                self.assertTrue(run_once(self.server.service.store))
            again=self.request(base+'/approve',request)[1];self.assertEqual(again['id'],job['id'])
            workspace=self.request('/api/apps/sample-one')[1]
            self.assertEqual(workspace['agent_access']['profiles'][0]['status'],'TESTED')
            self.assertEqual(again['result']['publication'],'NOT_RUN')
            self.assertEqual(self.request('/agent-access.js')[0],200)


if __name__=='__main__':unittest.main()
