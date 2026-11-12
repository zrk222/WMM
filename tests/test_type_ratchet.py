"""The maintained Python allowlist stays clean under pinned Pyright."""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TypeRatchetTests(unittest.TestCase):
    def test_maintained_python_types(self):
        if shutil.which("npx") is None or not (ROOT / "node_modules/pyright").exists():
            self.skipTest("Pyright is installed by the maintainability CI job")
        result = subprocess.run([sys.executable, "tools/check_types.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
