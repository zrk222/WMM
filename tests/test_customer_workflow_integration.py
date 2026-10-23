"""Actual local HTTP, CSRF, restart and hash-bound workspace portability."""
import copy
from pathlib import Path
import unittest
from tests import test_http
from tests.test_customer_workflow import proposal
from mission_control.common import Invalid, digest
from mission_control.store import Store
from mission_control.customer_workflow_store import CustomerWorkflows


class CustomerWorkflowIntegrationTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

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
