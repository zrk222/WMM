"""User-authored automation rules are deterministic proposals, never effects."""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from mission_control.automation_rules import evaluate, main, project, validate
from mission_control.common import Invalid
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.review_access import Access
from mission_control.service import Service
from mission_control.store import Store
from tests import test_verified_review as identities
from tests import test_agent_grants as grant_fixtures

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


class AutomationSimulationHTTPTests(unittest.TestCase):
    setUp = grant_fixtures.GrantTests.setUp
    tearDown = grant_fixtures.GrantTests.tearDown
    route = "/api/apps/sample-one/automation/evaluate"

    def test_owner_preview_reads_saved_facts_without_vault_provider_or_database_write(self):
        self.store.save_record("sample-one", {
            "kind": "connection", "title": "Synthetic connection", "source": "Synthetic test",
            "data": {"provider": "app_store", "auth_mode": "managed_key", "credential_ref": "fixture-only"},
        })
        paths = (self.store.path, Path(f"{self.store.path}-wal"))
        # A read-only SQLite WAL session can create an empty coordination file.
        def hashes():
            return [sha256(path.read_bytes() if path.exists() else b"").hexdigest() for path in paths]
        before = hashes()
        with (patch("mission_control.connection_setup.Connections.vault", side_effect=AssertionError("opened vault")),
              patch("mission_control.operator_identity.github_read", side_effect=AssertionError("called provider"))):
            report = self.owner.request("POST", self.route, {"rules": EXAMPLE})
        self.assertEqual([row["rule_id"] for row in report["proposals"]], ["cohort-setup-review"])
        self.assertEqual(report["results"][0]["status"], "UNKNOWN")
        self.assertEqual(hashes(), before)

    def test_anonymous_checker_and_other_app_are_denied(self):
        Access(self.store).save("sample-one", identities.OWNER, identities.CHECKER, {
            "login": identities.CHECKER["login"], "role": "CHECKER", "status": "ACTIVE", "version": None,
        })
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        checker = OperatorClient(self.origin)
        checker.bootstrap()
        checker.request("POST", "/api/identity/login", {"token": identities.CHECKER_TOKEN})
        for client, route in ((anonymous, self.route), (checker, self.route),
                              (self.owner, self.route.replace("sample-one", "sample-two"))):
            with self.subTest(route=route), self.assertRaises(ClientError) as error:
                client.request("POST", route, {"rules": EXAMPLE})
            self.assertEqual(error.exception.status, 403)


    def test_saved_rule_http_is_local_and_owner_only(self):
        route = self.route.replace("/evaluate", "/rules")
        anonymous = OperatorClient(self.origin)
        anonymous.bootstrap()
        with (patch("mission_control.connection_setup.Connections.vault", side_effect=AssertionError("opened vault")),
              patch("mission_control.operator_identity.github_read", side_effect=AssertionError("called provider"))):
            self.assertIsNone(self.owner.request("GET", route))
            saved = self.owner.request("POST", route, {"document": EXAMPLE})
            self.assertEqual(self.owner.request("GET", route), saved)
            for client, target in ((anonymous, route), (self.owner, route.replace("sample-one", "sample-two"))):
                for method, data in (("GET", None), ("POST", {"document": EXAMPLE})):
                    with self.subTest(method=method, target=target), self.assertRaises(ClientError) as error:
                        client.request(method, target, data)
                    self.assertEqual(error.exception.status, 403)
