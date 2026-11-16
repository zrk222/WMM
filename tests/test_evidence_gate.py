"""Campaign launch gate refuses an incomplete measurement plan."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from mission_control.campaign_contract import scope_data
from mission_control.campaign_execution import SCHEMA
from mission_control.campaign_metric_definitions import joined_outcome_advice
from mission_control.campaign_transport import MetaTransport, Unconfirmed
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.evidence_gate import (
    APPLE_MEASUREMENT,
    APPLE_PRIMARY_METRIC,
    assert_ready,
    check_promotion_link,
    evaluate,
    latest,
    measurement_plan,
    plan_providers,
    provider_set,
)
from mission_control.operator_client import OperatorClient
from mission_control.store import Store
from mission_control.worker import campaign_job_preview
from tests import test_campaign_access, test_campaign_execution


def plan():
    now = datetime.now(timezone.utc)
    return dict(
        primary_metric="paid_conversion",
        denominator="installs",
        link="https://example.test/app?utm_campaign=launch-a",
        campaign_tag="launch-a",
        starts_at=(now - timedelta(minutes=5)).isoformat(),
        ends_at=(now + timedelta(days=8)).isoformat(),
        hypothesis="The tagged launch improves paid conversion.",
        decision_rule="Keep if the interval excludes zero; otherwise revise.",
    )


class EvidenceGateTests(unittest.TestCase):
    def test_apple_plan_binds_one_organic_post_to_the_exact_listing_and_readiness(self) -> None:
        from tests.test_apple_metrics_http_route import APP, AppleMetricsRouteTests

        source = AppleMetricsRouteTests()
        source.setUp()
        self.addCleanup(source.doCleanups)
        approved = dict(
            plan(),
            link="https://apps.apple.com/ca/app/example/id123?pt=456&ct=Early%20Launch&mt=8",
            campaign_tag="Early Launch",
            primary_metric=APPLE_PRIMARY_METRIC,
            denominator="none",
        )
        saved = measurement_plan(approved)
        self.assertEqual(saved["campaign_tag"], "early launch")
        self.assertEqual(saved["measurement_source"], APPLE_MEASUREMENT)
        self.assertEqual(measurement_plan(saved, retained=True), saved)
        self.assertNotIn("utm_campaign", saved)
        with self.assertRaisesRegex(Invalid, "match the tag"):
            measurement_plan(dict(approved, campaign_tag="other"))
        with self.assertRaisesRegex(Invalid, "first-time downloads"):
            measurement_plan(dict(approved, primary_metric="paid_conversion"))

        scope = dict(measurement_plan=saved, status="ACTIVE", ad_account_id=None)
        post = dict(link=saved["link"])
        self.assertEqual(evaluate(scope, {"posthog", "revenuecat"}, request=post)["status"], "BLOCKED")
        self.assertEqual(evaluate(scope, {APPLE_MEASUREMENT}, request=post)["status"], "READY")
        self.assertEqual(evaluate(dict(scope, ad_account_id="123"), {APPLE_MEASUREMENT})["status"], "BLOCKED")
        self.assertEqual(
            evaluate(scope, {APPLE_MEASUREMENT}, request=dict(link="https://example.test/"))["status"], "BLOCKED"
        )
        with patch.dict(os.environ, {"GROWTH_SAMPLE_ONE_SYNTHETIC": "fixture"}):
            self.assertEqual(plan_providers(source.store, APP, saved), set())
            inventory_id = source.campaign_inventory([])
            self.assertEqual(assert_ready(source.store, APP, scope, post)["status"], "READY")
            with self.assertRaisesRegex(Invalid, "this app's App Store listing"):
                plan_providers(source.store, APP, dict(saved, link=saved["link"].replace("id123", "id999")))
            with connection(source.store.path, write=True) as db:
                db.execute("UPDATE jobs SET result=json_set(result,'$.coverage','PARTIAL') WHERE id=?", (inventory_id,))
            self.assertEqual(plan_providers(source.store, APP, saved), set())
            with connection(source.store.path, write=True) as db:
                db.execute(
                    "UPDATE jobs SET result=json_set(result,'$.coverage','COMPLETE','$.observed_at',?) WHERE id=?",
                    ((datetime.now(timezone.utc) - timedelta(days=8)).isoformat(), inventory_id),
                )
            self.assertEqual(plan_providers(source.store, APP, saved), set())
        self.assertEqual(plan_providers(source.store, APP, saved), set())

        campaign: Any = test_campaign_execution.CampaignTests()
        campaign.setUp()
        self.addCleanup(campaign.doCleanups)
        with self.assertRaisesRegex(Invalid, "exactly one organic post"):
            scope_data(dict(campaign.body, measurement_plan=approved))
        body = dict(campaign.body, max_posts=1, measurement_plan=approved)
        with self.assertRaisesRegex(Invalid, "this app's App Store listing"):
            campaign.service.prepare_scope("sample", "owner", body)
        app = campaign.store.app("sample")
        campaign.store.save_app("sample", dict(app["data"], store_app_id="123"), app["version"])
        draft = campaign.service.prepare_scope("sample", "owner", body)
        self.assertEqual(draft["measurement_plan"], saved)

    def test_transport_checks_write_permission_after_resolution_and_before_request(self):
        events = []

        def deny():
            events.append("validate")
            raise Invalid("Evidence changed")

        def resolve(*_):
            events.append("resolve")
            return "192.0.2.1"

        with (
            patch("mission_control.campaign_transport.address", side_effect=resolve),
            patch("mission_control.campaign_transport.trust_context"),
            patch("mission_control.campaign_transport.PinnedHTTPS") as connection_factory,
        ):
            conn = connection_factory.return_value
            with self.assertRaises(Unconfirmed):
                MetaTransport().publish("123", "synthetic", None, "token", "secret", deny)
            self.assertEqual(events, ["resolve", "validate"])
            conn.request.assert_not_called()
            conn.close.assert_called_once()

    def test_organic_source_drift_at_dispatch_never_sends_post(self):
        fixture: Any = test_campaign_execution.CampaignTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        approved = plan()
        post = dict(
            fixture.post,
            link=approved["link"],
            content_hash=digest(dict(message=fixture.post["message"], link=approved["link"])),
        )
        body = dict(fixture.body, measurement_plan=approved, approved_content_hashes=[post["content_hash"]])
        proposal = fixture.service.prepare_scope("sample", "owner", body)
        scope_id = proposal["scope_id"]
        fixture.service.activate_scope("sample", "owner", scope_id, proposal["approval_hash"])
        with (
            patch("mission_control.evidence_gate.provider_set", side_effect=[{"posthog", "revenuecat"}] * 2 + [set()]),
            patch("mission_control.campaign_execution.check_destination", return_value={"status": "REACHABLE"}),
            self.assertRaises(Unconfirmed),
        ):
            fixture.service.run_post("sample", "owner", scope_id, post)
        self.assertEqual(fixture.transport.posts, 0)

    def test_new_scope_cannot_claim_a_prior_measurement_tag(self) -> None:
        fixture: Any = test_campaign_execution.CampaignTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        approved = plan()
        body = dict(fixture.body, measurement_plan=approved)
        first = fixture.service.prepare_scope("sample", "owner", body)
        second = fixture.service.prepare_scope("sample", "owner", body)
        fixture.service.activate_scope("sample", "owner", first["scope_id"], first["approval_hash"])
        for rejected in (
            lambda: fixture.service.prepare_scope("sample", "owner", body),
            lambda: fixture.service.activate_scope("sample", "owner", second["scope_id"], second["approval_hash"]),
        ):
            with self.assertRaisesRegex(Invalid, "tag belongs to an earlier campaign"):
                rejected()
        self.assertEqual(fixture.service.get_scope("sample", second["scope_id"])["status"], "DRAFT")
        retained = fixture.service.get_scope("sample", first["scope_id"])
        self.assertEqual((retained["status"], retained["approval_hash"]), ("ACTIVE", first["approval_hash"]))
        replacement = dict(approved, campaign_tag="launch-b", link=approved["link"].replace("launch-a", "launch-b"))
        fresh = fixture.service.prepare_scope("sample", "owner", dict(body, measurement_plan=replacement))
        activated = fixture.service.activate_scope("sample", "owner", fresh["scope_id"], fresh["approval_hash"])
        self.assertEqual(activated["status"], "ACTIVE")
        self.assertEqual(fixture.transport.posts, 0)
        # Dropping the plan in a raw API request still cannot publish under a conflicting tag.
        post = dict(fixture.post, link=approved["link"])
        post["content_hash"] = digest({"message": post["message"], "link": post["link"]})
        unmeasured = fixture.service.prepare_scope(
            "sample", "owner", dict(fixture.body, approved_content_hashes=[post["content_hash"]])
        )
        fixture.service.activate_scope("sample", "owner", unmeasured["scope_id"], unmeasured["approval_hash"])
        with (
            patch("mission_control.campaign_execution.check_destination", return_value={"status": "REACHABLE"}),
            self.assertRaisesRegex(Invalid, "tag belongs to an earlier campaign"),
        ):
            fixture.service.run_post("sample", "owner", unmeasured["scope_id"], post)
        self.assertEqual(fixture.transport.posts, 0)
        self.assertEqual(fixture.service.list_intents("sample", unmeasured["scope_id"]), [])

    def test_joined_advice_distinguishes_missing_data_from_a_testable_drop(self) -> None:
        delivery = {"status": "EXACT_TAGGED_POST_READBACK"}
        report = {
            "coverage": "DECLARED_COMPLETE",
            "counts": {"INSTALL": 70, "ACTIVATION": 67, "TRIAL_START": 55, "PURCHASE": 17},
        }
        result = joined_outcome_advice(delivery, report)
        self.assertEqual(result["status"], "REVIEW_PAID")
        self.assertIn("17 paid out of 55 trial starters", str(result["reason"]))
        self.assertIn("fresh approval", str(result["next_action"]))
        self.assertEqual(joined_outcome_advice({}, report)["status"], "REPAIR_DELIVERY")
        self.assertEqual(
            joined_outcome_advice(delivery, dict(report, coverage="PARTIAL"))["status"], "COLLECT_MATCHED_WINDOW"
        )
        self.assertEqual(joined_outcome_advice(delivery, dict(report, counts=None))["status"], "COLLECT_MORE")

    def test_legacy_scheduled_link_reserves_campaign_tag_case_insensitively(self) -> None:
        from mission_control.campaign_schedule import initialize

        fixture: Any = test_campaign_execution.CampaignTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        initialize(fixture.store)
        stamp = now()
        item = {"request": {"link": "https://example.test/app?utm_campaign=Launch-A"}}
        with connection(fixture.store.path) as db:
            db.execute(
                "INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("old", "sample", "owner", fixture.scope["scope_id"], "{}", digest({}), "OFF", 1, stamp, stamp),
            )
            db.execute(
                "INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)",
                ("prior-item", "old", 1, canonical(item), digest(item), "VERIFIED", None, stamp, stamp),
            )
        with self.assertRaisesRegex(Invalid, "tag belongs to an earlier campaign"):
            fixture.service.prepare_scope("sample", "owner", dict(fixture.body, measurement_plan=plan()))
        self.assertEqual(fixture.transport.posts, 0)

    def test_plan_binds_tagged_link_and_window(self):
        base = plan()
        value = measurement_plan(base)
        self.assertEqual(value["utm_campaign"], "launch-a")
        with self.assertRaises(Invalid):
            measurement_plan(dict(base, campaign_tag="other"))
        with self.assertRaises(Invalid):
            measurement_plan(dict(base, ends_at=base["starts_at"]))

    def test_real_scope_round_trip_dispatches_only_the_approved_link(self):
        fixture: Any = test_campaign_execution.CampaignTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        value = plan()
        post = dict(
            fixture.post,
            link=value["link"],
            content_hash=digest({"message": fixture.post["message"], "link": value["link"]}),
        )
        body = dict(fixture.body, measurement_plan=value, approved_content_hashes=[post["content_hash"]])
        proposal = fixture.service.prepare_scope("sample", "owner", body)
        scope_id = proposal["scope_id"]
        approved = fixture.service.activate_scope("sample", "owner", scope_id, proposal["approval_hash"])
        self.assertEqual(approved["approval_hash"], proposal["approval_hash"])
        with (
            patch("mission_control.evidence_gate.provider_set", return_value={"posthog", "revenuecat"}),
            patch("mission_control.campaign_execution.check_destination", return_value={"status": "REACHABLE"}),
        ):
            with self.assertRaisesRegex(Invalid, "TAGGED_LINK"):
                fixture.service.run_post("sample", "owner", scope_id, fixture.post)
            result = fixture.service.run_post("sample", "owner", scope_id, post)
            self.assertEqual(fixture.service.run_post("sample", "owner", scope_id, post)["id"], result["id"])
        self.assertEqual(result["status"], "VERIFIED")
        self.assertEqual(fixture.transport.posts, 1)

    def test_gate_is_ready_only_with_both_source_families(self):
        scope = dict(status="ACTIVE", measurement_plan=plan())
        ready = evaluate(scope, {"posthog", "revenuecat"})
        self.assertEqual(ready["status"], "READY")
        blocked = evaluate(scope, {"posthog"})
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertTrue(any(item["name"] == "OUTCOME_SOURCE" for item in blocked["blockers"]))

    def test_measurement_window_includes_start_and_excludes_end(self):
        approved = plan()
        starts = datetime.fromisoformat(approved["starts_at"])
        ends = datetime.fromisoformat(approved["ends_at"])
        scope = dict(status="ACTIVE", measurement_plan=approved)
        providers = {"posthog", "revenuecat"}

        def checks(at):
            return {item["name"]: item["status"] for item in evaluate(scope, providers, observed=at)["checks"]}

        self.assertEqual(checks(starts - timedelta(seconds=1))["WINDOW"], "NOT_STARTED")
        self.assertEqual(checks(starts)["WINDOW"], "PASS")
        self.assertEqual(checks(ends)["WINDOW"], "EXPIRED")

    def test_mismatched_request_link_blocks_launch(self):
        scope = dict(status="ACTIVE", measurement_plan=plan())
        result = evaluate(
            scope, {"posthog", "revenuecat"}, request={"link": "https://example.test/app?utm_campaign=other"}
        )
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any(item["name"] == "TAGGED_LINK" for item in result["blockers"]))

    def test_assert_ready_reads_saved_connection_records(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "state.sqlite")
            self.assertEqual(provider_set(store, "sample-one"), set())
            with connection(store.path) as db:
                for provider in ("posthog", "revenuecat"):
                    sid = provider + "-source"
                    config = dict(provider=provider, project_id="project-" + provider)
                    config_hash = digest(config)
                    stamp = now()
                    report = dict(
                        **config,
                        source_version=1,
                        configuration_hash=config_hash,
                        observed_at=stamp,
                        scope=(
                            "PROJECT_ID_CHECKED"
                            if provider == "posthog"
                            else "PROJECT_PATH_CHECKED_PROJECT_WIDE_METRICS"
                        ),
                        rows=[dict(id="metric", unit="events", period="last_7_days", value=0)],
                    )
                    db.execute(
                        "INSERT INTO insight_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            "sample-one",
                            sid,
                            provider,
                            canonical(config),
                            config_hash,
                            "key",
                            "ref",
                            1,
                            "CONNECTED",
                            0,
                            0,
                            None,
                            "",
                            "",
                        ),
                    )
                    db.execute(
                        "INSERT INTO insight_reports VALUES(?,?,?,?,?,?,?)",
                        ("sample-one", sid + "-report", sid, provider, canonical(report), digest(report), stamp),
                    )
            result = assert_ready(store, "sample-one", dict(status="ACTIVE", measurement_plan=plan()))
            self.assertEqual(result["status"], "READY")
            self.assertFalse(result["outcome_tracking_verified"])
            with self.assertRaises(Invalid):
                assert_ready(
                    store,
                    "sample-one",
                    dict(status="ACTIVE", measurement_plan=plan()),
                    request={"link": "https://example.test/"},
                )
            with connection(store.path) as db:
                retained = db.execute(
                    "SELECT data,created FROM insight_reports WHERE app_id=? AND provider=?",
                    ("sample-one", "revenuecat"),
                ).fetchone()
            assert retained is not None
            data, stamp = json.loads(retained["data"]), retained["created"]
            invalid = (
                (data, "wrong-hash"),
                (dict(data, project_id="other-project"), None),
                (dict(data, scope="unverified"), None),
                (dict(data, rows=[None]), None),
                (dict(data, source_version=2), None),
                (dict(data, observed_at=(datetime.now(timezone.utc) - timedelta(days=8)).isoformat()), None),
            )
            for index, (changed, receipt) in enumerate(invalid):
                with self.subTest(index=index):
                    with connection(store.path) as db:
                        db.execute(
                            "INSERT INTO insight_reports VALUES(?,?,?,?,?,?,?)",
                            (
                                "sample-one",
                                f"invalid-{index}",
                                "revenuecat-source",
                                "revenuecat",
                                canonical(changed),
                                receipt or digest(changed),
                                stamp,
                            ),
                        )
                    self.assertEqual(provider_set(store, "sample-one"), {"posthog"})
                    with self.assertRaisesRegex(Invalid, "OUTCOME_SOURCE"):
                        assert_ready(store, "sample-one", dict(status="ACTIVE", measurement_plan=plan()))

    def test_workspace_readiness_omits_private_scope_data(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "state.sqlite")
            saved = {"measurement_plan": measurement_plan(dict(plan(), hypothesis="private owner text"))}
            with connection(store.path) as db:
                db.executescript(SCHEMA)
                db.execute(
                    "INSERT INTO campaign_scopes VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        "sample-one",
                        "private-scope-id",
                        "owner",
                        1,
                        canonical(saved),
                        digest(saved),
                        "ACTIVE",
                        0,
                        "",
                        "",
                    ),
                )
            view = latest(store, "sample-one")
            for private in ("private owner text", "private-scope-id", "example.test", "launch-a"):
                self.assertNotIn(private, canonical(view))
            self.assertEqual(view["status"], "BLOCKED")

    def test_campaign_http_reads_preserve_owner_review_and_hide_exact_inputs(self):
        fixture: Any = test_campaign_access.CampaignGatewayTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        approved = dict(plan(), hypothesis="synthetic private hypothesis")
        fixture.scope["measurement_plan"] = approved
        scope_id = fixture.activate()["scope_id"]
        owner_view = fixture.owner_call("status", {"scope_id": scope_id})
        self.assertEqual(owner_view["scope"]["measurement_plan"]["hypothesis"], approved["hypothesis"])

        reader = fixture.agent(["campaign.history", "campaign.status"])
        for operation, args in (("campaign.history", {}), ("campaign.status", {"scope_id": scope_id})):
            response = reader.call(dict(app_id="sample-one", operation=operation, input=args))
            self.assertNotIn(approved["hypothesis"], canonical(response))
            self.assertNotIn(approved["link"], canonical(response))

        message = "synthetic exact post reserved for owner"
        with connection(fixture.store.path) as db:
            request = dict(fixture.post, link=approved["link"], message=message)
            payload = canonical(dict(scope_id=scope_id, batch_id="sample-batch", request=request))
            db.execute(
                "INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)",
                ("sample-job", "sample-one", "campaign_post", payload, "QUEUED", now(), now(), "sample-key"),
            )
        from tests.test_verified_review import CHECKER_TOKEN

        anonymous = OperatorClient(fixture.origin)
        other = OperatorClient(fixture.origin)
        other.bootstrap()
        other.request("POST", "/api/identity/login", {"token": CHECKER_TOKEN})
        for viewer in (anonymous, other):
            view = canonical(viewer.request("GET", "/api/apps/sample-one"))
            self.assertNotIn(approved["hypothesis"], view)
            self.assertNotIn(approved["link"], view)

        signed_out = OperatorClient(fixture.origin)
        signed_out.bootstrap()
        for endpoint in ("/api/apps/sample-one", "/api/apps/sample-one/jobs"):
            serialized = canonical(signed_out.request("GET", endpoint))
            self.assertNotIn(approved["hypothesis"], serialized)
            self.assertNotIn(approved["link"], serialized)
            self.assertNotIn(message, serialized)
            self.assertIn(digest(approved["link"]), serialized)
            self.assertIn("sample-job", serialized)
        self.assertEqual(fixture.wire.posts, 0)

    def test_generic_job_preview_carries_only_a_link_fingerprint(self):
        exact = "https://example.test/path?utm_campaign=launch-a"
        result: Any = campaign_job_preview(
            dict(
                action="campaign_post",
                data={"scope_id": "scope", "request": {"link": exact, "message": "private"}},
                result={"status": "VERIFIED", "remote_id": "123_777", "result": {"final_url": exact}},
            )
        )
        self.assertEqual(result["data"]["approved_link_sha256"], digest(exact))
        self.assertNotIn(exact, canonical(result))
        self.assertNotIn("private", canonical(result))
        self.assertEqual(result["result"]["status"], "VERIFIED")

    def test_paid_promotion_requires_the_approved_destination_receipt(self):
        saved = measurement_plan(plan())
        for data in ({}, {"destination_check": {"approved_link_sha256": "different"}}):
            with self.assertRaises(Invalid):
                check_promotion_link({"result": canonical(data)}, saved)
        check_promotion_link(
            {"result": canonical({"destination_check": {"approved_link_sha256": digest(saved["link"])}})}, saved
        )

    def test_retained_plan_revalidates_without_changing_approval(self):
        saved = measurement_plan(plan())
        self.assertEqual(measurement_plan(saved, retained=True), saved)
        for malformed in (dict(saved, utm_campaign="other"), dict(saved, link="https://[bad")):
            with self.assertRaises(Invalid):
                measurement_plan(malformed, retained=True)
        self.assertEqual(evaluate({"measurement_plan": saved}, {"posthog", "revenuecat"})["status"], "READY")
        for request in ({}, {"link": None}):
            blocked = evaluate({"measurement_plan": saved}, {"posthog", "revenuecat"}, request=request)
            self.assertEqual(blocked["status"], "BLOCKED")
        expired = evaluate(
            {"measurement_plan": saved},
            {"posthog", "revenuecat"},
            observed=datetime.now(timezone.utc) + timedelta(days=10),
        )
        self.assertEqual(expired["status"], "BLOCKED")

    def test_campaign_scope_accepts_one_optional_measurement_plan(self):
        import datetime as clock

        now = clock.datetime.now(clock.timezone.utc)
        body = dict(
            connection_id="11111111-1111-4111-8111-111111111111",
            page_id="123",
            ad_account_id=None,
            currency="USD",
            expires_at=(now + clock.timedelta(hours=1)).isoformat(),
            max_posts=1,
            max_calls=10,
            max_campaigns=0,
            max_campaign_minor=0,
            max_total_minor=0,
            approved_content_hashes=["a" * 64],
            approved_rights_hashes=["b" * 64],
            approved_targeting_hashes=[],
            billing_acknowledged=True,
            ordinary_ad_attestation=True,
            measurement_plan=plan(),
        )
        value = cast(dict[str, object], scope_data(body))
        plan_value = value["measurement_plan"]
        assert isinstance(plan_value, dict)
        self.assertEqual(plan_value["campaign_tag"], "launch-a")
        with self.assertRaises(Invalid):
            scope_data(dict(body, measurement_plan=dict(plan(), link="https://example.test/app")))
