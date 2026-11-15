"""Actual isolated SQLite readiness facts, scope closure and secret-free projection."""

from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from mission_control.automation_requirements import (
    Readiness,
    WORKFLOWS,
    UNBUNDLED_OPERATIONS,
    workflow_catalog,
    verification,
)
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.operation_catalog import OPERATIONS
from mission_control.review_access import Access
from mission_control.store import Store
from tests.test_verified_review import OWNER, STRANGER

NOW = datetime.fromisoformat("2026-10-24T12:00:00+00:00")
PROFILE = "11111111-1111-4111-8111-111111111111"
ACCOUNT = "22222222-2222-4222-8222-222222222222"
FOREIGN = "33333333-3333-4333-8333-333333333333"
PRIVATE = "synthetic-private-marker-never-public"


class AutomationReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "state.sqlite", seed=False)
        for app in ("sample-one", "sample-two"):
            self.store.save_app(
                app, dict(name="Synthetic readiness app", release="build-1", locale="en-US", currency="USD")
            )
            Access(self.store).bootstrap(app, OWNER, dict(confirm_owner=True))
        self.profile()
        self.account()
        self.readiness = Readiness(self.store, clock=lambda: NOW)

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self, app="sample-one", identity=PROFILE, status="TESTED", stamp=NOW):
        data = dict(
            provider="codex",
            model="",
            capabilities=["campaign_plan", "original_copy"],
            credential_ref=PRIVATE,
            tool=dict(executable=PRIVATE, fingerprint="fixed-fingerprint"),
        )
        with connection(self.store.path) as db:
            db.execute(
                "INSERT OR REPLACE INTO agent_connections VALUES(?,?,?,?,?,?,?,?)",
                (
                    app,
                    identity,
                    1,
                    canonical(data),
                    status,
                    stamp.isoformat() if stamp else None,
                    NOW.isoformat(),
                    NOW.isoformat(),
                ),
            )

    def account(self, app="sample-one", identity=ACCOUNT, **changes):
        facts = dict(reported_scopes=["user.info.basic"], renewal="REFRESH_TOKEN")
        data = dict(
            facts=facts,
            destination=dict(id="synthetic-destination"),
            last_read_at=NOW.isoformat(),
            access_token=PRIVATE,
            unexpected=dict(refresh_token=PRIVATE),
        )
        row = dict(
            app_id=app,
            id=identity,
            provider="tiktok",
            config_version=1,
            version=1,
            subject_id="synthetic-subject",
            data=canonical(data),
            secret_ref=PRIVATE,
            status="CONNECTED_READ_TESTED",
            expires=NOW.timestamp() + 3600,
            refresh_expires=NOW.timestamp() + 7200,
            renewed_at=NOW.timestamp(),
            lease=None,
            lease_until=0,
            created=NOW.isoformat(),
            updated=NOW.isoformat(),
        )
        row.update(changes)
        with connection(self.store.path) as db:
            db.execute(
                "INSERT OR IGNORE INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                (app, "tiktok", 1, "{}", PRIVATE, "CONFIGURED", NOW.isoformat(), NOW.isoformat()),
            )
            db.execute(
                "INSERT OR REPLACE INTO social_connections VALUES(" + ",".join("?" for _ in row) + ")",
                tuple(row.values()),
            )

    def body(self, **changes):
        body = dict(
            agent_id="selected-agent",
            manifest_version=1,
            workflows=["local_evidence"],
            agent_connection_id=PROFILE,
            social_connection_ids=[],
        )
        return dict(body, **changes)

    def report(self, **changes):
        return self.readiness.report("sample-one", OWNER, self.body(**changes))

    def dump(self):
        with connection(self.store.path) as db:
            return "\n".join(db.iterdump())

    def test_inventory_maps_every_operation_and_rejects_catalog_drift(self):
        catalog = workflow_catalog()
        mapped = {name for row in catalog["workflows"].values() for name in row["operations"]}
        unbundled = set(catalog["unbundled_operations"])
        self.assertFalse(mapped & unbundled)
        self.assertEqual(mapped | unbundled, set(OPERATIONS))
        self.assertEqual(len(catalog["workflows"]), 13)
        self.assertEqual(
            catalog["workflows"]["release_delivery"],
            dict(
                name="Build and deployment delivery",
                operations=[],
                blockers=["RELEASE_EFFECT_OPERATION_COVERAGE_REQUIRED"],
            ),
        )
        catalog["workflows"]["local_evidence"]["operations"].clear()
        self.assertTrue(workflow_catalog()["workflows"]["local_evidence"]["operations"])
        with patch.dict(OPERATIONS, {"new.unmapped": dict(effect="NEW_EFFECT")}):
            with self.assertRaises(Invalid):
                workflow_catalog()
        with patch.dict(OPERATIONS, {}, clear=True):
            with self.assertRaises(Invalid):
                self.report()

    def test_new_operations_stay_explicitly_unbundled_and_owner_only_is_not_grantable(self):
        from mission_control.agent_grants import issue_data
        from mission_control.operation_catalog import catalog

        expected = {
            "creative.source.save",
            "creative.analysis.save",
            "creative.profile.save",
            "creative.requirement.save",
            "creative.brief.save",
            "creative.batch.plan",
            "creative.batch.create",
            "creative.batch.list",
            "creative.batch.cancel",
            "handoff.create",
            "handoff.resume",
            "experiment.schedule",
            "experiment.schedule-run",
            "organic-video.claim",
            "organic-video.submit",
            "organic-video.policy-read",
            "organic-video.policy-reserve",
            "organic-video.policy-admit",
            "organic-video.workflow-prepare",
            "organic-video.intent-create",
            "organic-video.intent-read",
            "organic-video.intent-execute",
        }
        study_operations = {
            "observational-campaign.register",
            "observational-campaign.link",
            "observational-campaign.ingest",
            "observational-campaign.report",
            "observational-campaign.history",
            "observational-campaign.correct",
        }
        expected |= study_operations | {"packaging.editor-prepare"}
        self.assertEqual(set(UNBUNDLED_OPERATIONS), expected)
        for name in study_operations:
            self.assertEqual(UNBUNDLED_OPERATIONS[name], "local_evidence")
        bundled = {name for row in WORKFLOWS.values() for name in row["operations"]}
        self.assertFalse(expected & bundled)
        for name in ("organic-video.claim", "organic-video.submit"):
            self.assertEqual(UNBUNDLED_OPERATIONS[name], "viral_discovery")
        self.assertEqual(WORKFLOWS["viral_discovery"]["operations"], [])
        owner_only = {"experiment.schedule", "experiment.schedule-run"}
        self.assertEqual({name for name, group in UNBUNDLED_OPERATIONS.items() if group == "OWNER_ONLY"}, owner_only)
        self.assertTrue((expected - owner_only).issubset(catalog()["operations"]))
        self.assertFalse(owner_only & set(catalog()["operations"]))
        for name in expected:
            body = dict(
                agent_id="fixture",
                manifest_version=1,
                operations=[name],
                expires=(NOW + timedelta(hours=1)).isoformat(),
                max_calls=1,
            )
            if name in owner_only:
                with self.subTest(name=name), self.assertRaises(Invalid):
                    issue_data(body, NOW)
            else:
                issue_data(body, NOW)
        for changed in ({"workspace.read": "local_evidence"}, {"handoff.create": "UNKNOWN_WORKFLOW"}):
            with self.subTest(changed=changed), patch.dict(UNBUNDLED_OPERATIONS, changed), self.assertRaises(Invalid):
                workflow_catalog()
        with patch.dict(UNBUNDLED_OPERATIONS, {}, clear=True), self.assertRaises(Invalid):
            workflow_catalog()

    def test_native_media_inventory_is_explicit_and_standing_remains_blocked(self):
        from mission_control.ios_automation import native_blockers

        operations = {
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
        }
        workflow = workflow_catalog()["workflows"]["video_authoring_editing"]
        self.assertEqual(
            {name for name in workflow["operations"] if name.startswith(("ios.scene.", "ios.timeline."))}, operations
        )
        self.assertIn("COMPLETE_AGENT_AND_HUMAN_EDITOR_REQUIRED", workflow["blockers"])
        self.assertEqual(
            native_blockers({"workflows": ["video_authoring_editing"]}),
            [{"workflow": "video_authoring_editing", "reason": "NATIVE_WORKFLOW_ADAPTER_REQUIRED"}],
        )

    def test_native_workflow_maps_track_the_shared_catalog_exactly(self):
        from mission_control.ios_automation import NATIVE_WORKFLOWS, native_blockers

        for name, approved in NATIVE_WORKFLOWS.items():
            with self.subTest(workflow=name):
                self.assertEqual(sorted(approved), sorted(WORKFLOWS[name]["operations"]))
        self.assertEqual(native_blockers({"workflows": ["local_evidence"]}), [])
        self.assertEqual(native_blockers({"workflows": ["native_video_authoring"]}), [])

    def test_inference_profile_is_not_authority_and_report_performs_no_writes_or_tools(self):
        before = self.dump()
        with (
            patch("mission_control.credential_vault.Vault.get", side_effect=AssertionError("No vault read")),
            patch("mission_control.agent_process.capture", side_effect=AssertionError("No process")),
            patch("urllib.request.urlopen", side_effect=AssertionError("No network")),
        ):
            result = self.report()
        inventory = result["inventory"]
        self.assertEqual(inventory["inference"]["status"], "TESTED_FRESH")
        self.assertEqual(inventory["scope_status"], "READY_FOR_SCOPE_REVIEW")
        self.assertEqual(inventory["activation"], "NOT_PERFORMED")
        self.assertFalse(inventory["grants_issued"])
        self.assertEqual(result["inventory_sha256"], digest(inventory))
        self.assertEqual(inventory["inference"]["quota"], "UNKNOWN")
        self.assertEqual(inventory["inference"]["account_identity"], "NOT_INDEPENDENTLY_VERIFIED")
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertEqual(before, self.dump())
        self.assertEqual(result["inventory_sha256"], self.report()["inventory_sha256"])

    def test_configured_stale_future_missing_and_disconnected_are_not_fresh(self):
        cases = [
            ("CONFIGURED_UNTESTED", NOW, "CONFIGURED_UNTESTED"),
            ("DISCONNECTED", NOW, "DISCONNECTED"),
            ("NEEDS_ATTENTION", NOW, "NEEDS_ATTENTION"),
            ("TESTED", None, "NOT_VERIFIED"),
            ("TESTED", NOW - timedelta(hours=24, microseconds=1), "STALE"),
            ("TESTED", NOW + timedelta(microseconds=1), "INVALID_VERIFICATION"),
            ("TESTED", NOW - timedelta(hours=24), "TESTED_FRESH"),
        ]
        for status, stamp, expected in cases:
            with self.subTest(status=status, stamp=stamp):
                self.profile(status=status, stamp=stamp)
                inventory = self.report()["inventory"]
                self.assertEqual(inventory["inference"]["status"], expected)
                self.assertEqual(inventory["scope_status"] == "READY_FOR_SCOPE_REVIEW", expected == "TESTED_FRESH")
        self.assertEqual(self.report(agent_connection_id=None)["inventory"]["inference"]["status"], "MISSING")
        self.assertEqual(verification("ambiguous", NOW), "INVALID_VERIFICATION")
        self.assertEqual(verification("2026-10-24T12:00:00", NOW), "INVALID_VERIFICATION")
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_connections SET last_test='broken-verification-time'")
        invalid = self.report()["inventory"]["inference"]
        self.assertEqual(invalid["status"], "INVALID_VERIFICATION")
        self.assertIsNone(invalid["fresh_until"])

    def test_owner_app_version_and_selected_connection_scopes_are_enforced(self):
        with self.assertRaises(PermissionError):
            self.readiness.report("sample-one", STRANGER, self.body())
        Access(self.store).save(
            "sample-one", OWNER, STRANGER, dict(login=STRANGER["login"], role="MAKER", status="ACTIVE", version=None)
        )
        with self.assertRaises(PermissionError):
            self.readiness.report("sample-one", STRANGER, self.body())
        self.profile(app="sample-two", identity=FOREIGN)
        self.account(app="sample-two", identity=FOREIGN)
        for body in (
            self.body(manifest_version=2),
            self.body(agent_connection_id=FOREIGN),
            self.body(social_connection_ids=[FOREIGN]),
        ):
            with self.assertRaises(Invalid):
                self.readiness.report("sample-one", OWNER, body)
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED' WHERE app_id='sample-one'")
        with self.assertRaises(PermissionError):
            self.report()

    def test_selection_rejects_unknown_workflows_duplicates_hidden_authority_and_bad_ids(self):
        cases = [
            self.body(workflows=[]),
            self.body(workflows=["new-workflow"]),
            self.body(workflows=["local_evidence"] * 2),
            self.body(workflows=[{}]),
            self.body(agent_connection_id="../../credential"),
            self.body(agent_id="--shell"),
            self.body(social_connection_ids=[ACCOUNT] * 2),
            self.body(social_connection_ids=[ACCOUNT] * 21),
            self.body(manifest_version=True),
            dict(self.body(), token=PRIVATE),
            self.body(social_connection_ids="all"),
        ]
        for body in cases:
            with self.subTest(body=body), self.assertRaises(Invalid):
                self.readiness.report("sample-one", OWNER, body)

    def test_social_account_identity_scopes_and_expiry_do_not_imply_publication(self):
        result = self.report(workflows=["social_publish"], social_connection_ids=[ACCOUNT])
        account = result["inventory"]["accounts"][0]
        self.assertEqual(account["subject_id"], "synthetic-subject")
        self.assertEqual(account["destination_id"], "synthetic-destination")
        self.assertEqual(account["reported_scopes"], ["user.info.basic"])
        self.assertEqual(account["status"], "TESTED_FRESH")
        self.assertTrue(account["publishing_implemented"])
        self.assertEqual(account["publication_connection_provider"], "tiktok")
        self.assertIn("PUBLICATION_ADAPTER_REQUIRED", result["inventory"]["workflows"][0]["blockers"])
        self.assertNotIn(PRIVATE, json.dumps(result))
        for changes, expected in [
            ({"expires": NOW.timestamp()}, "EXPIRED"),
            ({"expires": None}, "EXPIRY_UNKNOWN"),
            ({"lease": PRIVATE}, "RENEWING"),
            ({"status": "DISCONNECTED"}, "DISCONNECTED"),
        ]:
            self.account(**changes)
            self.assertEqual(
                self.report(social_connection_ids=[ACCOUNT])["inventory"]["accounts"][0]["status"], expected
            )

    def test_organic_publication_lists_implemented_channels_without_granting_approval(self):
        for provider in ("facebook", "instagram", "tiktok", "youtube", "linkedin"):
            self.account(provider=provider)
            with connection(self.store.path) as db:
                db.execute(
                    "INSERT OR IGNORE INTO social_configs VALUES(?,?,?,?,?,?,?,?)",
                    ("sample-one", provider, 1, "{}", PRIVATE, "CONFIGURED", NOW.isoformat(), NOW.isoformat()),
                )
            before = self.dump()
            result = self.report(workflows=["organic_publication"], social_connection_ids=[ACCOUNT])
            inventory = result["inventory"]
            account = inventory["accounts"][0]
            self.assertTrue(account["publishing_implemented"])
            self.assertEqual(
                account["publication_connection_provider"], "facebook" if provider == "instagram" else provider
            )
            workflow = inventory["workflows"][0]
            self.assertEqual(workflow["status"], "BLOCKED")
            self.assertIn("EXACT_CURRENT_OWNER_PUBLICATION_APPROVAL_REQUIRED", workflow["blockers"])
            self.assertIn("Publish an approved post", workflow["repair"])
            self.assertEqual("PUBLICATION_CONNECTION_REQUIRED" in workflow["blockers"], provider == "instagram")
            self.assertFalse(inventory["grants_issued"])
            self.assertNotIn(PRIVATE, json.dumps(result))
            self.assertEqual(before, self.dump())

    def test_organic_publication_requires_every_selected_account_to_be_fresh(self):
        missing = self.report(workflows=["organic_publication"])["inventory"]["workflows"][0]
        self.assertIn("FRESH_DESTINATION_ACCOUNT_REQUIRED", missing["blockers"])
        self.account(expires=NOW.timestamp())
        self.account(identity=FOREIGN)
        expired = self.report(workflows=["organic_publication"], social_connection_ids=[ACCOUNT, FOREIGN])["inventory"][
            "workflows"
        ][0]
        self.assertIn("FRESH_DESTINATION_ACCOUNT_REQUIRED", expired["blockers"])

    def test_social_state_unknown_scopes_renewal_state_stale_read_and_provider_changes(self):
        with connection(self.store.path) as db:
            data = json.loads(db.execute("SELECT data FROM social_connections").fetchone()[0])
        for changes, expected in [
            ({"facts": dict(reported_scopes=None)}, "SCOPES_UNKNOWN"),
            ({"last_read_at": (NOW - timedelta(hours=25)).isoformat()}, "STALE"),
            ({"last_read_at": (NOW + timedelta(hours=1)).isoformat()}, "INVALID_VERIFICATION"),
        ]:
            self.account(data=canonical(dict(data, **changes)))
            self.assertEqual(
                self.report(social_connection_ids=[ACCOUNT])["inventory"]["accounts"][0]["status"], expected
            )
            if expected == "SCOPES_UNKNOWN":
                self.assertEqual(
                    self.report(social_connection_ids=[ACCOUNT])["inventory"]["accounts"][0]["renewal"], "UNKNOWN"
                )
        self.account()
        with connection(self.store.path) as db:
            db.execute("UPDATE social_configs SET version=2")
        self.assertEqual(
            self.report(social_connection_ids=[ACCOUNT])["inventory"]["accounts"][0]["status"], "PROVIDER_SETUP_CHANGED"
        )

    def test_inventory_hash_changes_with_private_revision_account_config_and_owner_role(self):
        previous = self.report(social_connection_ids=[ACCOUNT])["inventory_sha256"]
        statements = [
            "UPDATE agent_connections SET version=version+1",
            "UPDATE social_configs SET version=version+1",
            "UPDATE operator_roles SET version=version+1 WHERE app_id='sample-one'",
            "UPDATE social_connections SET secret_ref='synthetic-rotated-reference'",
            "UPDATE agent_connections SET data=json_set(data,'$.tool.fingerprint','changed')",
        ]
        for statement in statements:
            with connection(self.store.path) as db:
                db.execute(statement)
            current = self.report(social_connection_ids=[ACCOUNT])["inventory_sha256"]
            self.assertNotEqual(previous, current)
            previous = current

    def test_workflow_states_preserve_every_incomplete_parent_workflow_as_blocked(self):
        result = self.report(workflows=list(WORKFLOWS))["inventory"]
        self.assertEqual(len(result["workflows"]), len(WORKFLOWS))
        self.assertEqual(result["scope_status"], "BLOCKED")
        for row in result["workflows"]:
            if row["id"] not in (
                "local_evidence",
                "experiment_preparation",
                "pipeline_preparation",
                "native_screen_render",
            ):
                self.assertTrue(row["blockers"], row)
                self.assertEqual(row["status"], "BLOCKED")
        social = next(row for row in result["workflows"] if row["id"] == "social_publish")
        self.assertIn("FRESH_DESTINATION_ACCOUNT_REQUIRED", social["blockers"])
        release = next(row for row in result["workflows"] if row["id"] == "release_delivery")
        self.assertEqual(release["operations"], [])
        self.assertEqual(release["status"], "BLOCKED")
        self.assertIn("RELEASE_EFFECT_OPERATION_COVERAGE_REQUIRED", release["blockers"])

    def test_object_field_and_malformed_public_projection_do_not_return_secret_objects(self):
        malformed = [
            "not JSON",
            "[]",
            canonical(dict(provider={}, model="")),
            canonical(dict(provider="codex", capabilities=PRIVATE, model="")),
            canonical(dict(provider="codex", model={"api_key": PRIVATE})),
        ]
        for data in malformed:
            with connection(self.store.path) as db:
                db.execute("UPDATE agent_connections SET data=?", (data,))
            with self.assertRaises(Invalid) as error:
                self.report()
            self.assertNotIn(PRIVATE, str(error.exception))
        self.profile()
        for field in ("facts", "destination"):
            self.account(data=canonical({field: [PRIVATE]}))
            with self.assertRaises(Invalid):
                self.report(social_connection_ids=[ACCOUNT])


if __name__ == "__main__":
    unittest.main()
