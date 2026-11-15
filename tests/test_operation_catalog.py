"""Closed catalog and route construction are validated before transport."""

import unittest
from mission_control.common import Invalid, digest
from mission_control.operation_catalog import (
    catalog,
    descriptor,
    path_segment,
    exact_keys,
    local_constraints,
    request_data,
    OPERATIONS,
)


class OperationCatalogTests(unittest.TestCase):
    def test_catalog_is_fresh_hash_bound_and_honest_about_unfinished_authority(self):
        value = catalog()
        self.assertEqual(
            value["catalog_sha256"], digest({key: item for key, item in value.items() if key != "catalog_sha256"})
        )
        self.assertFalse(value["full_agent_operation"])
        self.assertEqual(value["operations"]["media.sources"]["method"], "GET")
        self.assertEqual(value["operations"]["media.sources"]["suffix"], "/media/sources")
        self.assertTrue(
            {
                "creative.batch.plan",
                "creative.batch.create",
                "creative.batch.list",
                "creative.batch.cancel",
                "handoff.create",
                "handoff.resume",
            }.issubset(value["operations"])
        )
        reviewed = {
            "creative.source.save",
            "creative.analysis.save",
            "creative.profile.save",
            "creative.requirement.save",
            "creative.brief.save",
        }
        self.assertEqual(set(value["review"]["mandatory_operations"]), reviewed)
        for name in reviewed:
            self.assertEqual(value["operations"][name]["required"], ["data"])
            self.assertEqual(value["operations"][name]["optional"], ["id", "version"])
        expected_effects = {
            "campaign.history": "READ_PRIVATE_LOCAL_DATA",
            "campaign.status": "READ_PRIVATE_LOCAL_DATA",
            "campaign.publish": "PUBLISH_WITH_STANDING_CAMPAIGN_AUTHORITY",
            "campaign.ad-launch": "SPEND_WITH_STANDING_CAMPAIGN_AUTHORITY",
            "campaign.pause": "PAUSE_OWNED_EXTERNAL_CAMPAIGN",
            "campaign.reconcile": "READ_OWNED_PROVIDER_STATUS",
            "hypit.plan": "READ_PRIVATE_EXECUTION_PLAN",
            "hypit.reuse": "READ_PRIVATE_LOCAL_ARTIFACT",
        }
        self.assertEqual(
            {name for name in value["operations"] if name.startswith("campaign.")},
            {name for name in expected_effects if name.startswith("campaign.")},
        )
        for name, effect in expected_effects.items():
            self.assertEqual(value["operations"][name]["effect"], effect)
            self.assertEqual(value["operations"][name]["method"], "POST")
        self.assertEqual(value["operations"]["report.read"]["effect"], "READ_PRIVATE_LOCAL_DATA")
        native_media = {name for name in value["operations"] if name.startswith(("ios.scene.", "ios.timeline."))}
        self.assertEqual(
            native_media,
            {
                "ios.scene.projects",
                "ios.scene.read",
                "ios.scene.save",
                "ios.scene.plan",
                "ios.scene.start",
                "ios.scene.inspect",
                "ios.scene.cancel",
                "ios.timeline.queue",
                "ios.timeline.inspect",
                "ios.timeline.cancel",
            },
        )
        for action in ("history", "read", "save", "reconcile"):
            operation = value["operations"]["packaging." + action]
            self.assertEqual(operation["method"], "POST")
            self.assertEqual(operation["suffix"], "/packaging/" + action)
            expected = "WRITE_LOCAL_PLAN" if action == "save" else "READ_PRIVATE_LOCAL_DATA"
            self.assertEqual(operation["effect"], expected)
        value["operations"]["workspace.read"]["suffix"] = "/arbitrary"
        self.assertEqual(catalog()["operations"]["workspace.read"]["suffix"], "")
        self.assertIn("human_approval", value["denied"])

    def test_external_video_collector_never_exposes_owner_preparation_or_tool_authority(self):
        from mission_control.automation_requirements import workflow_catalog

        operations = catalog()["operations"]
        self.assertNotIn("organic-video.prepare", operations)
        self.assertEqual(
            {name for name in operations if name.startswith("organic-video.")},
            {
                "organic-video.claim",
                "organic-video.submit",
                "organic-video.policy-read",
                "organic-video.policy-reserve",
                "organic-video.policy-admit",
                "organic-video.workflow-prepare",
                "organic-video.intent-create",
                "organic-video.intent-read",
                "organic-video.intent-execute",
            },
        )
        for suffix in ("policy-create", "policy-revoke", "intent-reconcile", "intake", "prepare"):
            self.assertNotIn("organic-video." + suffix, operations)
        for action, fields in (("claim", ["task_id", "task_hash"]), ("submit", ["task_id", "result"])):
            rule = operations["organic-video." + action]
            self.assertEqual(rule["required"], fields)
            self.assertEqual(rule["effect"], "WRITE_LOCAL_EVIDENCE")
            self.assertEqual(rule["suffix"], "/organic-video/" + action)
            self.assertEqual(rule["optional"], [])
        workflows = workflow_catalog()
        self.assertEqual(workflows["workflows"]["viral_discovery"]["operations"], [])
        self.assertEqual(
            set(workflows["workflows"]["organic_publication"]["operations"]),
            {"publication.list", "publication.get", "publication.draft", "publication.prepare", "publication.execute"},
        )
        self.assertEqual(
            workflows["workflows"]["organic_publication"]["blockers"],
            ["EXACT_CURRENT_OWNER_PUBLICATION_APPROVAL_REQUIRED"],
        )
        for action in ("claim", "submit"):
            self.assertEqual(workflows["unbundled_operations"]["organic-video." + action], "viral_discovery")

    def test_path_segment_rejects_encoded_query_traversal_and_host_syntax(self):
        self.assertEqual(path_segment("sample-one"), "sample-one")
        for value in (
            None,
            True,
            "../other",
            "one/other",
            "one?approve=true",
            "%2fother",
            "https://other",
            "Upper",
            "one#x",
            "one_2",
            "one\r\nHost:x",
        ):
            with self.subTest(value=value), self.assertRaises(Invalid):
                path_segment(value)

    def test_request_data_resolves_every_catalog_route_and_closed_input(self):
        for name, rule in OPERATIONS.items():
            body = {key: "fixture" for key in rule["required"]}
            if name == "billing.save":
                body["kind"] = "billing"
            if name == "experiment.action":
                body["operation"] = "observe"
            if name == "evidence.save":
                body["kind"] = "measurement"
            if name == "pipeline.prepare":
                body = dict(action="pipeline", data=dict(stage=0), request_key="synthetic-key")
            envelope = dict(app_id="sample-one", operation=name, input=body)
            if rule["resource"]:
                envelope["resource_id"] = "resource-one"
            value = request_data(envelope)
            self.assertEqual(value["method"], rule["method"])
            self.assertTrue(value["path"].startswith("/api/apps/sample-one"))
            self.assertNotIn("{resource_id}", value["path"])
            with self.assertRaises(Invalid):
                request_data(dict(envelope, input=dict(body, approve=True)))

    def test_unknown_approval_and_resource_injection_are_denied(self):
        base = dict(app_id="sample-one", operation="workspace.read", input={})
        for name in (
            "human.approve",
            "identity.login",
            "provider.execute",
            "spend",
            "credentials.save",
            "/api/identity/login",
        ):
            with self.assertRaises(Invalid):
                request_data(dict(base, operation=name))
        for extra in ({"resource_id": "other"}, {"url": "http://external.example"}, {"approved": True}):
            with self.assertRaises(Invalid):
                request_data(dict(base, **extra))
        with self.assertRaises(Invalid):
            request_data(dict(base, operation="experiment.evaluate"))
        with self.assertRaises(Invalid):
            request_data(dict(base, operation="experiment.evaluate", resource_id="../other"))
        with self.assertRaises(Invalid):
            request_data(
                dict(
                    base,
                    operation="billing.save",
                    input=dict(id="a", manifest_version=1, kind="connection", title="x", source="x", data={}),
                )
            )
        with self.assertRaises(Invalid):
            local_constraints("experiment.action", dict(operation="approve"))
        self.assertEqual(descriptor("GET", "", "READ")["required"], [])
        with self.assertRaises(Invalid):
            exact_keys([], ())
