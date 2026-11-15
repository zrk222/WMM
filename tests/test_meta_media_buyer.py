"""Contract, capability drift, privacy and no-network tests for the on-demand role."""

import copy
import json
import time
import unittest
from unittest.mock import patch
from mission_control.agent_operations import discovery
from mission_control.common import Invalid, digest
from mission_control.meta_media_buyer import contract, index, selector
from mission_control.operation_catalog import catalog, request_data


class MetaMediaBuyerTests(unittest.TestCase):
    def setUp(self):
        self.app = dict(
            id="sample-one",
            version=1,
            data=dict(
                name="Synthetic app",
                job="Improve app activation",
                locale="en-US",
                private_marker="DO_NOT_EXPORT_THIS_MARKER",
            ),
        )
        self.operations = catalog()["operations"]

    def test_compact_default_and_exact_on_demand_profile_with_current_hash(self):
        base = discovery(self.app)
        self.assertNotIn("specialist", base)
        self.assertEqual(base["specialist_profiles"], index())
        self.assertLess(len(json.dumps(index())), 500)
        value = discovery(self.app, "meta_media_buyer")
        role = value["specialist"]
        self.assertEqual(role["app_hash"], digest(self.app["data"]))
        self.assertEqual(role["manifest_version"], 1)
        self.assertEqual(role["contract_sha256"], digest({k: v for k, v in role.items() if k != "contract_sha256"}))
        self.assertEqual(value["contract_sha256"], digest({k: v for k, v in value.items() if k != "contract_sha256"}))
        self.assertNotIn("DO_NOT_EXPORT_THIS_MARKER", json.dumps(value))
        self.assertFalse(role["authority"]["execution_authority"])
        self.assertEqual(role["authority"]["additional_operations"], [])
        self.assertEqual(role["authority"]["automatic_spend_minor"], 0)
        self.assertIsNone(role["owner_report"]["unknown_numbers"])

    def test_catalog_operations_and_actual_campaign_adapter_match(self):
        from pathlib import Path

        role = contract(self.app, self.operations)
        for name, rule in role["operations"].items():
            self.assertEqual(rule["effect"], self.operations[name]["effect"])
        source = Path("mission_control/campaign_execution.py").read_text(encoding="utf-8")
        current = role["capabilities"]["implemented"]
        for field in ("campaign_objective", "optimization_goal", "billing_event"):
            self.assertIn(current[field], source)
        self.assertEqual(current["publisher_platforms"], ["facebook"])
        self.assertTrue(any("Advantage+" in v for v in role["capabilities"]["implementation_required"]))
        broken = copy.deepcopy(self.operations)
        del broken["campaign.pause"]
        with self.assertRaises(Invalid):
            contract(self.app, broken)

    def test_no_network_calls_determinism_and_changed_app_or_rules_invalidate(self):
        start = time.perf_counter()
        with patch("socket.socket") as network:
            first = contract(self.app, self.operations)
            for _ in range(50):
                self.assertEqual(contract(self.app, self.operations), first)
            network.assert_not_called()
        self.assertLess(time.perf_counter() - start, 5)
        changed = dict(self.app, version=2, data=dict(self.app["data"], job="Different objective"))
        self.assertNotEqual(contract(changed, self.operations)["contract_sha256"], first["contract_sha256"])
        altered = copy.deepcopy(self.operations)
        altered["report.read"]["effect"] = "CHANGED"
        self.assertNotEqual(contract(self.app, altered)["contract_sha256"], first["contract_sha256"])

    def test_exact_selector_and_fixed_transport_reject_injection_before_io(self):
        for bad in (None, True, {}, [], 1, "", "META_MEDIA_BUYER", "meta_media_buyer&approved=true", "../profile"):
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                selector(bad)
            with self.assertRaises(Invalid):
                request_data(dict(app_id="sample-one", operation="operations.read", input=dict(profile=bad)))
        data = request_data(
            dict(app_id="sample-one", operation="operations.read", input=dict(profile="meta_media_buyer"))
        )
        self.assertEqual(
            data, dict(method="GET", path="/api/apps/sample-one/agent-operations?profile=meta_media_buyer", body=None)
        )
        with self.assertRaises(Invalid):
            request_data(
                dict(
                    app_id="sample-one",
                    operation="operations.read",
                    input=dict(profile="meta_media_buyer", approved=True),
                )
            )

    def test_decisions_and_reports_preserve_evidence_and_recovery(self):
        role = contract(self.app, self.operations)
        actions = {v["when"]: v["action"] for v in role["decisions"]}
        self.assertEqual(actions["intent_outcome_unknown"], "RECONCILE_RETAIN_LIABILITY")
        self.assertEqual(actions["unsupported_objective_or_mutation"], "PREPARE_IMPLEMENTATION_REQUIREMENT")
        self.assertEqual(actions["owner_stop_rule_met"], "GUARDED_PAUSE_AND_READBACK")
        fields = set(role["owner_report"]["required_fields"])
        self.assertTrue(
            {
                "denominators",
                "cohort_maturity",
                "attribution_window_and_model",
                "reserved_liability_minor",
                "unknown_metrics_and_reasons",
                "decision",
                "next_action",
            }
            <= fields
        )
        self.assertTrue(any("100000" in s and "AND" in s and "UGC" in s for s in role["buying_discipline"]))
        self.assertTrue(all(s["observed_on"] == "2026-11-04" for s in role["sources"]))
