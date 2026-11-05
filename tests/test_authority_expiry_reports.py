"""Campaign owner reports reflect effective expiry consent without widening child clocks."""

from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from mission_control.authority_expiry import AuthorityExpiry
from mission_control.common import canonical
from mission_control.db import connection
from tests import test_campaign_owner_reports as fixture


class AuthorityExpiryReportTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.CampaignOwnerReportsTests(
            "test_private_report_immutable_hash_missing_kpis_and_no_effects"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.store = self.fixture.store

    def test_extended_permission_is_reported_without_rewriting_original_or_children(self):
        plan = self.fixture.plan()
        before = self.fixture.capture()
        original_expiry = before["report"]["campaign"]["expires_at"]
        transport = self.fixture.fixture.wire
        provider_state = (transport.posts, canonical(transport.objects))
        with connection(self.store.path) as db:
            plan_before = db.execute(
                "SELECT summary FROM campaign_report_plans WHERE id=?", (plan["id"],)
            ).fetchone()["summary"]
            monitor_before = db.execute(
                "SELECT summary FROM campaign_monitors WHERE id=?",
                (self.fixture.monitor["id"],),
            ).fetchone()["summary"]

        owner = dict(principal="owner", login="owner")
        expiry = AuthorityExpiry(self.store)
        review = expiry.preview(
            "sample",
            owner,
            dict(
                kind="CAMPAIGN",
                id=self.fixture.fixture.scope["scope_id"],
                expires=(datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
            ),
        )
        consent = expiry.confirm(
            "sample",
            owner,
            dict(
                **review,
                request_id="report-expiry-extension-1",
                extended_expiry_consent=True,
            ),
        )

        original_deadline_plus_one = datetime.fromisoformat(original_expiry) + timedelta(seconds=1)
        with patch("mission_control.campaign_owner_reports.now", return_value=original_deadline_plus_one.isoformat()):
            current = self.fixture.capture()
        campaign = current["report"]["campaign"]
        self.assertEqual(consent["receipt"]["revision"], 1)
        self.assertEqual(campaign["expires_at"], original_expiry)
        self.assertEqual(campaign["permission_expires_at"], review["preview"]["new_expiry"])
        self.assertEqual(campaign["consent_revision"], 1)
        self.assertEqual(campaign["status"], "ACTIVE")
        self.assertNotIn("historical", current["report"]["next_action"])
        self.assertNotEqual(current["hash"], before["hash"])
        self.assertEqual((transport.posts, canonical(transport.objects)), provider_state)

        with connection(self.store.path) as db:
            self.assertEqual(
                db.execute(
                    "SELECT summary FROM campaign_report_plans WHERE id=?", (plan["id"],)
                ).fetchone()["summary"],
                plan_before,
            )
            self.assertEqual(
                db.execute(
                    "SELECT summary FROM campaign_monitors WHERE id=?",
                    (self.fixture.monitor["id"],),
                ).fetchone()["summary"],
                monitor_before,
            )
        with self.fixture.owner():
            self.assertEqual(self.fixture.reports.read("sample", before["id"]), before)

        future = datetime.fromisoformat(campaign["permission_expires_at"]) + timedelta(seconds=1)
        with patch("mission_control.campaign_owner_reports.now", return_value=future.isoformat()):
            expired = self.fixture.capture()
        self.assertEqual(expired["report"]["campaign"]["permission_expires_at"], campaign["permission_expires_at"])
        self.assertIn("historical", expired["report"]["next_action"])

        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_scopes SET status='REVOKED' WHERE id=?", (self.fixture.fixture.scope["scope_id"],))
        revoked = self.fixture.capture()
        self.assertEqual(revoked["report"]["campaign"]["status"], "REVOKED")
        self.assertIn("historical", revoked["report"]["next_action"])


if __name__ == "__main__":
    unittest.main()
