"""Campaign launch gate refuses an incomplete measurement plan."""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast

from mission_control.campaign_contract import scope_data
from mission_control.common import Invalid
from mission_control.evidence_gate import assert_ready, evaluate, measurement_plan
from mission_control.store import Store


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
            store.save_record(
                "sample-one",
                dict(kind="connection", title="PostHog", source="synthetic", data=dict(provider="posthog")),
            )
            store.save_record(
                "sample-one",
                dict(kind="connection", title="RevenueCat", source="synthetic", data=dict(provider="revenuecat")),
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
