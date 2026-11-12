"""Every closed operation keeps a generated docs row in sync."""

import subprocess
import sys
import unittest
from pathlib import Path

from mission_control.operation_catalog import OPERATIONS

ROOT = Path(__file__).resolve().parents[1]


class OperationDocsTests(unittest.TestCase):
    def test_generated_reference_matches_the_catalog(self):
        result = subprocess.run(
            [sys.executable, "tools/generate_operation_docs.py", "--check"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_every_operation_has_a_row(self):
        text = (ROOT / "docs/operation-catalog.md").read_text(encoding="utf-8")
        missing = [name for name in OPERATIONS if f"| `{name}` |" not in text]
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
