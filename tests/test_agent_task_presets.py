"""Real catalog parity and unchanged server grant validation for owner presets."""

from datetime import datetime, timedelta, timezone
import json
import subprocess
import unittest

from mission_control.agent_grants import issue_data
from mission_control.common import Invalid
from mission_control.meta_media_buyer import contract
from mission_control.operation_catalog import OPERATIONS


def ui_profiles():
    code = "const fs=require('node:fs'),m={exports:{}};new Function('module',fs.readFileSync('./mission_control/static/agent-control.js','utf8'))(m);process.stdout.write(JSON.stringify(m.exports.taskProfiles));"
    result = subprocess.run(["node", "-e", code], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


class OwnerTaskPresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ui_profiles()

    def test_every_fixed_name_effect_matches_the_real_catalog(self):
        self.assertEqual(set(self.profiles), {"research", "organic", "meta"})
        for profile, definition in self.profiles.items():
            self.assertTrue(definition["operations"], profile)
            for name, effect in definition["operations"].items():
                self.assertIn(name, OPERATIONS, f"{profile}: missing {name}")
                self.assertEqual(OPERATIONS[name]["effect"], effect, f"{profile}: changed effect for {name}")

    def test_research_is_fixed_read_only_operation_set(self):
        allowed = {
            "READ_PRIVATE_LOCAL_DATA",
            "READ_LOCAL_POLICY",
            "READ_PRIVATE_EXECUTION_PLAN",
            "READ_PRIVATE_LOCAL_ARTIFACT",
            "READ_OWNED_PROVIDER_STATUS",
        }
        operations = self.profiles["research"]["operations"]
        self.assertGreaterEqual(len(operations), 10)
        for name, effect in operations.items():
            self.assertIn(effect, allowed)
            self.assertFalse(name.startswith(("native.queue", "editor.queue")))
        self.assertFalse(
            any(
                effect.startswith(("WRITE_", "QUEUE_", "PUBLISH_", "SPEND_", "RENDER_"))
                for effect in operations.values()
            )
        )

    def test_organic_and_meta_contracts_cover_supported_specialists_without_auto_authority(self):
        organic = self.profiles["organic"]["operations"]
        self.assertTrue(
            {
                "discovery.collect",
                "discovery.review",
                "creative.brief.save",
                "hypit.plan",
                "hypit.queue",
                "editor.edit",
                "editor.queue",
                "organic-video.policy-reserve",
                "organic-video.policy-admit",
                "organic-video.intent-create",
                "organic-video.intent-execute",
                "report.read",
            }
            <= set(organic)
        )
        meta = self.profiles["meta"]["operations"]
        specialist = contract({"id": "synthetic", "version": 1, "data": {}}, OPERATIONS)
        self.assertTrue(set(specialist["operations"]) <= set(meta))
        self.assertFalse(specialist["authority"]["execution_authority"])
        self.assertEqual(specialist["authority"]["automatic_spend_minor"], 0)

    def test_existing_issue_validation_still_accepts_explicit_grant_and_rejects_invalid_scope(self):
        now = datetime.now(timezone.utc)
        valid = {
            "agent_id": "agent-one",
            "manifest_version": 1,
            "operations": ["growth.read"],
            "expires": (now + timedelta(hours=1)).isoformat(),
            "max_calls": 20,
        }
        issue_data(valid, now)
        for patch in (
            {"operations": ["missing.operation"]},
            {"operations": []},
            {"max_calls": 0},
            {"max_calls": 10001},
        ):
            with self.subTest(patch=patch), self.assertRaises(Invalid):
                issue_data({**valid, **patch}, now)


if __name__ == "__main__":
    unittest.main()
