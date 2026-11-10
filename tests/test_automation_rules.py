"""User-authored automation rules are deterministic proposals, never effects."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from mission_control.automation_rules import evaluate, evaluate_app, main, project, validate
from mission_control.common import Invalid
from mission_control.service import Service
from mission_control.store import Store

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads((ROOT / "docs/automation-rules.example.json").read_text(encoding="utf-8"))
STAMP = "2026-11-10T12:00:00+00:00"


class AutomationRuleTests(unittest.TestCase):
    def test_example_rule_fires_repair_proposal_without_side_effects(self):
        value = evaluate(EXAMPLE, {"study": {"window": {"state": "ENDED"}, "coverage": "PARTIAL"}}, STAMP)
        self.assertEqual([row["rule_id"] for row in value["proposals"]], ["coverage-repair"])
        proposal = value["proposals"][0]
        self.assertEqual(proposal["status"], "PROPOSED")
        self.assertEqual(proposal["mode"], "PROPOSE_ONLY")
        self.assertIn("no publication", value["boundaries"][0])

    def test_missing_and_partial_facts_never_match(self):
        value = evaluate(EXAMPLE, {"study": {"window": {"state": "ENDED"}}}, STAMP)
        coverage = next(row for row in value["results"] if row["rule_id"] == "coverage-repair")
        self.assertEqual(coverage["status"], "UNKNOWN")
        self.assertIn("study.coverage", coverage["missing"])
        self.assertEqual(value["proposals"], [])

    def test_complete_mature_result_proposes_review(self):
        value = evaluate(EXAMPLE, {"study": {"window": {"state": "ENDED"}, "coverage": "COMPLETE"},
                                   "retention": {"maturity": "MATURE"}}, STAMP)
        self.assertEqual([row["rule_id"] for row in value["proposals"]], ["mature-result-review"])

    def test_priority_deduplication_and_expiry(self):
        document = {"schema": "wmm.automation-rules.v1", "mode": "PROPOSE_ONLY", "timezone": "UTC", "rules": [
            {"id": "a", "enabled": True, "priority": 1, "when": {"fact": "x", "op": "eq", "value": 1},
             "then": {"propose": {"action": "review", "tool": "reports.read", "reason": "low"}, "requires": ["OWNER_REVIEW"]}},
            {"id": "b", "enabled": True, "priority": 9, "when": {"fact": "x", "op": "eq", "value": 1},
             "then": {"propose": {"action": "review", "tool": "reports.read", "reason": "high"}, "requires": ["OWNER_REVIEW"]}},
            {"id": "c", "enabled": True, "priority": 5, "expires_at": "2026-01-01T00:00:00+00:00",
             "when": {"fact": "x", "op": "eq", "value": 1},
             "then": {"propose": {"action": "other", "tool": "reports.read", "reason": "old"}, "requires": ["OWNER_REVIEW"]}}]}
        value = evaluate(document, {"x": 1}, STAMP)
        self.assertEqual(len(value["proposals"]), 1)
        self.assertEqual(value["proposals"][0]["reason"], "high")
        expired = next(row for row in value["results"] if row["rule_id"] == "c")
        self.assertEqual(expired["status"], "EXPIRED")

    def test_boolean_logic_and_comparisons(self):
        document = {"schema": "wmm.automation-rules.v1", "mode": "PROPOSE_ONLY", "timezone": "UTC", "rules": [
            {"id": "logic", "enabled": True, "priority": 1,
             "when": {"all": [{"fact": "a", "op": "gte", "value": 2},
                              {"any": [{"fact": "b", "op": "in", "value": ["x", "y"]},
                                       {"not": {"fact": "c", "op": "exists"}}]},
                              {"fact": "d", "op": "contains", "value": "ok"}]},
             "then": {"propose": {"action": "review", "tool": "reports.read", "reason": "matched"}, "requires": ["OWNER_REVIEW"]}}]}
        value = evaluate(document, {"a": 2, "b": "x", "d": ["ok"]}, STAMP)
        self.assertEqual(value["proposals"][0]["action"], "review")
        self.assertEqual(evaluate(document, {"a": 1, "b": "x", "d": ["ok"]}, STAMP)["proposals"], [])

    def test_live_workspace_projection_has_no_invented_metrics(self):
        import tempfile
        from pathlib import Path as PathValue
        with tempfile.TemporaryDirectory() as folder:
            store = Store(PathValue(folder) / "state.sqlite", seed=False)
            store.save_app("sample-one", dict(name="Synthetic app", release="build-1", job="Synthetic job",
                                             audience="Synthetic audience", activation="Synthetic value",
                                             locale="en-US", currency="USD"))
            facts = project(Service(store).workspace("sample-one"))
        self.assertEqual(facts["app"]["release"], "build-1")
        self.assertEqual(facts["metrics"]["cohort_count"], 0)
        self.assertEqual(facts["install"]["campaign_count"], 0)
        self.assertEqual(facts["measurement"]["state"], "NO_DATA")
        self.assertNotIn("retention_rate", str(facts))

    def test_database_example_proposes_review_without_writing_workspace(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "existing.sqlite3"
            store = Store(path, seed=False)
            store.save_app("facts-review", dict(name="Synthetic app", release="build-1"))
            other = store.save_app("separate-app", dict(name="Separate synthetic app", release="build-2"))
            store.save_record("separate-app", dict(kind="cohort", title="Separate cohort",
                source="Synthetic fixture", data={"installs": 3}, manifest_version=other["version"]))
            before = path.read_bytes()
            captured = StringIO()
            with redirect_stdout(captured):
                self.assertEqual(main(["--rules", str(ROOT / "docs/automation-rules.example.json"),
                                       "--database", str(path), "--app", "facts-review"]), 0)
            self.assertEqual([app["id"] for app in store.apps()], ["facts-review", "separate-app"])
            self.assertEqual(path.read_bytes(), before)
        result = json.loads(captured.getvalue())
        self.assertEqual([row["rule_id"] for row in result["proposals"]], ["cohort-setup-review"])
        self.assertEqual(result["proposals"][0]["status"], "PROPOSED")

    def test_missing_database_does_not_create_a_workspace(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "not-created" / "missing.sqlite3"
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(["--rules", str(ROOT / "docs/automation-rules.example.json"),
                      "--database", str(path), "--app", "facts-review"])
            self.assertFalse(path.parent.exists())

    def test_omitted_sections_do_not_project_zero_counts(self):
        self.assertEqual(project({}), {})

    def test_evaluate_app_uses_the_current_saved_workspace(self):
        import tempfile
        from pathlib import Path as PathValue
        with tempfile.TemporaryDirectory() as folder:
            store = Store(PathValue(folder) / "state.sqlite", seed=False)
            store.save_app("sample-one", dict(name="Synthetic app", release="build-1", job="Synthetic job",
                                             audience="Synthetic audience", activation="Synthetic value",
                                             locale="en-US", currency="USD"))
            document = {"schema": "wmm.automation-rules.v1", "mode": "PROPOSE_ONLY", "timezone": "UTC", "rules": [
                {"id": "app-ready", "enabled": True, "priority": 1,
                 "when": {"fact": "app.release", "op": "eq", "value": "build-1"},
                 "then": {"propose": {"action": "review", "tool": "reports.read", "reason": "saved app"},
                          "requires": ["OWNER_REVIEW"]}}]}
            value = evaluate_app(store, "sample-one", document)
        self.assertEqual(value["proposals"][0]["rule_id"], "app-ready")

    def test_invalid_unknown_and_unsafe_shapes_reject(self):
        bad = json.loads(json.dumps(EXAMPLE))
        bad["rules"][0]["when"] = {"fact": "x", "op": "sql", "value": 1}
        with self.assertRaises(Invalid):
            validate(bad)
        bad = json.loads(json.dumps(EXAMPLE))
        bad["rules"][0]["unexpected"] = True
        with self.assertRaises(Invalid):
            validate(bad)
        bad = json.loads(json.dumps(EXAMPLE))
        bad["rules"][0]["then"]["propose"]["tool"] = ""
        with self.assertRaises(Invalid):
            validate(bad)
