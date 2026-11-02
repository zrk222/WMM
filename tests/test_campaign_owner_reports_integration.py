"""Private report HTTP and real background worker retain owner authority."""
import json
import unittest
from mission_control.db import connection
from mission_control.server import owner_domain_post
from mission_control import campaign_owner_reports as reports
from tests import test_campaign_owner_reports as report_fixtures

class ReportIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.f = report_fixtures.CampaignOwnerReportsTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store = self.f.store
        self.client = self.f.fixture.client
        self.base = "/api/apps/sample/campaign-owner-reports/"

    def test_actual_owner_router_and_logged_out_worker_report(self):
        self.assertEqual(owner_domain_post(["api","apps","sample","campaign-owner-reports","history"]).__module__, "mission_control.campaign_owner_reports")
        plan = self.f.plan()
        # Isolate local report generation from the separately approved provider monitor.
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='OFF'")
        self.client.request("POST", "/api/identity/logout", {})
        self.assertTrue(self.f.fixture.server.runner.poll())
        with connection(self.store.path) as db:
            job = db.execute("SELECT * FROM jobs WHERE action='campaign_owner_report'").fetchone()
            self.assertEqual(job["status"], "SUCCEEDED")
            saved = json.loads(job["result"])
            self.assertEqual(saved["report"]["visibility"], "PRIVATE_OWNER_ONLY")
            self.assertFalse(saved["report"]["authority_issued"])
            self.assertEqual(saved["plan_id"], plan["id"])
            self.assertEqual(db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0], 1)
        self.assertIn("owner_reports", self.f.fixture.server.runner.health["components"])

    def test_real_http_capture_read_and_off_report_plan(self):
        body = {"selection": self.f.chosen(), "request_key": "88888888-8888-4888-8888-888888888888"}
        saved = self.client.request("POST", self.base+"capture", body)
        reread = self.client.request("POST", self.base+"read", {"report_id":saved["id"]})
        self.assertEqual(saved["hash"], reread["hash"])
        plan = self.f.plan()
        off = self.client.request("POST", self.base+"off", {"plan_id":plan["id"],"version":plan["version"]})
        self.assertEqual(off["status"], "OFF")
        self.assertEqual(reports.tick(self.store), 0)

if __name__ == "__main__":
    unittest.main()
