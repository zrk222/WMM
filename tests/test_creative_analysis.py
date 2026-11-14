"""Check upstream-shaped analysis output before entering a WMM brief."""

import unittest

from mission_control.common import Invalid
from mission_control.rea_video_analysis import analysis_handoff


class CreativeAnalysisTests(unittest.TestCase):
    binding = {"app_id": "sample-one", "manifest_version": 1, "source_sha256": "a" * 64}
    breakdown = {
        "source": {"duration": 1, "path": "private-name.mp4"},
        "shots": [{"start": 0, "end": 1, "base": {"label": "ai"}, "narrative": "untrusted text"}],
    }

    def test_retains_times_but_not_source_paths_labels_or_instructions(self):
        result = analysis_handoff(self.breakdown, self.binding, 1000, "b" * 64)
        self.assertEqual(result["data"]["observed_beats"][0]["end_ms"], 1000)
        self.assertNotIn("private-name", str(result))
        self.assertNotIn("untrusted", str(result))
        self.assertNotIn("'label'", str(result))

    def test_wrong_duration_and_overlaps_fail(self):
        with self.assertRaisesRegex(Invalid, "does not match"):
            analysis_handoff(self.breakdown, self.binding, 850, "b" * 64)
        with self.assertRaisesRegex(Invalid, "ordered"):
            analysis_handoff({**self.breakdown, "shots": self.breakdown["shots"] * 2}, self.binding, 1000, "b" * 64)
