"""Read-only protocol discovery through the actual isolated loopback server."""
import unittest
import time
from unittest.mock import patch
from tests import test_http
from mission_control.agent_operations import discovery
from mission_control.common import digest


class AgentOperationTests(unittest.TestCase):
    setUp = test_http.HTTPTests.setUp
    tearDown = test_http.HTTPTests.tearDown
    request = test_http.HTTPTests.request

    def test_discovery_exact_scope_hashes_and_no_authority(self):
        app = self.server.service.store.app("sample-one")
        expected = discovery(app)
        code, result, _ = self.request("/api/apps/sample-one/agent-operations")
        self.assertEqual(code, 200)
        self.assertEqual(result, expected)
        self.assertEqual(result["app_hash"], digest(app["data"]))
        self.assertFalse(result["execution_authority"])
        self.assertFalse(result["resolution_execution"]["independent_human_approval_enforced"])
        self.assertFalse(result["coverage"]["complete_autonomous_operation"])
        self.assertEqual(result["coverage"]["feedback_missing_tools"], ["discover_setup", "inspect_tracking"])
        unsigned = {k: v for k, v in result.items() if k != "contract_sha256"}
        self.assertEqual(result["contract_sha256"], digest(unsigned))

    def test_query_path_and_unknown_app_rejected_without_mutation(self):
        before = self.server.service.store.export("sample-one")
        for route in ("/api/apps/absent/agent-operations", "/api/apps/sample-one/agent-operations?approve=true",
                      "/api/apps/sample-one/agent-operations/execute"):
            self.assertNotEqual(self.request(route)[0], 200)
        self.assertEqual(self.request("/api/apps/sample-one/agent-operations", {"approved": True})[0], 404)
        after = self.server.service.store.export("sample-one")
        self.assertEqual(before["payload"], after["payload"])
        self.assertEqual(before["sha256"], after["sha256"])

    def test_manifest_change_invalidates_discovery_hash(self):
        first = self.request("/api/apps/sample-one/agent-operations")[1]
        store = self.server.service.store
        app = store.app("sample-one")
        store.save_app("sample-one", dict(app["data"], job="A changed synthetic objective"), app["version"])
        second = self.request("/api/apps/sample-one/agent-operations")[1]
        self.assertNotEqual(first["contract_sha256"], second["contract_sha256"])
        self.assertNotEqual(first["policy_sha256"], second["policy_sha256"])

    def test_discovery_does_not_export_private_records(self):
        store = self.server.service.store
        store.save_record("sample-one", dict(kind="measurement", title="Synthetic confidential evidence",
            source="Private synthetic source", data={"private_marker": "SYNTHETIC_PRIVATE_RECORD"}))
        result = self.request("/api/apps/sample-one/agent-operations")[1]
        self.assertNotIn("SYNTHETIC_PRIVATE_RECORD", str(result))
        self.assertNotIn("Private synthetic source", str(result))

    def test_discovery_is_bounded_and_performs_no_provider_calls(self):
        app = self.server.service.store.app("sample-one")
        started = time.perf_counter()
        with patch("socket.socket") as network:
            for _ in range(100):
                self.assertEqual(len(discovery(app)["supported_resolution_tools"]), 7)
            network.assert_not_called()
        self.assertLess(time.perf_counter() - started, 5)
