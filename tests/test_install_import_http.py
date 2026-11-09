"""Owner HTTP preview/confirm for the install import; no browser dependency."""
import unittest
from mission_control.operator_client import ClientError
from tests.test_agent_grants import GrantTests

CAMPAIGN = "11111111-1111-4111-8111-111111111111"
REQUEST = "22222222-2222-4222-8222-222222222222"


class InstallImportHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fx = GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)

    def payload(self, event="install"):
        return dict(text="id,event,time\ninstall_a," + event + ",2026-11-02T00:00:00+00:00\n",
                    format="csv", mapping=dict(install_id="id", state="event", occurred_at="time",
                                               state_values={"install": "ATTRIBUTED", "organic": "UNATTRIBUTED"}),
                    source="APPSFLYER", campaign_token=CAMPAIGN, request_id=REQUEST,
                    observed_at="2026-11-10T00:00:00+00:00",
                    window=dict(starts_at="2026-11-01T00:00:00+00:00", ends_at="2026-11-08T00:00:00+00:00"),
                    coverage=dict(complete=True, source_event_count=1))

    def test_preview_then_confirm_records_once_and_updates_summary(self):
        preview = self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/preview",
                                        self.payload())
        self.assertEqual(preview["checklist"]["status"], "READY")
        self.assertEqual(preview["batch"]["installs"][0]["install_id"], "install_a")
        confirm = self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/confirm",
                                        self.payload())
        self.assertEqual(confirm["result"]["inserted"], 1)
        again = self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/confirm",
                                      self.payload())
        self.assertEqual(again["result"]["status"], "ALREADY_RECORDED")
        summary = self.fx.server.service.workspace("sample-one")["install_attribution"]
        self.assertEqual(summary["campaigns"][0]["campaign_token"], CAMPAIGN)

    def test_blocked_preview_and_confirm_do_not_write(self):
        blocked = self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/preview",
                                        self.payload("purchase"))
        self.assertEqual(blocked["checklist"]["status"], "BLOCKED")
        self.assertIsNone(blocked["batch"])
        with self.assertRaises(ClientError):
            self.fx.owner.request("POST", "/api/apps/sample-one/install-attribution/imports/confirm",
                                  self.payload("purchase"))


if __name__ == "__main__":
    unittest.main()
