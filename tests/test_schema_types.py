"""Generated row types stay in lock-step with the assembled schema."""

import subprocess
import sys
import unittest
from pathlib import Path

from mission_control import http_types, schema_types

ROOT = Path(__file__).resolve().parents[1]


class SchemaTypeTests(unittest.TestCase):
    def test_generated_file_matches_the_current_schema(self):
        result = subprocess.run(
            [sys.executable, "tools/generate_schema_types.py", "--check"], cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_known_rows_have_typed_columns(self):
        self.assertEqual(schema_types.AuditRow.__annotations__["app_id"], str)
        self.assertEqual(schema_types.JobsRow.__annotations__["attempts"], int)
        rows = [name for name in vars(schema_types) if name.endswith("Row")]
        self.assertGreater(len(rows), 100)

    def test_http_version_projection_matches_generated_apps_row(self) -> None:
        self.assertEqual(
            http_types.AppVersionRow.__annotations__["version"],
            schema_types.AppsRow.__annotations__["version"],
        )


if __name__ == "__main__":
    unittest.main()
