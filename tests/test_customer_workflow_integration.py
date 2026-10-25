"""Actual local HTTP, CSRF, restart and hash-bound workspace portability."""
import copy
from pathlib import Path
import unittest
from tests import test_http
from tests.test_customer_workflow import proposal, prototype
from mission_control.common import Invalid, digest
from mission_control.store import Store
from mission_control.customer_workflow_store import CustomerWorkflows
from tests import test_agent_mcp as mcp_fixture


class CustomerWorkflowIntegrationTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

    def test_prototype_result_cli_http_restart_and_portable_readback(self):
        import json,subprocess,sys
        legacy=self.body()
        original=self.request('/api/apps/sample-one/customer-workflows',legacy)[1]
        body=dict(legacy,id='tested-workflow',data=dict(legacy['data'],prototype_result=prototype()))
        envelope=dict(app_id='sample-one',operation='customer.save',input=body)
        call=subprocess.run([sys.executable,'-m','mission_control.agent_cli','call','--origin',
            'http://127.0.0.1:'+str(self.server.server_port)],input=json.dumps(envelope).encode(),capture_output=True,timeout=30)
        self.assertEqual(call.returncode,0,call.stderr)
        saved=json.loads(call.stdout)
        self.assertEqual(saved['data']['prototype_result'],prototype())
        rows=self.request('/api/apps/sample-one/customer-workflows')[1]['history']
        self.assertEqual(next(r for r in rows if r['id']==original['id'])['hash'],original['hash'])
        self.assertEqual(self.request('/api/apps/sample-one/customer-workflows',body)[1]['hash'],saved['hash'])
        changed=dict(body,id='denied-result',data=dict(body['data'],prototype_result=dict(prototype(),consent=False)))
        self.assertEqual(self.request('/api/apps/sample-one/customer-workflows',changed)[0],400)
        self.assertEqual(len(self.request('/api/apps/sample-one/customer-workflows')[1]['history']),2)
        reopened=Store(self.server.service.store.path,seed=False)
        self.assertEqual(CustomerWorkflows(reopened).list('sample-one')['history'],rows)
        snapshot=reopened.export('sample-one')
        restored=Store(Path(self.tmp.name)/'prototype-restored.sqlite',seed=False);restored.restore(snapshot)
        result=next(r for r in CustomerWorkflows(restored).list('sample-one')['history'] if r['id']==saved['id'])
        self.assertEqual(result['hash'],saved['hash']);self.assertEqual(result['data']['prototype_result'],prototype())
        self.assertFalse(result['readout']['demand_verified'])

    def body(self):
        store = self.server.service.store
        app = store.app("sample-one")
        if app["data"].get("release") != "build-1":
            store.save_app("sample-one", dict(app["data"], release="build-1", locale="en-US", currency="USD"), app["version"])
        return dict(id="workflow-one", manifest_version=store.app("sample-one")["version"], data=proposal())

    def test_http_create_read_replay_scope_and_csrf(self):
        body = self.body()
        route = "/api/apps/sample-one/customer-workflows"
        self.assertEqual(self.request(route, body, headers={"X-CSRF-Token": "wrong"})[0], 403)
        self.assertEqual(self.request(route + "?approve=true", body)[0], 400)
        self.assertEqual(self.request("/api/apps/sample-two/customer-workflows", body)[0], 400)
        code, row, _ = self.request(route, body)
        self.assertEqual(code, 201)
        self.assertEqual(self.request(route, body)[1], row)
        value = self.request(route)[1]
        self.assertEqual(len(value["history"]), 1)
        self.assertFalse(value["demand_verified"])
        self.assertEqual(self.request(route + "?approve=true")[0], 400)
        self.assertEqual(self.request(route + "/execute", body)[0], 400)
        self.assertEqual(self.request(route, raw=b'{"id":"one","id":"two"}')[0], 400)

    def test_workspace_export_restore_preserves_history_without_authority(self):
        self.request("/api/apps/sample-one/customer-workflows", self.body())
        snapshot = self.request("/api/apps/sample-one/export")[1]
        self.assertEqual(len(snapshot["payload"]["customer_workflows"]), 1)
        restored = Store(Path(self.tmp.name) / "recovery/state.sqlite", seed=False)
        restored.restore(snapshot)
        source = CustomerWorkflows(self.server.service.store).list("sample-one")["history"][0]
        target = CustomerWorkflows(restored).list("sample-one")["history"][0]
        self.assertEqual(target["hash"], source["hash"])
        self.assertEqual(target["data"], source["data"])
        self.assertEqual(target["imported"], 1)
        self.assertFalse(target["readout"]["demand_verified"])

    def test_tampered_restore_rolls_back_every_row_and_legacy_snapshots_work(self):
        self.request("/api/apps/sample-one/customer-workflows", self.body())
        snapshot = self.server.service.store.export("sample-one")
        bad = copy.deepcopy(snapshot)
        bad["payload"]["customer_workflows"][0]["data"]["buyer"] = "changed"
        bad["sha256"] = digest(bad["payload"])
        restored = Store(Path(self.tmp.name) / "tampered/state.sqlite", seed=False)
        with self.assertRaises(Invalid):
            restored.restore(bad)
        self.assertEqual(restored.apps(), [])
        legacy = copy.deepcopy(snapshot)
        legacy["payload"].pop("customer_workflows")
        legacy["sha256"] = digest(legacy["payload"])
        restored.restore(legacy)
        self.assertEqual(CustomerWorkflows(restored).list("sample-one")["history"], [])


@unittest.skipUnless(mcp_fixture.HAS_MCP,'Optional MCP SDK is not installed')
class PrototypeMCPTests(unittest.IsolatedAsyncioTestCase):
    setUp=mcp_fixture.MCPSubprocessTests.setUp
    tearDown=mcp_fixture.MCPSubprocessTests.tearDown
    session=mcp_fixture.MCPSubprocessTests.session
    tool=mcp_fixture.MCPSubprocessTests.tool
    data=mcp_fixture.MCPSubprocessTests.data
    call=mcp_fixture.MCPSubprocessTests.call
    cli=mcp_fixture.MCPSubprocessTests.cli

    async def test_mcp_prototype_save_cli_history_and_scoped_denial(self):
        body=dict(id='mcp-prototype',manifest_version=1,data=dict(proposal(),prototype_result=prototype()))
        async with self.session() as client:
            saved=self.data(await self.tool(client,'customer.save',body))
            process,rows=self.call('customer.history')
            self.assertEqual(process.returncode,0)
            self.assertEqual(rows['history'][0]['hash'],saved['hash'])
            self.assertEqual(rows['history'][0]['data']['prototype_result'],prototype())
            denied=await self.tool(client,'customer.save',dict(body,id='denied',manifest_version=99))
            self.assertTrue(denied.isError)
            self.assertEqual(self.data(await self.tool(client,'customer.history',app='sample-two'))['history'],[])
