"""Generated evidence and dependency trees stay out of the tracked tree."""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORED = (".factory", ".forge", ".prestige", ".wrangler", "node_modules")


class RepositoryHygieneTests(unittest.TestCase):
    def test_generated_paths_are_not_tracked(self):
        if not (ROOT / ".git").exists():
            self.skipTest("A source archive has no git index to inspect")
        tracked = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", *IGNORED], capture_output=True, text=True, check=True
        ).stdout
        self.assertEqual(tracked.strip(), "")


if __name__ == "__main__":
    unittest.main()
