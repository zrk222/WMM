"""Workflow routing checks preserve the reviewed full job definitions."""

import hashlib
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The browser profile provisions Chromium and the local render runtime and runs
# both owner-bound OneSignal journeys, creative batches, organic research and
# exact-approved publication with retained synthetic desktop/mobile evidence.
# All eight backend shards and the native/package job definitions are retained.
# One Ubuntu shard also runs the isolated native Secret Service acceptance.
BASELINES = {
    ".github/workflows/checks.yml": "3dc252440b5568f4ee53491534fb796427a94acf18bda8a4d5176e25d623bfc7",
    ".github/workflows/platform-checks.yml": "8f2b207e65ac21434b6476c18d7c8d1e4da90315f8f6fd9f64eb6ca59cb2eb2a",
    ".github/workflows/desktop-packages.yml": "f0aac774bb6117a0f8a60ae2ad681282ee537fcfcc9b0919cbe7a0df6f854541",
}
GROUP = "${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}"


def job_digest(path):
    text = (ROOT / path).read_text(encoding="utf-8")
    if path == ".github/workflows/checks.yml":
        gate = text.split("      - name: Enforce automatically enrolled source ratchets\n", 1)
        if len(gate) == 2:
            text = (
                gate[0]
                + "      - name: Install pinned runtime and formatter"
                + gate[1].split("      - name: Install pinned runtime and formatter", 1)[1]
            )
        text = text.replace("        with:\n          fetch-depth: 0\n", "", 1)
    raw = (
        json.dumps(json.loads(text)["jobs"], separators=(",", ":"), ensure_ascii=False)
        if path.endswith("platform-checks.yml")
        else text[text.index("\njobs:") :]
    )
    return hashlib.sha256(raw.encode()).hexdigest()


class CurrentCandidateCITests(unittest.TestCase):
    def test_browser_profile_keeps_batch_and_both_onesignal_journeys(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
        browser = text.split("  browser:\n", 1)[1].split("  windows:\n", 1)[0]
        self.assertIn("timeout-minutes: 45", browser)
        self.assertIn("WMM_BROWSER_TEST_PROFILE: '1'", browser)
        self.assertIn(
            "python -m unittest tests.test_creative_batches_browser tests.test_onesignal_ui_browser tests.test_onesignal_browser_integration tests.test_organic_research_browser tests.test_market_research_browser tests.test_organic_policy_gui_browser tests.test_publication_browser -v",
            browser,
        )
        self.assertIn("python -m unittest tests.test_automation_rules_browser -v", browser)
        self.assertIn("name: publication-browser-evidence", browser)
        self.assertIn("path: .factory/multichannel/browser/", browser)
        self.assertIn("retention-days: 3", browser)
        self.assertIn(
            "python -m unittest tests.test_insights_history_browser tests.test_observational_campaign_browser -v",
            browser,
        )
        self.assertIn("python tools/test_owner_onboarding_browser.py", browser)
        self.assertIn("python tools/test_goal_journey_browser.py", browser)
        self.assertIn("python tools/test_install_report_browser.py", browser)
        self.assertIn("python tools/test_campaign_monitor_browser.py", browser)
        self.assertIn("python tools/test_organic_taste_browser.py", browser)
        self.assertIn("python tools/test_goal_packet_history_browser.py", browser)
        self.assertIn("python tools/test_weekly_review_actions_browser.py", browser)
        self.assertIn("python tools/test_client_dashboard_browser.py", browser)
        self.assertIn("python tools/test_authority_expiry_browser.py", browser)
        self.assertIn("python tools/test_agent_task_presets_browser.py", browser)
        self.assertEqual(text.count("python -m pip install --only-binary :all: -r docs/requirements-auth.txt"), 3)

    def test_ratchet_reads_exact_base_without_executing_enrollment(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text()
        self.assertIn('python tools/source_ratchet.py --base "$RATCHET_BASE" --head HEAD', text)
        self.assertIn("github.event.pull_request.base.sha || github.event.before", text)
        self.assertNotIn("source_ratchet.py --write", text)

    def test_property_profiles_and_replay_caches_stay_isolated(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text()
        self.assertIn("HYPOTHESIS_PROFILE: wmm-ci", text)
        self.assertEqual(text.count("-r docs/requirements-properties.txt"), 3)
        self.assertEqual(text.count("actions/cache/restore@caa296126883cff596d87d8935842f9db880ef25"), 2)
        self.assertEqual(text.count("actions/cache/save@caa296126883cff596d87d8935842f9db880ef25"), 2)
        self.assertEqual(text.count("path: .factory/hypothesis/examples"), 4)
        self.assertEqual(text.count("restore-keys:"), 2)
        for block in text.split("restore-keys: |\n")[1:]:
            prefix = block.splitlines()[0]
            self.assertIn("hashFiles('docs/requirements-properties.txt')", prefix)
            self.assertIn("github.event.pull_request.number || 'main'", prefix)
            self.assertIn("matrix.shard", prefix)
            self.assertNotIn("github.run_id", prefix)
        self.assertNotIn("pull_request_target", text)

    def test_report_type_imports_are_hash_pinned_without_runtime_provisioning(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
        maintained = text.split("  maintainability:\n", 1)[1].split("  browser:\n", 1)[0]
        self.assertIn(
            "--require-hashes --no-deps --only-binary :all: -r docs/requirements-report-types.txt", maintained
        )
        self.assertNotIn("playwright install", maintained)
        requirements = (ROOT / "docs/requirements-report-types.txt").read_text(encoding="utf-8")
        for dependency in ("playwright==1.57.0", "PyMuPDF==1.27.2.2"):
            self.assertIn(dependency + " --hash=sha256:", requirements)

    def test_native_library_types_run_with_pinned_local_tooling(self):
        text = (ROOT / ".github/workflows/checks.yml").read_text(encoding="utf-8")
        maintained = text.split("  maintainability:\n", 1)[1].split("  browser:\n", 1)[0]
        self.assertIn("run: node tools/check_js_types.mjs", maintained)
        self.assertLess(maintained.index("npm ci --ignore-scripts"), maintained.index("node tools/check_js_types.mjs"))

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
