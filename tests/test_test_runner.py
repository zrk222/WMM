"""The canonical test entry point reports profiles without pretending optional suites passed."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wmm_test_runner", ROOT / "tools" / "test.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class TestRunnerContractTests(unittest.TestCase):
    def test_browser_modules_are_classified_by_name(self):
        self.assertTrue(runner.is_browser_module("tests.test_publication_browser"))
        self.assertFalse(runner.is_browser_module("tests.test_guided_workflow"))

    def test_core_discovery_is_nonempty_and_keeps_browser_modules_for_skips(self):
        cases, excluded = runner.discover("core")
        self.assertGreater(len(cases), 1000)
        self.assertEqual(excluded, 0)

    def test_profile_inventory_is_side_effect_free(self):
        self.assertEqual(runner.main(["--profile", "inventory"]), 0)
        self.assertEqual(runner.main(["--list"]), 0)

    def test_missing_core_tools_are_named_not_silently_green(self):
        gaps = runner.core_gaps()
        self.assertIsInstance(gaps, list)
        for gap in gaps:
            self.assertTrue(gap)
