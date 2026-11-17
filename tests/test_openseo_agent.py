"""Real scoped agent dispatch and HTTP privacy for native OpenSEO reads."""

import json
import unittest
from unittest.mock import patch

from mission_control.operator_client import ClientError, OperatorClient
from mission_control.store import Store
from tests.test_agent_grants import GrantTests
from tests.test_measurement_connectors import FakeVault
from tests.test_openseo_read import provider_reply, setup


class OpenSEOAgentTests(unittest.TestCase):
    store: Store
    owner: OperatorClient
    origin: str
    setUp = GrantTests.setUp
    tearDown = GrantTests.tearDown
    body = GrantTests.body

    def test_scoped_agent_reads_and_saves_exact_native_evidence(self):
        app = self.store.app("sample-one")
        self.store.save_app("sample-one", dict(app["data"], website="https://sample.example"), app["version"])
        FakeVault.values, FakeVault.fail_delete = {}, 0
        with (
            patch("mission_control.insights.Vault", FakeVault),
            patch("mission_control.openseo_transport.call_tool", side_effect=provider_reply),
        ):
            connected = self.owner.request("POST", "/api/apps/sample-one/insights/setup", setup())
            assert connected is not None
            sid = connected["source_id"]
            grant_body = dict(self.body(["web.research.read", "web.research.save"]), manifest_version=2)
            grant = self.owner.request("POST", "/api/apps/sample-one/agent-grants/issue", grant_body)
            assert grant is not None
            agent = OperatorClient(self.origin, grant_token=grant["token"])
            read = agent.call(
                dict(app_id="sample-one", operation="web.research.read", resource_id=sid, input={"confirm_read": True})
            )
            assert read is not None
            self.assertEqual(read["status"], "CONNECTED")
            workspace = self.owner.request("GET", "/api/apps/sample-one")
            assert workspace is not None
            sources = workspace["insights"]
            report = sources["reports"][0]
            result = agent.call(
                dict(
                    app_id="sample-one",
                    operation="web.research.save",
                    resource_id=sid,
                    input=dict(id="agent-web-result", manifest_version=2, report_id=report["id"]),
                )
            )
            assert result is not None
            self.assertEqual(result["kind"], "WEB_SEO_EVIDENCE")
            self.assertNotIn(setup()["api_key"], json.dumps(result))
            with self.assertRaises(ClientError) as cross_app:
                agent.call(
                    dict(
                        app_id="sample-two",
                        operation="web.research.read",
                        resource_id=sid,
                        input={"confirm_read": True},
                    )
                )
            self.assertEqual(cross_app.exception.status, 403)
