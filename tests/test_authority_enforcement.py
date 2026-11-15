"""Server-side authority enforcement: spoofed bodies, budgets and AGENT origin."""

from datetime import datetime, timedelta, timezone
import unittest
from mission_control.common import Invalid, digest, now
from mission_control.complete_automation import proposal_data
from mission_control.campaign_contract import scope_data
from mission_control.operation_authority import REQUEST
from mission_control.operator_client import ClientError
from mission_control.review_access import Access
from mission_control.setup_approval import apply
from tests import test_agent_grants as grants_fixture
from tests import test_publication_authority as publication_fixture
from tests import test_setup_approval as setup_fixture

HASH = "a" * 64


class SetupOriginEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.fx = setup_fixture.SetupApprovalTests(
            "test_apply_selected_observation_and_edited_value_without_readiness_claim"
        )
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def test_body_cannot_inject_agent_origin_or_provenance(self):
        row = self.fx.start()
        for body in (
            self.fx.approval(row, {"name": "Reviewed", "origin": "AGENT"}),
            dict(self.fx.approval(row), origin="AGENT"),
            dict(self.fx.approval(row), setup_sources={"name": {"origin": "AGENT"}}),
        ):
            with self.subTest(body=body), self.assertRaises(Invalid):
                apply(self.fx.store, "sample-one", body)
        saved = self.fx.store.app("sample-one")
        token = REQUEST.set(dict(grant_id="grant-one"))
        try:
            apply(self.fx.store, "sample-one", self.fx.approval(row, {"name": "Reviewed"}))
        finally:
            REQUEST.reset(token)
        self.assertEqual(self.fx.store.app("sample-one")["data"]["setup_sources"]["name"]["origin"], "AGENT")
        self.assertNotEqual(self.fx.store.app("sample-one"), saved)


class GrantIssuanceSpoofTests(unittest.TestCase):
    def setUp(self):
        self.fx = grants_fixture.GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
        self.fx.setUp()
        self.addCleanup(self.fx.tearDown)

    def test_issue_body_cannot_set_authority_or_quota_state(self):
        for extra in (
            dict(used=0),
            dict(status="ACTIVE"),
            dict(app_hash=HASH),
            dict(owner="attacker"),
            dict(grant_id="forged"),
            dict(token_hash=HASH),
        ):
            with self.subTest(extra=extra), self.assertRaises(ClientError):
                self.fx.owner.request("POST", "/api/apps/sample-one/agent-grants/issue", dict(self.fx.body(), **extra))


class BudgetEnforcementTests(unittest.TestCase):
    def test_automation_scope_requires_zero_spend_and_exact_fields(self):
        observed = datetime.now(timezone.utc)
        body = dict(
            selection=dict(
                agent_id="agent-one",
                manifest_version=1,
                workflows=["local_evidence"],
                agent_connection_id=None,
                social_connection_ids=[],
            ),
            purpose="Synthetic review",
            limits=dict(
                expires=(observed + timedelta(hours=1)).isoformat(),
                max_calls=1,
                max_inflight=1,
                currency="USD",
                spend_limit_minor=0,
            ),
        )
        self.assertEqual(proposal_data(body, observed)["limits"]["spend_limit_minor"], 0)
        for changed in (
            dict(limits=dict(body["limits"], spend_limit_minor=1)),
            dict(limits=dict(body["limits"], spend_limit_minor=True)),
            dict(spend_minor=1),
        ):
            with self.subTest(changed=changed), self.assertRaises(Invalid):
                proposal_data(dict(body, **changed), observed)

    def test_campaign_scope_bounds_and_exact_fields(self):
        body = dict(
            connection_id="11111111-1111-4111-8111-111111111111",
            page_id="123",
            ad_account_id="456",
            currency="USD",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            max_posts=1,
            max_calls=5,
            max_campaigns=1,
            max_campaign_minor=100,
            max_total_minor=200,
            approved_content_hashes=[HASH],
            approved_rights_hashes=[HASH],
            approved_targeting_hashes=[HASH],
            billing_acknowledged=True,
            ordinary_ad_attestation=True,
        )
        self.assertEqual(scope_data(body)["max_total_minor"], 200)
        for changed in (
            dict(max_campaign_minor=300),
            dict(max_campaigns=21),
            dict(max_calls=0),
            dict(approved_content_hashes=[]),
            dict(spend_limit_minor=1),
        ):
            with self.subTest(changed=changed), self.assertRaises(Invalid):
                scope_data(dict(body, **changed))


class RoleAndPublicationEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.fx = publication_fixture.PublicationAuthorityTests("test_budget_and_review_are_enforced_atomically")
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def test_member_setup_cannot_grant_owner_or_supply_identity_fields(self):
        reviewer = dict(principal="github:2", login="maker")
        for body in (
            dict(login="maker", role="OWNER", status="ACTIVE", version=None),
            dict(login="maker", role="MAKER", status="ACTIVE", version=None, principal="github:2"),
        ):
            with self.subTest(body=body), self.assertRaises(Invalid):
                Access(self.fx.store).save(publication_fixture.APP, publication_fixture.OWNER, reviewer, body)

    def test_publication_approval_rejects_spoofed_state_and_immutable_limits(self):
        item = self.fx.prepare()
        with self.assertRaises(Invalid):
            self.fx.activate(item, calls_used=0)
        with self.assertRaises(Invalid):
            self.fx.activate(item, owner=publication_fixture.OWNER["principal"])
        approved = self.fx.activate(item, max_calls=1)
        with self.assertRaises(Exception):
            from mission_control.db import connection

            with connection(self.fx.store.path) as db:
                db.execute("UPDATE publication_authorities SET max_calls=999 WHERE id=?", (item["id"],))
        self.assertEqual(approved["max_calls"], 1)


if __name__ == "__main__":
    unittest.main()
