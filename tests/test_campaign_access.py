"""Actual HTTP owner scope and agent delivery with a synthetic provider boundary."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from mission_control.campaign_execution import CampaignExecutionService
from mission_control.common import canonical, digest, now
from mission_control.db import connection
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.store import Store
from tests import test_agent_grants as grant_fixture
from tests.test_campaign_execution import FakePaidTransport, FakeTransport


class CampaignGatewayTests(unittest.TestCase):
    # GrantTests.setUp populates these through setUp_base.
    store: Store
    origin: str
    owner: OperatorClient

    setUp_base = grant_fixture.GrantTests.setUp
    tearDown = grant_fixture.GrantTests.tearDown
    body = grant_fixture.GrantTests.body

    def setUp(self):
        self.setUp_base()
        stamp = now()
        self.wire = FakeTransport()
        self.connection = "11111111-1111-4111-8111-111111111111"
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                (
                    "sample-one",
                    "facebook",
                    1,
                    canonical({"provider": "facebook"}),
                    "cfg",
                    "CONFIGURED_UNTESTED",
                    stamp,
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample-one",
                    self.connection,
                    "facebook",
                    1,
                    1,
                    "subject",
                    canonical(
                        {
                            "destination": {
                                "id": "123",
                                "name": "Synthetic Page",
                                "kind": "PAGE",
                                "tasks": ["CREATE_CONTENT"],
                            },
                            "facts": {"renewal": "OFFICIAL_REAUTHORIZATION"},
                        }
                    ),
                    "grant",
                    "CONNECTED_READ_TESTED",
                    None,
                    None,
                    0,
                    None,
                    0,
                    stamp,
                    stamp,
                ),
            )
        self.message = "An exact synthetic app post"
        self.content = digest({"message": self.message, "link": None})
        self.scope = dict(
            connection_id=self.connection,
            page_id="123",
            ad_account_id=None,
            currency="CAD",
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            max_posts=1,
            max_calls=50,
            max_campaigns=0,
            max_campaign_minor=0,
            max_total_minor=0,
            approved_content_hashes=[self.content],
            approved_rights_hashes=["b" * 64],
            approved_targeting_hashes=[],
            billing_acknowledged=False,
            ordinary_ad_attestation=False,
        )
        self.post = dict(
            request_id="22222222-2222-4222-8222-222222222222",
            message=self.message,
            link=None,
            content_hash=self.content,
            rights_hash="b" * 64,
        )
        # Only the remote provider is synthetic. The owner, scope, grant, quota,
        # protected transaction and durable intent paths are real.
        self.transport = patch("mission_control.campaign_execution.MetaTransport", side_effect=lambda: self.wire)
        self.transport.start()
        self.addCleanup(self.transport.stop)
        self.preflight = patch.object(
            CampaignExecutionService,
            "_preflight",
            lambda flow, app, actor, scope_id, action, active=True: (
                flow.get_scope(app, scope_id),
                "synthetic-secret",
                "synthetic-token",
            ),
        )
        self.preflight.start()
        self.addCleanup(self.preflight.stop)

    def owner_call(self, action, body):
        result = self.owner.request("POST", "/api/apps/sample-one/campaigns/" + action, body)
        assert isinstance(result, dict)
        return result

    def activate(self):
        saved = self.owner_call("prepare", {"scope": self.scope})
        return self.owner_call("activate", {"scope_id": saved["scope_id"], "approval_hash": saved["approval_hash"]})

    def agent(self, names):
        issued = self.owner.request(
            "POST", "/api/apps/sample-one/agent-grants/issue", {**self.body(), "operations": names}
        )
        assert isinstance(issued, dict)
        return OperatorClient(self.origin, grant_token=issued["token"])

    def test_fresh_owner_and_exact_hash_are_required_to_issue_authority(self):
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        with self.assertRaises(ClientError):
            anonymous.request("POST", "/api/apps/sample-one/campaigns/prepare", {"scope": self.scope})
        saved = self.owner_call("prepare", {"scope": self.scope})
        with self.assertRaises(ClientError):
            self.owner_call("activate", {"scope_id": saved["scope_id"], "approval_hash": "0" * 64})
        self.assertEqual(self.owner_call("history", {})["scopes"][0]["status"], "DRAFT")
        self.assertEqual(self.wire.posts, 0)

    def test_scoped_agent_publishes_once_then_reads_verified_delivery(self):
        saved = self.activate()
        agent = self.agent(["campaign.publish", "campaign.status"])
        envelope = dict(
            app_id="sample-one",
            operation="campaign.publish",
            input={"scope_id": saved["scope_id"], "request": self.post},
        )
        sent = agent.call(envelope)
        again = agent.call(envelope)
        assert isinstance(sent, dict) and isinstance(again, dict)
        self.assertEqual(sent["id"], again["id"])
        self.assertEqual(sent["status"], "VERIFIED")
        self.assertEqual(self.wire.posts, 1)
        result = agent.call(
            dict(app_id="sample-one", operation="campaign.status", input={"scope_id": saved["scope_id"]})
        )
        assert isinstance(result, dict)
        self.assertEqual(result["intents"][0]["remote_id"], "123_777")
        self.assertNotIn("synthetic-token", canonical(result))
        self.owner_call("revoke", {"scope_id": saved["scope_id"]})
        with self.assertRaises(ClientError):
            agent.call(envelope)
        self.assertEqual(self.wire.posts, 1)

    def test_changed_draft_recommends_owner_review_without_scheduling_or_publishing(self) -> None:
        scope_id = self.activate()["scope_id"]
        agent = self.agent(["campaign.publish"])
        due = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        original = self.owner_call("status", {"scope_id": scope_id})["scope"]
        text = "A revised synthetic app post"
        variants = (
            dict(self.post, message=text, content_hash=digest({"message": text, "link": None})),
            dict(self.post, rights_hash="c" * 64),
        )
        for request in variants:
            with self.assertRaises(ClientError) as schedule:
                self.owner_call(
                    "schedule-prepare", {"scope_id": scope_id, "items": [{"due_at": due, "request": request}]}
                )
            with self.assertRaises(ClientError) as publish:
                agent.call(
                    dict(
                        app_id="sample-one",
                        operation="campaign.publish",
                        input={"scope_id": scope_id, "request": request},
                    )
                )
            for rejected in (schedule.exception, publish.exception):
                self.assertEqual((rejected.status, rejected.code), (403, "CAMPAIGN_REVIEW_REQUIRED"))
                self.assertIn("app owner to review the exact post and its rights", str(rejected))
                self.assertNotIn(request["message"], str(rejected))
        self.assertEqual(self.owner_call("schedule-history", {})["batches"], [])
        self.assertEqual(self.owner_call("status", {"scope_id": scope_id}), {"scope": original, "intents": []})
        self.assertEqual(self.wire.posts, 0)
        valid = self.owner_call(
            "schedule-prepare", {"scope_id": scope_id, "items": [{"due_at": due, "request": self.post}]}
        )
        self.assertEqual(valid["summary"]["items"][0]["request"]["content_hash"], self.content)
        self.assertEqual(self.wire.posts, 0)

    def test_tracked_receipts_match_exact_link_and_do_not_widen_grant_access(self):
        link = "https://example.com/?utm_campaign=study-a"
        self.content = digest({"message": self.message, "link": link})
        self.scope["approved_content_hashes"] = [self.content]
        self.post.update(link=link, content_hash=self.content)
        scope = self.activate()["scope_id"]
        with (
            patch(
                "mission_control.campaign_execution.check_destination",
                return_value={"approved_link_sha256": digest(link)},
            ),
            patch.object(self.wire, "read_post", side_effect=TimeoutError("Synthetic read failure")),
        ):
            result = self.owner_call("publish", {"scope_id": scope, "request": self.post})
        self.assertEqual(result["status"], "VERIFYING")
        body = {"approved_link_sha256": digest(link)}
        self.assertEqual(self.owner_call("history", body)["tracked_posts"]["records"], [])
        self.owner_call("reconcile", {"scope_id": scope, "intent_id": result["id"]})
        self.assertEqual(
            self.owner_call("history", body)["tracked_posts"],
            {"complete": True, "records": [{"id": result["id"], "page_id": "123", "remote_id": "123_777"}]},
        )
        self.assertEqual(
            self.owner_call("history", {"approved_link_sha256": digest(link + "b")})["tracked_posts"]["records"], []
        )
        self.assertNotIn("tracked_posts", self.owner_call("history", {}))
        with self.assertRaises(ClientError):
            self.owner_call("history", {"approved_link_sha256": "not-a-fingerprint"})
        with self.assertRaises(ClientError):
            self.agent(["campaign.history"]).call(dict(app_id="sample-one", operation="campaign.history", input=body))
        self.assertEqual(self.wire.posts, 1)

    def test_grant_cannot_create_scope_or_call_unsupported_effect(self):
        saved = self.activate()
        agent = self.agent(["campaign.status"])
        with self.assertRaises((ClientError, ValueError)):
            agent.call(dict(app_id="sample-one", operation="campaign.prepare", input={"scope": self.scope}))
        with self.assertRaises(ClientError):
            agent.call(
                dict(
                    app_id="sample-one",
                    operation="campaign.publish",
                    input={"scope_id": saved["scope_id"], "request": self.post},
                )
            )
        self.assertEqual(self.wire.posts, 0)

    def test_paid_launch_monitor_and_off_use_actual_protected_gateway(self):
        self.wire = FakePaidTransport()
        original = CampaignExecutionService
        with patch.object(
            original,
            "_credentials",
            return_value=(
                {},
                "synthetic-secret",
                {"access_token": "synthetic-user-token", "page_token": "synthetic-page-token"},
            ),
        ):
            organic = self.activate()
            self.owner_call("publish", {"scope_id": organic["scope_id"], "request": self.post})
            target = {"countries": ["CA"]}
            self.scope.update(
                ad_account_id="456",
                max_campaigns=1,
                max_campaign_minor=100,
                max_total_minor=100,
                approved_targeting_hashes=[digest(target)],
                billing_acknowledged=True,
                ordinary_ad_attestation=True,
            )
            paid = self.activate()
            agent = self.agent(["campaign.ad-launch", "campaign.status", "campaign.reconcile", "campaign.pause"])
            request = dict(
                request_id="33333333-3333-4333-8333-333333333333",
                post_id="123_777",
                content_hash=self.content,
                rights_hash="b" * 64,
                targeting_hash=digest(target),
                targeting=target,
                lifetime_budget_minor=80,
                end_time=(datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
                name="Synthetic approved app campaign",
            )
            envelope = dict(
                app_id="sample-one",
                operation="campaign.ad-launch",
                input={"scope_id": paid["scope_id"], "request": request},
            )
            launched = agent.call(envelope)
            assert isinstance(launched, dict)
            self.assertEqual(launched["status"], "ACTIVE_campaign")
            self.assertEqual(launched["commitment"], 80)
            replay = agent.call(envelope)
            assert isinstance(replay, dict)
            self.assertEqual(replay["id"], launched["id"])
            self.assertEqual(len(self.wire.objects), 4)
            observed = agent.call(
                dict(
                    app_id="sample-one",
                    operation="campaign.reconcile",
                    input={"scope_id": paid["scope_id"], "intent_id": launched["id"]},
                )
            )
            assert isinstance(observed, dict)
            self.assertEqual(observed["result"]["reported_spend"], "1.23")
            stopped = self.owner_call("revoke", {"scope_id": paid["scope_id"]})
            self.assertEqual(stopped["pause_results"][0]["status"], "PAUSED_campaign")
            self.assertEqual(self.wire.objects[launched["ids"]["campaign"]]["status"], "PAUSED")
            with self.assertRaises(ClientError):
                agent.call(envelope)
            self.assertEqual(len(self.wire.objects), 4)

    def test_unbound_domain_calls_and_duplicate_fields_are_rejected(self):
        from mission_control.campaign_access import dispatch

        with self.assertRaises(PermissionError):
            dispatch(self.store, "sample-one", "history", {})
        for body in ({"scope": self.scope, "owner": "forged"}, {"scope": self.scope, "approve": True}):
            with self.assertRaises(ClientError):
                self.owner_call("prepare", body)
        self.assertEqual(self.wire.posts, 0)


if __name__ == "__main__":
    unittest.main()
