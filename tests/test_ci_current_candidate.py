"""Workflow routing checks preserve the reviewed full job definitions."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The browser profile provisions Chromium and the local render runtime and runs
# both owner-bound OneSignal journeys alongside the existing creative batch suite.
# All eight backend shards and the native/package job definitions are retained.
BASELINES = {".github/workflows/checks.yml":"1a4db37787fdd39690ab21b035cba91c41648db62c960e6a210eb472b992955f",".github/workflows/platform-checks.yml":"8f2b207e65ac21434b6476c18d7c8d1e4da90315f8f6fd9f64eb6ca59cb2eb2a",".github/workflows/desktop-packages.yml":"e706a3cecaff27d02493a91b6e22b9b6719d435d16b7e0c47a2dbf9c45362349"}
GROUP = "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"

def job_digest(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    raw = json.dumps(json.loads(text)["jobs"], separators=(",", ":"), ensure_ascii=False) if path.endswith("platform-checks.yml") else text[text.index("\njobs:"):]
    return hashlib.sha256(raw.encode()).hexdigest()

class CurrentCandidateCITests(unittest.TestCase):
    def test_browser_profile_keeps_batch_and_both_onesignal_journeys(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
        browser = text.split("  browser:\n", 1)[1].split("  windows:\n", 1)[0]
        self.assertIn("WMM_BROWSER_TEST_PROFILE: '1'", browser)
        self.assertIn("python -m unittest tests.test_creative_batches_browser tests.test_onesignal_ui_browser tests.test_onesignal_browser_integration -v", browser)

    def test_full_job_definitions_and_test_matrices_are_preserved(self):
        for path, expected in BASELINES.items():
            with self.subTest(path=path):
                self.assertEqual(job_digest(path), expected)

    def test_feature_pr_and_main_push_remain_canonical_events(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
        events = text.split("on:\n", 1)[1].split("concurrency:", 1)[0]
        self.assertEqual(events.strip(), "push:\n    branches: [main]\n  pull_request:")

    def test_each_workflow_cancels_only_its_own_superseded_candidate(self):
        for path in BASELINES:
            text = (ROOT / path).read_text(encoding="utf-8")
            with self.subTest(path=path):
                if path.endswith("platform-checks.yml"):
                    self.assertEqual(json.loads(text)["concurrency"], {"group": GROUP, "cancel-in-progress": True})
                else:
                    self.assertIn("  group: " + GROUP + "\n  cancel-in-progress: true\n", text)

if __name__ == "__main__":
    unittest.main()
