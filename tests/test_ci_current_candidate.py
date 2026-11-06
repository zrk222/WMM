"""Workflow routing checks preserve the reviewed full job definitions."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
# The browser profile provisions Chromium and the local render runtime and runs
# both owner-bound OneSignal journeys, creative batches and organic research.
# All eight backend shards and the native/package job definitions are retained.
BASELINES = {".github/workflows/checks.yml":"393471e00a0d031368e533ecfbb4f73eb09b29ea0f41cb5f021f0496e7bd1af2",".github/workflows/platform-checks.yml":"8f2b207e65ac21434b6476c18d7c8d1e4da90315f8f6fd9f64eb6ca59cb2eb2a",".github/workflows/desktop-packages.yml":"c9dd8f316a7660ef7baa92c46628fe49c948b455ea7f87f45fac866b6c323e45"}
GROUP = "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"

def job_digest(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    raw = json.dumps(json.loads(text)["jobs"], separators=(",", ":"), ensure_ascii=False) if path.endswith("platform-checks.yml") else text[text.index("\njobs:"):]
    return hashlib.sha256(raw.encode()).hexdigest()

class CurrentCandidateCITests(unittest.TestCase):
    def test_browser_profile_keeps_batch_and_both_onesignal_journeys(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
        browser = text.split("  browser:\n", 1)[1].split("  windows:\n", 1)[0]
        self.assertIn("timeout-minutes: 45", browser)
        self.assertIn("WMM_BROWSER_TEST_PROFILE: '1'", browser)
        self.assertIn("python -m unittest tests.test_creative_batches_browser tests.test_onesignal_ui_browser tests.test_onesignal_browser_integration tests.test_organic_research_browser tests.test_market_research_browser tests.test_organic_policy_gui_browser -v", browser)
        self.assertIn("python -m unittest tests.test_insights_history_browser tests.test_observational_campaign_browser -v", browser)
        self.assertIn("python tools/test_owner_onboarding_browser.py", browser)
        self.assertIn("python tools/test_campaign_monitor_browser.py", browser)
        self.assertIn("python tools/test_organic_taste_browser.py", browser)
        self.assertIn("python tools/test_goal_packet_history_browser.py", browser)
        self.assertIn("python tools/test_weekly_review_actions_browser.py", browser)
        self.assertIn("python tools/test_client_dashboard_browser.py", browser)
        self.assertIn("python tools/test_authority_expiry_browser.py", browser)
        self.assertIn("python tools/test_agent_task_presets_browser.py", browser)
        self.assertEqual(text.count('python -m pip install --only-binary :all: -r docs/requirements-auth.txt'), 3)

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
