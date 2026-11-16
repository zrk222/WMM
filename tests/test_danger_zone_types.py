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

    def test_new_public_access_methods_require_annotations(self):
        source = """class Access:
    def __init__(self, store: object) -> None: pass
    def verified(self, item: int) -> int: return item
    def new(self, item): return item
    @staticmethod
    def static(self) -> None: pass
    def _internal(self, item): return item
"""
        self.assertEqual(
            checker.check_source(source, set(), {"Access"}),
            [
                "Missing parameter annotation: Access.new.item",
                "Missing return annotation: Access.new",
                "Missing parameter annotation: Access.static.self",
            ],
        )

    def test_reviewed_handler_methods_require_annotations(self) -> None:
        source = """class Handler:
    def session(self) -> str: return "token"
    def boundary(self, write): return "token"
    def _internal(self, value): return value
"""
        self.assertEqual(
            checker.check_source(source, set(), methods={"Handler": {"session", "boundary"}}),
            [
                "Missing parameter annotation: Handler.boundary.write",
                "Missing return annotation: Handler.boundary",
            ],
        )

    def test_new_public_framing_function_requires_annotations(self):
        self.assertEqual(
            checker.check_source("async def new(request): pass", set(), all_public=True),
            ["Missing parameter annotation: new.request", "Missing return annotation: new"],
        )

    def test_strict_allowlist_includes_reviewed_authority_modules(self) -> None:
        strict = json.loads((ROOT / "pyrightconfig.json").read_text(encoding="utf-8"))["strict"]
        self.assertIn("mission_control/agent_grants.py", strict)
        self.assertIn("mission_control/operation_authority.py", strict)
        self.assertIn("mission_control/automation_execution.py", strict)
        self.assertIn("mission_control/campaign_schedule.py", strict)
        self.assertIn("mission_control/agent_tasks.py", strict)
        self.assertIn("mission_control/agent_context.py", strict)
        self.assertIn("mission_control/agent_contract.py", strict)
        self.assertIn("mission_control/agent_registry.py", strict)
        self.assertIn("mission_control/agent_access.py", strict)

    def test_agent_task_boundary_names_remain_patchable(self) -> None:
        from mission_control import (
            agent_api,
            agent_context,
            agent_contract,
            agent_native,
            agent_registry,
            agent_tasks,
            agent_usage,
            draft_recipes,
            worker,
        )

        upstream = (
            (agent_api, "request"),
            (agent_context, "snapshot"),
            (agent_contract, "bounded_text"),
            (agent_contract, "draft"),
            (agent_contract, "exact"),
            (agent_contract, "output_contract"),
            (agent_contract, "prompt"),
            (agent_native, "run"),
            (agent_usage, "observation"),
            (draft_recipes, "recipe"),
            (draft_recipes, "validate"),
            (worker, "json_job"),
        )
        for module, name in upstream:
            self.assertTrue(callable(getattr(module, name)), name)
        self.assertIsNotNone(agent_registry.REGISTRY)
        for name in (
            "api_run",
            "snapshot",
            "bounded_text",
            "draft",
            "exact",
            "output_contract",
            "prompt",
            "native_run",
            "usage_observation",
            "recipe",
            "validate_recipe",
            "json_job",
        ):
            self.assertTrue(callable(getattr(agent_tasks, name)), name)

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
