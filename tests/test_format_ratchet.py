"""Maintained files stay Ruff-formatted and lint-clean where Ruff is installed."""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class FormatRatchetTests(unittest.TestCase):
    def test_maintained_files_are_formatted_and_clean(self):
        if shutil.which("ruff") is None:
            self.skipTest("Ruff is installed by the pinned formatting CI job")
        result = subprocess.run([sys.executable, "tools/check_format.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
