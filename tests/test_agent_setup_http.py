"""Owner-only offline host setup report over the exact running loopback origin."""

import threading
import unittest
from unittest.mock import patch

from mission_control.operator_client import ClientError, OperatorClient
from mission_control.review_access import Access
from mission_control.server import Server
from tests import test_complete_automation as fixtures
from tests import test_verified_review as identities


class AgentSetupHttpTests(fixtures.AuthorityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_authority()
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = "http://127.0.0.1:" + str(self.server.server_port)
        self.identity_patch = patch(
            "mission_control.operator_identity.github_read",
            side_effect=identities.synthetic_identity,
        )
        self.identity_patch.start()
        self.owner = OperatorClient(self.origin)
        self.owner.bootstrap()
        self.owner.request("POST", "/api/identity/login", dict(token=identities.OWNER_TOKEN))

    def tearDown(self):
        self.identity_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.cleanup_authority()

    def test_setup_is_current_owner_only_uses_server_origin_and_is_read_only(self):
        before = self.fixture.dump()
        result = self.owner.request("POST", "/api/apps/sample-one/agent-grants/setup", {})
        self.assertEqual(result["origin"], self.origin)
        self.assertEqual(result["runtime_kind"], "SOURCE_PYTHON")
        self.assertEqual(result["authority"], "OWNER_ISSUED_SCOPED_GRANT_REQUIRED_FOR_GENERATED_CONFIG")
        config = result["mcp_config"]["mcpServers"]["wmm-local"]
        self.assertIn("--use-grant", config["args"])
        self.assertNotIn("WMM_AGENT_GRANT", config["env"])
        self.assertEqual(before, self.fixture.dump())

    def test_setup_rejects_non_owner_client_origin_body_and_query(self):
        Access(self.store).save(
            "sample-one",
            identities.OWNER,
            identities.CHECKER,
            dict(login=identities.CHECKER["login"], role="CHECKER", status="ACTIVE", version=None),
        )
        checker = OperatorClient(self.origin)
        checker.bootstrap()
        checker.request("POST", "/api/identity/login", dict(token=identities.CHECKER_TOKEN))
        with self.assertRaises(ClientError) as rejected:
            checker.request("POST", "/api/apps/sample-one/agent-grants/setup", {})
        self.assertEqual(rejected.exception.status, 403)

        with self.assertRaises(ClientError) as rejected:
            self.owner.request(
                "POST",
                "/api/apps/sample-one/agent-grants/setup",
                dict(origin="http://127.0.0.1:1"),
            )
        self.assertEqual(rejected.exception.status, 400)
        with self.assertRaises(ClientError) as rejected:
            self.owner.request("POST", "/api/apps/sample-one/agent-grants/setup?origin=http://127.0.0.1:1", {})
        self.assertEqual(rejected.exception.status, 400)
