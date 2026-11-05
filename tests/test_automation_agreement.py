"""Real SQLite/HTTP agreement review; no live providers, credentials or effects.

The combined API exercises build_summary, local_scope, campaign_scope,
campaign_blockers, campaign_receipts, batch_row, batch_scope, batch_item and
item_view against persisted resources. Static names aid scoped QA routing;
the HTTP/SQLite assertions supply behavioral evidence.
"""

from datetime import datetime, timedelta
import threading
import unittest
from unittest.mock import patch

from mission_control.automation_agreement import (
    Agreement,
    selection,
    saved_object,
    owned,
)
from mission_control.campaign_execution import SCHEMA
from mission_control.campaign_schedule import SCHEMA as SCHEDULE_SCHEMA
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.operator_client import OperatorClient, ClientError
from mission_control.server import Server
from tests.test_complete_automation import AuthorityFixture
from tests import test_verified_review as identities

SCOPE = "44444444-4444-4444-8444-444444444444"
BATCH = "55555555-5555-4555-8555-555555555555"
ITEM = "66666666-6666-4666-8666-666666666666"
REQUEST = "77777777-7777-4777-8777-777777777777"


class AutomationAgreementTests(AuthorityFixture, unittest.TestCase):
    def setUp(self):
        self.setup_authority()
        self.addCleanup(self.cleanup_authority)
        self.issued = self.activate()
        self.agreement = Agreement(self.store, clock=lambda: self.observed)
        self.post = dict(
            request_id=REQUEST,
            message="Exact synthetic post",
            link=None,
            rights_hash="b" * 64,
        )
        self.post["content_hash"] = digest(
            dict(message=self.post["message"], link=None)
        )
        self.campaign_fixture()

    def campaign_fixture(self):
        app = self.store.app("sample-one")
        from tests.test_automation_requirements import ACCOUNT

        self.account_id = ACCOUNT
        scope = dict(
            connection_id=ACCOUNT,
            page_id="123",
            ad_account_id=None,
            currency="CAD",
            expires_at=(self.observed + timedelta(hours=1)).isoformat(),
            max_posts=1,
            max_calls=50,
            max_campaigns=0,
            max_campaign_minor=0,
            max_total_minor=0,
            approved_content_hashes=[self.post["content_hash"]],
            approved_rights_hashes=["b" * 64],
            approved_targeting_hashes=[],
            billing_acknowledged=False,
            ordinary_ad_attestation=False,
            app_id="sample-one",
            app_hash=digest(app["data"]),
            app_version=1,
            owner_principal=identities.OWNER["principal"],
            owner_version=1,
            connection_version=1,
            billing_notice="Media excludes fees and taxes; reports may lag.",
            rights_notice="Owner attestations only.",
        )
        item = dict(
            item_id=ITEM,
            due_at=(self.observed + timedelta(minutes=5)).isoformat(),
            request=self.post,
        )
        batch = dict(
            batch_id=BATCH,
            app_id="sample-one",
            owner=identities.OWNER["principal"],
            scope_id=SCOPE,
            scope_hash=digest(scope),
            items=[item],
        )
        self.scope, self.batch = scope, batch
        with connection(self.store.path) as db:
            db.executescript(SCHEMA + SCHEDULE_SCHEMA)
            db.execute(
                "INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                (
                    "sample-one",
                    "facebook",
                    1,
                    "{}",
                    "PRIVATE-CONFIG",
                    "CONFIGURED",
                    self.observed.isoformat(),
                    self.observed.isoformat(),
                ),
            )
            data = dict(
                destination=dict(id="123", name="Synthetic Page"),
                facts=dict(
                    reported_scopes=["pages_manage_posts"],
                    renewal="OFFICIAL_REAUTHORIZATION",
                ),
                last_read_at=self.observed.isoformat(),
                access_token="PRIVATE-TOKEN",
            )
            db.execute(
                "UPDATE social_connections SET provider='facebook',data=?,expires=? WHERE id=?",
                (canonical(data), self.observed.timestamp() + 3600, ACCOUNT),
            )
            db.execute(
                "INSERT INTO campaign_scopes VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample-one",
                    SCOPE,
                    identities.OWNER["principal"],
                    1,
                    canonical(scope),
                    digest(scope),
                    "ACTIVE",
                    0,
                    self.observed.isoformat(),
                    self.observed.isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    BATCH,
                    "sample-one",
                    identities.OWNER["principal"],
                    SCOPE,
                    canonical(batch),
                    digest(batch),
                    "ACTIVE",
                    2,
                    self.observed.isoformat(),
                    self.observed.isoformat(),
                ),
            )
            db.execute(
                "INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    ITEM,
                    BATCH,
                    datetime.fromisoformat(item["due_at"]).timestamp(),
                    canonical(item),
                    digest(item),
                    "READY",
                    None,
                    self.observed.isoformat(),
                    self.observed.isoformat(),
                ),
            )

    def body(self, **changes):
        return dict(
            dict(
                manifest_version=1,
                workflow_policy_id=self.issued["policy_id"],
                campaign_scope_id=SCOPE,
                schedule_batch_id=BATCH,
            ),
            **changes,
        )

    def preview(self, **changes):
        return self.agreement.preview(
            "sample-one", identities.OWNER, self.body(**changes)
        )

    def test_combined_review_snapshot_independent_scopes_and_read_only(self):
        before = self.fixture.dump()
        with (
            patch(
                "mission_control.agent_access.AgentAccess.secret",
                side_effect=AssertionError("No secrets"),
            ),
            patch(
                "mission_control.campaign_transport.MetaTransport.request",
                side_effect=AssertionError("No network"),
            ),
        ):
            result = self.preview()
        summary = result["summary"]
        self.assertEqual(result["summary_hash"], digest(summary))
        self.assertEqual(result["status"], "success")
        self.assertFalse(result["authority_issued"])
        self.assertFalse(summary["execution_authority"])
        self.assertEqual(summary["local_work"]["spend_limit_minor"], 0)
        self.assertEqual(summary["campaign"]["approval"]["currency"], "CAD")
        self.assertEqual(summary["campaign"]["approval_hash"], digest(self.scope))
        self.assertEqual(summary["schedule"]["items"][0]["request"], self.post)
        self.assertEqual(summary["schedule"]["summary_hash"], digest(self.batch))
        self.assertEqual(before, self.fixture.dump())
        for secret in (
            "PRIVATE-TOKEN",
            "PRIVATE-CONFIG",
            "synthetic-private-marker-never-public",
            "secret_ref",
            "credential_ref",
        ):
            self.assertNotIn(secret, canonical(result))
        self.assertIn("MAY_LAG", canonical(summary["pricing"]))

    def test_selection_boundary_closed_fields_owner_and_manifest(self):
        for body in (
            self.body(principal="forged"),
            self.body(manifest_version=True),
            self.body(
                workflow_policy_id=None, campaign_scope_id=None, schedule_batch_id=None
            ),
            self.body(manifest_version=2),
            self.body(campaign_scope_id="malformed"),
        ):
            with self.subTest(body=body), self.assertRaises(Invalid):
                self.agreement.preview("sample-one", identities.OWNER, body)
        with self.assertRaises(PermissionError):
            self.agreement.preview("sample-one", identities.STRANGER, self.body())
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_scopes SET owner=?",
                (identities.STRANGER["principal"],),
            )
        with self.assertRaises(Invalid):
            self.preview()

    def test_each_resource_requires_owner_and_exact_app(self):
        for table in (
            "automation_policies",
            "campaign_scopes",
            "campaign_schedule_batches",
        ):
            with self.subTest(table=table):
                with connection(self.store.path) as db:
                    db.execute(
                        "UPDATE " + table + " SET owner=?",
                        (identities.STRANGER["principal"],),
                    )
                with self.assertRaises(Invalid):
                    self.preview()
                with connection(self.store.path) as db:
                    db.execute(
                        "UPDATE " + table + " SET owner=?",
                        (identities.OWNER["principal"],),
                    )
        with self.assertRaises(Invalid):
            self.agreement.preview("sample-two", identities.OWNER, self.body())

    def test_batch_dependency_and_changed_summary_are_not_silently_omitted(self):
        derived = self.preview(campaign_scope_id=None)
        self.assertEqual(derived["summary"]["campaign"]["id"], SCOPE)
        with self.assertRaises(Invalid):
            self.preview(campaign_scope_id="88888888-8888-4888-8888-888888888888")
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_schedule_batches SET summary_hash='bad'")
        with self.assertRaises(Invalid):
            self.preview()

    def test_current_revisions_expiry_and_missing_freshness_are_explicit(self):
        original = self.preview()["summary_hash"]
        with connection(self.store.path) as db:
            db.execute("UPDATE social_connections SET expires=NULL,version=version+1")
        changed = self.preview()
        self.assertNotEqual(changed["summary_hash"], original)
        self.assertEqual(changed["status"], "warning")
        self.assertIn(
            "CAMPAIGN_CONNECTION_CHANGED", changed["summary"]["campaign"]["blockers"]
        )
        self.assertIn(
            "CAMPAIGN_ACCOUNT_EXPIRY_UNKNOWN",
            changed["summary"]["campaign"]["blockers"],
        )
        late = Agreement(
            self.store, clock=lambda: self.observed + timedelta(hours=2)
        ).preview("sample-one", identities.OWNER, self.body())
        self.assertIn("CAMPAIGN_SCOPE_EXPIRED", late["summary"]["campaign"]["blockers"])

    def test_tampered_due_post_or_scope_binding_rejects(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE campaign_schedule_items SET due=0")
        with self.assertRaises(Invalid):
            self.preview()
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_schedule_items SET due=?",
                (datetime.fromisoformat(self.batch["items"][0]["due_at"]).timestamp(),),
            )
            db.execute("UPDATE campaign_scopes SET summary_hash='changed'")
        with self.assertRaises(Invalid):
            self.preview()

    def test_job_receipts_uncertainty_and_job_binding_are_preserved(self):
        data = dict(batch_id=BATCH, item_id=ITEM, scope_id=SCOPE, request=self.post)
        stamp = self.observed.isoformat()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                (
                    "agreement-job",
                    "sample-one",
                    "campaign_post",
                    canonical(data),
                    "UNKNOWN",
                    stamp,
                    stamp,
                    "agreement-request",
                ),
            )
            db.execute(
                "UPDATE campaign_schedule_items SET job_id='agreement-job',status='QUEUED'"
            )
        result = self.preview()
        self.assertTrue(result["summary"]["dispatch_uncertain"])
        self.assertEqual(result["status"], "warning")
        self.assertEqual(
            result["summary"]["schedule"]["items"][0]["job_status"], "UNKNOWN"
        )
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET app_id='sample-two' WHERE id='agreement-job'")
        with self.assertRaises(Invalid):
            self.preview()

    def test_inactive_policy_quota_owner_revision_and_blocked_jobs_stay_visible(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE automation_policies SET status='OFF'")
            db.execute("UPDATE campaign_scopes SET calls=50,owner_version=2")
            db.execute("UPDATE campaign_schedule_items SET status='BLOCKED'")
        result = self.preview()
        summary = result["summary"]
        self.assertEqual(result["status"], "warning")
        self.assertEqual(summary["local_work"]["effective_status"], "OFF")
        self.assertIn(
            "CAMPAIGN_CALL_ALLOWANCE_EXHAUSTED", summary["campaign"]["blockers"]
        )
        self.assertIn("CAMPAIGN_OWNER_CHANGED", summary["campaign"]["blockers"])
        self.assertIn("SCHEDULE_ITEM_NEEDS_REVIEW", summary["schedule"]["blockers"])
        self.assertEqual(len(summary["schedule"]["items"]), 1)

    def test_single_snapshot_does_not_mix_concurrent_app_revision(self):
        from mission_control import automation_agreement as core

        original = core.campaign_scope

        def change_after_snapshot(db, app, owner, identity, observed):
            with connection(self.store.path) as writer:
                writer.execute(
                    "UPDATE apps SET version=version+1 WHERE id='sample-one'"
                )
            return original(db, app, owner, identity, observed)

        with patch.object(core, "campaign_scope", side_effect=change_after_snapshot):
            result = self.preview()
        self.assertEqual(result["summary"]["app"]["version"], 1)
        self.assertNotIn(
            "CAMPAIGN_APP_CHANGED", result["summary"]["campaign"]["blockers"]
        )
        with self.assertRaises(Invalid):
            self.preview()

    def test_scheduled_request_paid_historical_end_budget_target_and_remote_ids(self):
        stamp = self.observed.isoformat()
        target = dict(countries=["CA"])
        request = dict(
            request_id="99999999-9999-4999-8999-999999999999",
            post_id="123_777",
            content_hash=self.post["content_hash"],
            rights_hash="b" * 64,
            targeting_hash=digest(target),
            lifetime_budget_minor=80,
            end_time=(self.observed - timedelta(minutes=5)).isoformat(),
            targeting=target,
            name="Exact approved historical promotion",
        )
        scope = dict(
            self.scope,
            ad_account_id="456",
            max_campaigns=1,
            max_campaign_minor=90,
            max_total_minor=100,
            approved_targeting_hashes=[digest(target)],
            billing_acknowledged=True,
            ordinary_ad_attestation=True,
        )
        item = dict(
            item_id=ITEM,
            due_at=(self.observed - timedelta(minutes=10)).isoformat(),
            operation="campaign.ad-launch",
            request=request,
        )
        batch = dict(self.batch, scope_hash=digest(scope), items=[item])
        data = dict(
            batch_id=BATCH,
            item_id=ITEM,
            scope_id=SCOPE,
            request=request,
            operation="campaign.ad-launch",
        )
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_scopes SET summary=?,summary_hash=?",
                (canonical(scope), digest(scope)),
            )
            db.execute(
                "UPDATE campaign_schedule_batches SET summary=?,summary_hash=?",
                (canonical(batch), digest(batch)),
            )
            db.execute(
                "UPDATE campaign_schedule_items SET body=?,body_hash=?,due=?,job_id='paid-job',status='QUEUED'",
                (
                    canonical(item),
                    digest(item),
                    datetime.fromisoformat(item["due_at"]).timestamp(),
                ),
            )
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                (
                    "paid-job",
                    "sample-one",
                    "campaign_ad",
                    canonical(data),
                    "SUCCEEDED",
                    stamp,
                    stamp,
                    "paid-request",
                ),
            )
            db.execute(
                "INSERT INTO campaign_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample-one",
                    "verified-post",
                    SCOPE,
                    REQUEST,
                    digest(self.post),
                    self.post["content_hash"],
                    "b" * 64,
                    "123",
                    "VERIFIED",
                    "123_777",
                    None,
                    stamp,
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO campaign_paid_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample-one",
                    "paid-intent",
                    SCOPE,
                    request["request_id"],
                    digest(request),
                    "456",
                    "CAD",
                    80,
                    canonical(request),
                    canonical(
                        dict(campaign="101", adset="102", creative="103", ad="104")
                    ),
                    "ACTIVE_campaign",
                    None,
                    stamp,
                    stamp,
                ),
            )
        result = self.preview()
        item = result["summary"]["schedule"]["items"][0]
        self.assertEqual(item["operation"], "campaign.ad-launch")
        self.assertEqual(item["effective_status"], "ACTIVE_VERIFIED")
        self.assertEqual(item["intent"]["ids"]["ad"], "104")
        self.assertEqual(item["intent"]["commitment"], 80)
        self.assertEqual(result["summary"]["campaign"]["commitment_held_minor"], 80)
        self.assertEqual(
            result["summary"]["campaign"]["approval"]["approved_targeting_hashes"],
            [digest(target)],
        )
        self.assertEqual(
            result["summary"]["campaign"]["receipts"][1]["ids"]["campaign"], "101"
        )
        with connection(self.store.path) as db:
            db.execute(
                "UPDATE campaign_paid_intents SET status='PENDING_ACTIVATE_campaign'"
            )
        uncertain = self.preview()
        self.assertEqual(uncertain["status"], "warning")
        self.assertTrue(uncertain["summary"]["dispatch_uncertain"])
        self.assertEqual(
            uncertain["summary"]["schedule"]["items"][0]["effective_status"],
            "NEEDS_RECONCILIATION",
        )

    def test_helpers_reject_malformed_data_and_unknown_table(self):
        for raw in ("[]", "{broken"):
            with self.assertRaises(Invalid):
                saved_object(raw)
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):
                owned(
                    db,
                    "secret-table",
                    "sample-one",
                    SCOPE,
                    identities.OWNER["principal"],
                )
        with self.assertRaises(Invalid):
            selection({})

    def test_protected_http_fresh_identity_and_no_authority(self):
        server = Server(("127.0.0.1", 0), self.store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch(
                "mission_control.operator_identity.github_read",
                side_effect=identities.synthetic_identity,
            ):
                owner = OperatorClient("http://127.0.0.1:" + str(server.server_port))
                owner.bootstrap()
                route = "/api/apps/sample-one/agent-grants/agreement-preview"
                with self.assertRaises(ClientError):
                    owner.request("POST", route, self.body())
                owner.request(
                    "POST", "/api/identity/login", dict(token=identities.OWNER_TOKEN)
                )
                before = self.fixture.dump()
                result = owner.request("POST", route, self.body())
                self.assertFalse(result["authority_issued"])
                self.assertEqual(result["summary_hash"], digest(result["summary"]))
                self.assertEqual(before, self.fixture.dump())
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
