"""Real scoped CLI/MCP use existing immutable growth.save for market snapshots."""

import json
import unittest
from mission_control.operator_client import ClientError
from tests import test_agent_grants as fixture
from tests import test_video_edit_clients as editing
from tests import test_agent_mcp as sdk
from tests.test_market_research import fixture as research_fixture


class MarketResearchClientTests(unittest.IsolatedAsyncioTestCase):
    setUp = fixture.GrantTests.setUp
    tearDown = fixture.GrantTests.tearDown
    body = fixture.GrantTests.body
    envelope = fixture.GrantTests.envelope
    grant = editing.VideoClientsTests.grant
    cli = editing.VideoClientsTests.cli
    session = editing.VideoClientsTests.session

    @unittest.skipUnless(sdk.HAS_MCP, "Official MCP SDK required for two-client conformance")
    async def test_cli_save_mcp_read_and_identical_replay_share_one_source(self):
        self.grant(["growth.save", "growth.read"])
        body = research_fixture()
        saved = self.cli(self.envelope("growth.save", body))
        self.assertEqual(saved["kind"], "MARKET_RESEARCH")
        async with self.session() as client:
            catalog = await client.call_tool("wmm_catalog", {})
            self.assertEqual(
                catalog.structuredContent["data"]["domain_contracts"]["market_research"]["kind"], "MARKET_RESEARCH"
            )
            result = await client.call_tool("wmm_growth_read", dict(app_id="sample-one", input={}))
            self.assertFalse(result.isError, result.content)
            value = result.structuredContent["data"]
            self.assertEqual(len(value["history"]["history"]), 1)
            self.assertEqual(value["history"]["history"][0]["hash"], saved["hash"])
            self.assertIsNone(value["history"]["history"][0]["readout"]["analysis"]["candidates"][0]["metrics"]["rank"])
            again = await client.call_tool("wmm_growth_save", dict(app_id="sample-one", input=body))
            self.assertFalse(again.isError, again.content)
            self.assertEqual(again.structuredContent["data"]["hash"], saved["hash"])
            wrong = await client.call_tool("wmm_growth_save", dict(app_id="sample-two", input=body))
            self.assertTrue(wrong.isError)
        self.assertNotIn(self.token, json.dumps(value))
        self.assertEqual(len(self.cli(self.envelope("growth.read"))["history"]["history"]), 1)

    def test_no_write_grant_cannot_adopt_research(self):
        agent = self.grant(["growth.read"])
        with self.assertRaises(ClientError):
            agent.call(self.envelope("growth.save", research_fixture()))
        self.assertEqual(agent.call(self.envelope("growth.read"))["history"]["history"], [])
