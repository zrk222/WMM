"""Exercise the study through the owner route and the scoped agent gateway."""

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from mission_control.agent_mcp import execute_tool
from mission_control.operator_client import ClientError, OperatorClient
from tests import test_agent_grants as fixtures


class ObservationalCampaignTransportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixtures.GrantTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        store = self.fixture.store
        app = store.app("sample-one")
        store.save_app(app["id"], dict(app["data"], website="https://example.com/"), app["version"])
        self.version = store.app("sample-one")["version"]
        self.base = "/api/apps/sample-one/observational-campaign/"

    def test_owner_registration_and_scoped_mcp_reads_share_saved_study(self) -> None:
        start = datetime.now(timezone.utc) + timedelta(hours=1)
        registration = dict(
            request_id=str(uuid4()),
            manifest_version=self.version,
            definition=dict(
                id=str(uuid4()),
                name="Tagged landing test",
                hypothesis="Observe tagged registrations",
                source="facebook",
                creative_id="synthetic-reel",
                landing_path="/",
                starts_at=start.isoformat(),
                ends_at=(start + timedelta(days=1)).isoformat(),
                landing_event="page_view",
                registration_event="registration_completed",
                attribution_model="FIRST_TOUCH",
                collector_source_id="owned-events",
            ),
        )
        owner = self.fixture.owner
        saved = owner.request("POST", self.base + "register", registration)
        assert isinstance(saved, dict)
        binding = dict(study_id=saved["study_id"], study_hash=saved["study_hash"], manifest_version=self.version)
        url = owner.request("POST", self.base + "link", binding)
        assert isinstance(url, dict)
        self.assertIn("utm_campaign=" + saved["study_id"], url["url"])
        handoff = url["collector_setup"]
        self.assertEqual(handoff["schema"], "wmm.observational-collector-setup.v1")
        self.assertEqual(handoff["status"], "DECLARED_NOT_VERIFIED")
        self.assertEqual(handoff["app_id"], "sample-one")
        self.assertEqual(handoff["app_version"], self.version)
        self.assertEqual(handoff["study_id"], binding["study_id"])
        self.assertEqual(handoff["study_hash"], binding["study_hash"])
        self.assertEqual(handoff["tagged_url"], url["url"])
        self.assertEqual(handoff["source_id"], "owned-events")
        self.assertEqual(handoff["event_names"], {"LANDING": "page_view", "REGISTRATION": "registration_completed"})
        self.assertEqual(datetime.fromisoformat(handoff["starts_at"]), start)
        self.assertEqual(datetime.fromisoformat(handoff["ends_at"]), start + timedelta(days=1))
        self.assertTrue(handoff["post_close_coverage_required"])
        owner_report = owner.request("POST", self.base + "report", binding)
        assert isinstance(owner_report, dict)
        self.assertIsNone(owner_report["landing_subjects"])
        self.assertIsNone(owner_report["linked_registration_subjects"])
        grant = owner.request(
            "POST",
            "/api/apps/sample-one/agent-grants/issue",
            dict(self.fixture.body(["observational-campaign.link"]), manifest_version=self.version),
        )
        assert isinstance(grant, dict)
        token = grant["token"]
        args = dict(app_id="sample-one", input=binding)
        agent_result = execute_tool(self.fixture.origin, "wmm_observational-campaign_link", args, token)
        self.assertEqual(agent_result, url)
        client = OperatorClient(self.fixture.origin, grant_token=token)
        with self.assertRaises(ClientError) as denied:
            client.call(self.fixture.envelope("observational-campaign.report", binding))
        self.assertEqual(denied.exception.status, 403)
        with self.assertRaises(ClientError) as foreign:
            client.call(self.fixture.envelope("observational-campaign.link", binding, "sample-two"))
        self.assertEqual(foreign.exception.status, 403)

    def test_signed_out_session_cannot_read_private_history(self) -> None:
        owner = self.fixture.owner
        owner.request("POST", "/api/identity/logout", {})
        with self.assertRaises(ClientError) as denied:
            owner.request("POST", self.base + "history", {})
        self.assertEqual(denied.exception.status, 403)
