"""Prove missing signatures and incorrect generated-row assignments fail."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("danger_zone_types", ROOT / "tools/danger_zone_types.py")
assert SPEC and SPEC.loader
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


class DangerZoneTypesTests(unittest.TestCase):
    def test_reviewed_boundary_signatures_cannot_disappear(self):
        self.assertEqual(checker.check(ROOT), [])
        self.assertEqual(checker.check_source("def read(value: object) -> str: return str(value)", {"read"}), [])
        self.assertEqual(len(checker.check_source("def read(value): return value", {"read"})), 2)
        self.assertEqual(len(checker.check_source("", {"read"})), 1)

    def test_generated_rows_reject_wrong_grant_and_role_fields(self):
        if not (ROOT / "node_modules/pyright").is_dir():
            self.skipTest("Pinned Pyright is installed by maintainability CI")
        with tempfile.TemporaryDirectory(prefix="wmm-type-negative-") as folder:
            source = Path(folder) / "invalid_rows.py"
            source.write_text(
                "from mission_control.schema_types import AgentGrantsRow, OperatorRolesRow\n"
                "from mission_control.agent_grants import authenticated\n"
                "from datetime import datetime\n"
                "import sqlite3\n"
                "def corrupt(grant: AgentGrantsRow, role: OperatorRolesRow) -> None:\n"
                "    grant['max_calls'] = 'unbounded'\n"
                "    role['version'] = 'latest'\n"
                "def access(db: sqlite3.Connection, stamp: datetime) -> None:\n"
                "    authenticated(db, None, {}, stamp).get('status')\n"
            )
            configuration = Path(folder) / "pyrightconfig.json"
            configuration.write_text(
                json.dumps(
                    {
                        "typeCheckingMode": "standard",
                        "pythonVersion": "3.11",
                        "extraPaths": [str(ROOT)],
                        "include": [str(source)],
                    }
                )
            )
            result = subprocess.run(
                ["npx", "--no-install", "pyright", "--project", str(configuration), "--outputjson", str(source)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            errors = [row for row in report["generalDiagnostics"] if row["severity"] == "error"]
            self.assertEqual(len(errors), 3, errors)
            self.assertEqual({row["range"]["start"]["line"] for row in errors}, {5, 6, 8})


if __name__ == "__main__":
    unittest.main()
