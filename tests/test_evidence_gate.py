"""Campaign launch gate refuses an incomplete measurement plan."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from mission_control.campaign_contract import scope_data
from mission_control.campaign_execution import SCHEMA
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.evidence_gate import (
    assert_ready,
    check_promotion_link,
    evaluate,
    latest,
    measurement_plan,
    provider_set,
)
from mission_control.store import Store
from mission_control.worker import campaign_job_preview
from tests import test_campaign_execution


def plan():
    now = datetime.now(timezone.utc)
    return dict(
        primary_metric="paid_conversion",
        denominator="installs",
        link="https://example.test/app?utm_campaign=launch-a",
        campaign_tag="launch-a",
        starts_at=(now + timedelta(days=1)).isoformat(),
        ends_at=(now + timedelta(days=8)).isoformat(),
        hypothesis="The tagged launch improves paid conversion.",
        decision_rule="Keep if the interval excludes zero; otherwise revise.",
    )


class EvidenceGateTests(unittest.TestCase):
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
                    db.execute(
                        "INSERT INTO insight_sources VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("sample-one", sid, provider, "{}", "hash", "key", "ref", 1, "CONNECTED", 0, 0, None, "", ""),
                    )
                    db.execute(
                        "INSERT INTO insight_reports VALUES(?,?,?,?,?,?,?)",
                        (
                            "sample-one",
                            sid + "-report",
                            sid,
                            provider,
                            '{"source_version":1,"configuration_hash":"hash","rows":[{"value":0}]}',
                            "receipt",
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
            result = assert_ready(store, "sample-one", dict(status="ACTIVE", measurement_plan=plan()))
            self.assertEqual(result["status"], "READY")
            with self.assertRaises(Invalid):
                assert_ready(
                    store,
                    "sample-one",
                    dict(status="ACTIVE", measurement_plan=plan()),
                    request={"link": "https://example.test/"},
                )

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
