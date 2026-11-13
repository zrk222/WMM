"""Generated evidence and dependency trees stay out of the tracked tree."""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("branch_hygiene", ROOT / "tools/branch_hygiene.py")
assert SPEC and SPEC.loader
hygiene = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hygiene)
IGNORED = (".factory", ".forge", ".prestige", ".wrangler", "node_modules")
NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
OLD = (NOW - timedelta(days=8)).isoformat()
HEAD = "a" * 40
OTHER = "b" * 40
NAME = "codex/merged-one"


def pull(number: int = 1, name: str = NAME) -> dict[str, object]:
    return {
        "number": number,
        "state": "closed",
        "merged_at": OLD,
        "merge_commit_sha": "c" * 40,
        "head": {"ref": name, "sha": HEAD, "repo": {"full_name": hygiene.REPOSITORY}},
        "base": {"ref": "main", "repo": {"full_name": hygiene.REPOSITORY}},
    }


def branch(name: str = NAME) -> dict[str, object]:
    return {"name": name, "protected": False, "commit": {"sha": HEAD}}


class FakeAPI:
    def __init__(self) -> None:
        self.branches = [branch()]
        self.pulls = [pull()]
        self.opened: list[dict[str, object]] = []
        self.date = OLD
        self.calls: list[tuple[str, str]] = []
        self.reads = 0
        self.change_final = ""
        self.fail_delete = ""
        self.manifest: Path | None = None
        self.bad_repository = False

    @property
    def deletes(self) -> list[str]:
        return [endpoint for method, endpoint in self.calls if method == "DELETE"]

    def request(self, method: str, endpoint: str) -> object:
        self.calls.append((method, endpoint))
        parsed = urlsplit(endpoint)
        query = parse_qs(parsed.query)
        if method == "DELETE":
            if self.manifest is None or not self.manifest.is_file():
                raise AssertionError("Deletion preceded retained manifest")
            if self.fail_delete and self.fail_delete in endpoint:
                raise RuntimeError("synthetic unavailable provider")
            return None
        if not endpoint:
            return {"full_name": "other/repo" if self.bad_repository else hygiene.REPOSITORY, "default_branch": "main"}
        if parsed.path == "branches":
            page = int(query["page"][0])
            return copy.deepcopy(self.branches[(page - 1) * 100 : page * 100])
        if parsed.path == "pulls":
            rows = self.opened if query["state"] == ["open"] else self.pulls
            page = int(query["page"][0])
            return copy.deepcopy(rows[(page - 1) * 100 : page * 100])
        if parsed.path.startswith("branches/"):
            self.reads += 1
            name = unquote(parsed.path.removeprefix("branches/"))
            row = copy.deepcopy(next(row for row in self.branches if row["name"] == name))
            if self.reads == 2 and self.change_final == "head":
                row["commit"] = {"sha": OTHER}
            if self.reads == 2 and self.change_final == "protected":
                row["protected"] = True
            return row
        if parsed.path.startswith("pulls/"):
            number = int(parsed.path.removeprefix("pulls/"))
            return copy.deepcopy(next(row for row in self.pulls if row["number"] == number))
        if parsed.path.startswith("commits/"):
            return {"commit": {"committer": {"date": self.date}}}
        raise AssertionError("Unexpected synthetic API endpoint: " + endpoint)


class BranchHygieneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manifest = Path(self.tmp.name) / "manifest.json"
        self.results = Path(self.tmp.name) / "results.json"
        self.api = FakeAPI()

    def prepare(self) -> dict[str, object]:
        value = hygiene.plan(self.api, set(), NOW)
        hygiene.save(self.manifest, value)
        self.api.manifest = self.manifest
        self.api.calls.clear()
        return value

    def run_apply(self, active: set[str] | None = None):
        return hygiene.apply(self.api, self.manifest, self.results, NOW, lambda: active or set())

    def test_squash_merge_exact_source_head_is_eligible_without_ancestry(self):
        value = self.prepare()
        self.assertIsInstance(value["candidates"], list)
        self.assertEqual(
            value["candidates"], [{"branch": NAME, "sha": HEAD, "pr": 1, "merged_at": OLD, "committed_at": OLD}]
        )
        receipt = self.run_apply()
        self.assertEqual(receipt["outcomes"], [{"branch": NAME, "status": "deleted", "reason": "provider_confirmed"}])
        self.assertEqual(self.api.deletes, ["git/refs/heads/codex%2Fmerged-one"])
        self.assertEqual(json.loads(self.results.read_text()), receipt)
        self.assertEqual(len(receipt["manifest_sha256"]), 64)

    def test_plan_excludes_protected_open_active_and_non_agent_branches(self):
        self.api.branches = [
            branch("main"),
            branch("feature/work"),
            branch("codex/nested/unsafe"),
            branch("codex/-unsafe"),
            branch("codex/protected"),
            branch("codex/open"),
            branch("codex/active"),
        ]
        self.api.branches[4]["protected"] = True
        self.api.opened = [{"head": {"ref": "codex/open"}}]
        value = hygiene.plan(self.api, {"codex/active"}, NOW)
        self.assertEqual(value["candidates"], [])
        self.assertEqual(
            value["skipped"],
            [
                {"branch": "codex/protected", "reason": "protected_or_unknown"},
                {"branch": "codex/open", "reason": "open_pr"},
                {"branch": "codex/active", "reason": "active_worktree"},
            ],
        )
        self.assertFalse(self.api.deletes)

    def test_plan_requires_exact_main_merge_and_both_ages_strictly_over_seven_days(self):
        for changed in (
            "unmerged",
            "wrong_base",
            "wrong_sha",
            "wrong_source_repo",
            "wrong_base_repo",
            "recent_merge",
            "boundary_merge",
            "recent_commit",
            "boundary_commit",
        ):
            with self.subTest(changed=changed):
                self.api = FakeAPI()
                pr = self.api.pulls[0]
                if changed == "unmerged":
                    pr["merged_at"] = None
                elif changed == "wrong_base":
                    hygiene.obj(pr["base"])["ref"] = "develop"
                elif changed == "wrong_sha":
                    hygiene.obj(pr["head"])["sha"] = OTHER
                elif changed == "wrong_source_repo":
                    hygiene.obj(pr["head"])["repo"] = {"full_name": "fork/WMM"}
                elif changed == "wrong_base_repo":
                    hygiene.obj(pr["base"])["repo"] = {"full_name": "other/WMM"}
                elif changed.endswith("merge"):
                    pr["merged_at"] = (NOW - timedelta(days=7 if changed.startswith("boundary") else 6)).isoformat()
                else:
                    self.api.date = (NOW - timedelta(days=7 if changed.startswith("boundary") else 6)).isoformat()
                self.assertEqual(hygiene.plan(self.api, set(), NOW)["candidates"], [])
                self.assertFalse(self.api.deletes)

    def test_inventories_paginate_and_commit_metadata_is_requested_only_for_candidates(self):
        self.api.branches = [branch("ordinary-" + str(index)) for index in range(100)] + [branch()]
        self.api.pulls = [pull(index + 2, "ordinary-" + str(index)) for index in range(100)] + [pull()]
        value = hygiene.plan(self.api, set(), NOW)
        self.assertEqual(len(value["candidates"]), 1)
        self.assertTrue(any(endpoint == "branches?per_page=100&page=2" for _, endpoint in self.api.calls))
        self.assertTrue(any("state=closed&base=main&per_page=100&page=2" in endpoint for _, endpoint in self.api.calls))
        self.assertEqual(
            [endpoint for _, endpoint in self.api.calls if endpoint.startswith("commits/")], ["commits/" + HEAD]
        )

    def test_manifest_tampering_or_staleness_rejects_every_delete_before_api_calls(self):
        baseline = self.prepare()
        for changed in (
            "schema",
            "repository",
            "future",
            "expired",
            "injection",
            "sha",
            "pr",
            "extra",
            "duplicate",
            "recent",
        ):
            with self.subTest(changed=changed):
                value = copy.deepcopy(baseline)
                rows = value["candidates"]
                self.assertIsInstance(rows, list)
                if not isinstance(rows, list):
                    raise AssertionError("Invalid fixture")
                row = hygiene.obj(rows[0])
                if changed in ("schema", "repository"):
                    value[changed] = "other"
                elif changed in ("future", "expired"):
                    value["created_at"] = (
                        NOW + timedelta(seconds=1) if changed == "future" else NOW - timedelta(hours=2)
                    ).isoformat()
                elif changed == "injection":
                    row["branch"] = "codex/../../main?token=private"
                elif changed == "sha":
                    row["sha"] = "../main"
                elif changed == "pr":
                    row["pr"] = True
                elif changed == "extra":
                    value["endpoint"] = "other/repo"
                elif changed == "duplicate":
                    rows.append(copy.deepcopy(row))
                else:
                    row["committed_at"] = NOW.isoformat()
                hygiene.save(self.manifest, value)
                self.api.calls.clear()
                with self.assertRaises(ValueError):
                    self.run_apply()
                self.assertEqual(self.api.calls, [])

    def test_live_changes_prevent_deletion_including_final_head_and_protection_reads(self):
        for changed in (
            "head",
            "protected",
            "open",
            "active",
            "merge",
            "commit",
            "final_head",
            "final_protected",
            "repository",
        ):
            with self.subTest(changed=changed):
                self.api = FakeAPI()
                self.prepare()
                if changed == "head":
                    self.api.branches[0]["commit"] = {"sha": OTHER}
                elif changed == "protected":
                    self.api.branches[0]["protected"] = True
                elif changed == "open":
                    self.api.opened = [{"head": {"ref": NAME}}]
                elif changed == "merge":
                    hygiene.obj(self.api.pulls[0]["head"])["sha"] = OTHER
                elif changed == "commit":
                    self.api.date = NOW.isoformat()
                elif changed.startswith("final_"):
                    self.api.change_final = changed.removeprefix("final_")
                elif changed == "repository":
                    self.api.bad_repository = True
                if changed == "repository":
                    with self.assertRaises(ValueError):
                        self.run_apply()
                else:
                    receipt = self.run_apply({NAME} if changed == "active" else set())
                    self.assertEqual(receipt["outcomes"][0]["status"], "skipped")
                self.assertEqual(self.api.deletes, [])

    def test_new_worktree_at_final_check_prevents_deletion(self):
        self.prepare()
        reads = iter([set(), {NAME}])
        receipt = hygiene.apply(self.api, self.manifest, self.results, NOW, lambda: next(reads))
        self.assertEqual(receipt["outcomes"][0]["status"], "skipped")
        self.assertFalse(self.api.deletes)

    def test_invalid_json_naive_timestamp_and_manifest_results_alias_fail_without_requests(self):
        baseline = self.prepare()
        for text in (
            "not json",
            "[]",
            json.dumps({**baseline, "created_at": "2026-11-12T12:00:00"}),
            json.dumps({**baseline, "skipped": [{"branch": "main", "reason": "active_worktree"}]}),
        ):
            with self.subTest(text=text):
                self.manifest.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    self.run_apply()
                self.assertEqual(self.api.calls, [])
        hygiene.save(self.manifest, baseline)
        with self.assertRaises(ValueError):
            hygiene.apply(self.api, self.manifest, self.manifest, NOW, lambda: set())
        self.assertEqual(self.api.calls, [])

    def test_wrong_workflow_repository_and_unavailable_inventory_fail_closed(self):
        with patch.dict(hygiene.os.environ, {"GITHUB_REPOSITORY": "other/repo"}), self.assertRaises(ValueError):
            hygiene.plan(self.api, set(), NOW)
        self.assertEqual(self.api.calls, [])
        with (
            patch.object(self.api, "request", side_effect=RuntimeError("synthetic unavailable inventory")),
            self.assertRaises(RuntimeError),
        ):
            hygiene.plan(self.api, set(), NOW)
        self.assertFalse(self.api.deletes)

    def test_timeout_is_a_failed_outcome_without_claiming_deletion(self):
        self.prepare()
        with patch.object(
            self.api,
            "request",
            side_effect=[
                {"full_name": hygiene.REPOSITORY, "default_branch": "main"},
                subprocess.TimeoutExpired("synthetic request", 30),
            ],
        ):
            receipt = self.run_apply()
        self.assertEqual(receipt["outcomes"][0]["status"], "failed")
        self.assertIn("outcome_may_be_unknown", receipt["outcomes"][0]["reason"])
        self.assertFalse(self.api.deletes)

    def test_partial_provider_failure_is_retained_and_later_candidates_still_checked(self):
        self.api.branches.append(branch("codex/merged-two"))
        self.api.pulls.append(pull(2, "codex/merged-two"))
        self.prepare()
        self.api.fail_delete = "merged-one"
        receipt = self.run_apply()
        self.assertEqual([row["status"] for row in receipt["outcomes"]], ["failed", "deleted"])
        self.assertEqual(json.loads(self.results.read_text())["outcomes"], receipt["outcomes"])

    def test_worktree_parser_uses_exact_git_branch_records(self):
        result = subprocess.CompletedProcess(
            [], 0, "worktree /synthetic\nbranch refs/heads/codex/active\n\nworktree /detached\ndetached\n"
        )
        with patch.object(hygiene.subprocess, "run", return_value=result):
            self.assertEqual(hygiene.worktrees(), {"codex/active"})

    def test_provider_errors_never_relay_credentials_or_private_response_bodies(self):
        result = subprocess.CompletedProcess([], 1, "secret-token", "private-provider-error")
        with patch.object(hygiene.subprocess, "run", return_value=result) as run:
            with self.assertRaisesRegex(RuntimeError, "^GitHub request failed$"):
                hygiene.GitHub().request("GET", "branches")
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
            self.assertEqual(run.call_args.kwargs["encoding"], "utf-8")
            self.assertEqual(run.call_args.args[0][2:4], ["--hostname", "github.com"])

    def test_large_unicode_provider_json_is_decoded_as_utf8_using_a_real_child_process(self):
        real_run = subprocess.run
        suffix = "\u201d \u65e5\u672c\u8a9e \U0001f9ea"
        script = (
            "import json,sys;sys.stdout.buffer.write(json.dumps("
            "{'body':'x'*754378+'\\u201d \\u65e5\\u672c\\u8a9e \\U0001f9ea'},"
            "ensure_ascii=False).encode('utf-8'))"
        )

        def local_child(_argv, **kwargs):
            self.assertEqual(kwargs["encoding"], "utf-8")
            return real_run([sys.executable, "-c", script], **kwargs)

        with patch.object(hygiene.subprocess, "run", side_effect=local_child):
            value = hygiene.obj(hygiene.GitHub().request("GET", "pulls?state=closed"))
        self.assertEqual(value["body"], "x" * 754378 + suffix)

    def test_missing_malformed_or_undecodable_provider_output_fails_privately(self):
        for output in (None, b"not text", "{private-response", "\ud800"):
            with self.subTest(output=repr(output)):
                result = subprocess.CompletedProcess([], 0, output, "private-provider-error")
                with (
                    patch.object(hygiene.subprocess, "run", return_value=result),
                    self.assertRaisesRegex(RuntimeError, "^GitHub request failed$"),
                ):
                    hygiene.GitHub().request("GET", "branches")
        error = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "synthetic private error")
        with (
            patch.object(hygiene.subprocess, "run", side_effect=error),
            self.assertRaisesRegex(RuntimeError, "^GitHub request failed$"),
        ):
            hygiene.GitHub().request("GET", "branches")

    def test_workflow_uploads_manifest_before_apply_and_scheduled_cleanup_is_enabled(self):
        source = (ROOT / ".github/workflows/hygiene.yml").read_text(encoding="utf-8")
        self.assertLess(
            source.index("run: python tools/branch_hygiene.py plan"),
            source.index("name: branch-hygiene-before-deletion"),
        )
        self.assertLess(
            source.index("name: branch-hygiene-before-deletion"),
            source.index("run: python tools/branch_hygiene.py apply"),
        )
        self.assertIn("if-no-files-found: error", source)
        self.assertIn("if: github.event_name == 'schedule' || !inputs.dry_run", source)
        self.assertIn("default: true", source)
        self.assertIn("if: always()", source)
        self.assertIn("fetch-depth: 1", source)
        self.assertIn("pull-requests: read", source)
        self.assertNotIn("git fetch", source)
        self.assertNotIn("merge-base", source)


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
