"""Exercise independent choices and exact-source handoffs."""

import unittest

from mission_control.common import Invalid
from mission_control.creative_toolchain import handoff, plan


class CreativeToolchainTests(unittest.TestCase):
    binding = {"app_id": "sample-one", "manifest_version": 2, "source_sha256": "1" * 64}
    analysis = {
        "duration_ms": 1000,
        "observed_beats": [{"start_ms": 0, "end_ms": 800, "text": "App screen appears."}],
        "interpretation": "Likely product proof; intent unverified.",
        "analyzer_revision": "2" * 40,
        "analyzer_sha256": "2" * 64,
    }
    variant = {
        "artifact_sha256": "3" * 64,
        "request_id": "provider-one",
        "reviewed": True,
        "rights_sha256": "4" * 64,
    }

    def test_all_tools_independent_and_no_effects(self):
        for hypit in (False, True):
            for rea in (False, True):
                for genjutsu in (False, True):
                    choices = {"hypit": hypit, "rea-video": rea, "genjutsu": genjutsu}
                    result = plan(choices, self.binding, {})
                    for engine, enabled in choices.items():
                        self.assertEqual(result["tools"][engine] != "OFF", enabled)
                    self.assertFalse(result["external_execution"])
                    self.assertFalse(result["publication"])

    def test_combined_handoffs_bind_exact_app_revision_and_source(self):
        choices: dict[str, bool] = {"hypit": True, "rea-video": True, "genjutsu": True}
        receipts = {
            "rea-video": handoff("rea-video", self.binding, self.analysis),
            "genjutsu": handoff("genjutsu", self.binding, self.variant),
        }
        result = plan(choices, self.binding, receipts)["tools"]
        self.assertEqual(result["rea-video"], "DRAFT_METADATA_MATCHES")
        self.assertEqual(result["genjutsu"], "DRAFT_METADATA_MATCHES")
        for drift in ({"app_id": "sample-two"}, {"manifest_version": 3}, {"source_sha256": "5" * 64}):
            result = plan(choices, {**self.binding, **drift}, receipts)["tools"]
            self.assertEqual(result["hypit"], "READY_FOR_EXISTING_WORKFLOW")
            self.assertEqual(result["rea-video"], "LOCAL_ANALYSIS_NEEDED")
            self.assertEqual(result["genjutsu"], "PROVIDER_APPROVAL_NEEDED")
        receipts["genjutsu"]["data"]["artifact_sha256"] = "6" * 64
        self.assertEqual(plan(choices, self.binding, receipts)["tools"]["genjutsu"], "PROVIDER_APPROVAL_NEEDED")

    def test_invalid_timestamps_and_unreviewed_variants(self):
        with self.assertRaisesRegex(Invalid, "within the clip"):
            handoff(
                "rea-video",
                self.binding,
                {**self.analysis, "observed_beats": [{"start_ms": 0, "end_ms": 1001, "text": "Clip"}]},
            )
        with self.assertRaisesRegex(Invalid, "Review"):
            handoff("genjutsu", self.binding, {**self.variant, "reviewed": False})
