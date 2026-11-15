"""Every host receives the same current, non-authorizing operation contract."""

import unittest
from copy import deepcopy
from mission_control.agent_workflow_protocol import build
from mission_control.operation_catalog import catalog
from mission_control.marketing_agent_manifest import operating_manifest
from mission_control.personal_agent_profiles import operating_guide, PROFILES
from mission_control.common import digest


class AgentWorkflowProtocolTests(unittest.TestCase):
    def test_every_current_operation_retains_its_exact_transport_contract(self):
        source = catalog()
        result = build(source)
        self.assertEqual(result["operations"], sorted(source["operations"]))
        self.assertIn("implemented_catalog.operations", result["operation_contracts"])
        self.assertEqual(result["operation_count"], len(source["operations"]))
        for workflow in result["workflows"].values():
            self.assertTrue(set(workflow["operations"]) <= set(source["operations"]))
            self.assertFalse(workflow["automatic_chain"])
        self.assertEqual(result["authority"], "GUIDANCE_ONLY_NO_EXECUTION_AUTHORITY")

    def test_copy_isolation_and_changed_catalog_invalidate_protocol_hash(self):
        source = catalog()
        first = build(source)
        baseline = first["protocol_sha256"]
        first["operations"].clear()
        self.assertTrue(source["operations"])
        self.assertEqual(build(source)["protocol_sha256"], baseline)
        changed = deepcopy(source)
        changed["operations"]["campaign.publish"]["required"].append("new_revision")
        self.assertNotEqual(build(changed)["protocol_sha256"], baseline)

    def test_missing_capability_is_visible_and_not_invented(self):
        source = catalog()
        source["operations"].pop("campaign.ad-launch")
        result = build(source)
        self.assertIn("campaign.ad-launch", result["workflows"]["campaign_delivery"]["unavailable"])
        self.assertNotIn("campaign.ad-launch", result["workflows"]["campaign_delivery"]["operations"])

    def test_all_named_and_generic_hosts_reference_one_bound_protocol(self):
        app = {"id": "sample-one", "version": 1, "data": {"name": "Synthetic app", "release": "build-1"}}
        policy = operating_manifest(app)
        result = operating_guide(app, policy, catalog())
        shared = result["workflow_protocol"]["protocol_sha256"]
        self.assertEqual({row["id"] for row in result["profiles"]}, {row["id"] for row in PROFILES})
        for row in result["profiles"]:
            self.assertEqual(row["workflow_protocol_ref"], shared)
            self.assertIn("route", row)
            self.assertIn("unknown", row)
            self.assertNotIn("workflow_protocol", row)  # No six-fold prompt duplication.
        self.assertEqual(result["other_hosts"]["workflow_protocol_ref"], shared)
        self.assertFalse(result["execution_authority"])
        self.assertFalse(result["connection_verified"])
        self.assertEqual(policy["supported_execution"]["spend_minor"], 0)
        self.assertIn("campaign.ad-launch", policy["supported_execution"]["provider_writes"])
        improvement = result["workflow_protocol"]["continuous_improvement"]
        self.assertEqual(improvement["evaluation"]["operation"], "experiment.evaluate")
        self.assertEqual(improvement["evaluation"]["result_field"], "iteration")
        self.assertEqual(set(improvement["decisions"]), {"COLLECT", "REPAIR", "STOP", "CONTINUE", "REVISE"})
        self.assertNotIn("continuous_improvement", policy["owner_operating_protocol"])
        self.assertEqual(result["scope"]["policy_sha256"], digest(policy))
        check = dict(result)
        check.pop("guide_sha256")
        self.assertEqual(digest(check), result["guide_sha256"])


if __name__ == "__main__":
    unittest.main()
