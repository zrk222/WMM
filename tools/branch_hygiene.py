"""Plan and recheck stale, exactly merged WMM agent refs using bounded GitHub APIs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, TypedDict
from urllib.parse import quote, urlencode

REPOSITORY = "zrk222/WMM"
SCHEMA = "wmm.branch-hygiene.v1"
AGE = timedelta(days=7)
TTL = timedelta(hours=1)
BRANCH = re.compile(r"codex/[A-Za-z0-9][A-Za-z0-9._-]*\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class API(Protocol):
    def request(self, method: str, endpoint: str) -> object: ...


class Receipt(TypedDict):
    repository: str
    schema: str
    manifest_sha256: str
    outcomes: list[dict[str, str]]


class GitHub:
    def request(self, method: str, endpoint: str) -> object:
        result = subprocess.run(
            [
                "gh",
                "api",
                "--hostname",
                "github.com",
                "--method",
                method,
                ("repos/" + REPOSITORY + "/" + endpoint).rstrip("/"),
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode:
            # Never relay gh stderr: authentication/provider responses are private.
            raise RuntimeError("GitHub request failed")
        return json.loads(result.stdout) if result.stdout.strip() else None


def obj(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected API object")
    return value


def stamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Missing timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def pages(api: API, endpoint: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for page in range(1, 1001):
        separator = "&" if "?" in endpoint else "?"
        value = api.request("GET", endpoint + separator + urlencode({"per_page": 100, "page": page}))
        if not isinstance(value, list):
            raise ValueError("Expected paginated list")
        rows.extend(obj(item) for item in value)
        if len(value) < 100:
            return rows
    raise ValueError("API pagination exceeded safety bound")


def worktrees() -> set[str]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"], capture_output=True, text=True, check=True, timeout=30
    )
    return {
        line.removeprefix("branch refs/heads/")
        for line in result.stdout.splitlines()
        if line.startswith("branch refs/heads/")
    }


def verify_repository(api: API) -> None:
    if os.environ.get("GITHUB_REPOSITORY", REPOSITORY) != REPOSITORY:
        raise ValueError("Unexpected workflow repository")
    repository = obj(api.request("GET", ""))
    if repository.get("full_name") != REPOSITORY or repository.get("default_branch") != "main":
        raise ValueError("Repository identity or main branch changed")


def merge_matches(pr: dict[str, object], branch: str, sha: str, now: datetime) -> bool:
    head, base = obj(pr.get("head")), obj(pr.get("base"))
    return (
        pr.get("state") == "closed"
        and pr.get("merged_at") is not None
        and now - stamp(pr["merged_at"]) > AGE
        and head.get("ref") == branch
        and head.get("sha") == sha
        and obj(head.get("repo")).get("full_name") == REPOSITORY
        and base.get("ref") == "main"
        and obj(base.get("repo")).get("full_name") == REPOSITORY
    )


def commit_time(api: API, sha: str) -> str:
    value = obj(obj(obj(api.request("GET", "commits/" + sha)).get("commit")).get("committer")).get("date")
    stamp(value)
    if not isinstance(value, str):
        raise ValueError("Missing commit date")
    return value


def plan(api: API, active: set[str], now: datetime) -> dict[str, object]:
    verify_repository(api)
    branches = pages(api, "branches")
    opened = {str(obj(pr.get("head")).get("ref")) for pr in pages(api, "pulls?state=open")}
    merged = pages(api, "pulls?state=closed&base=main")
    candidates: list[dict[str, object]] = []
    skipped: list[dict[str, str]] = []
    for branch in branches:
        name = branch.get("name")
        if not isinstance(name, str) or not BRANCH.fullmatch(name):
            continue
        sha = obj(branch.get("commit")).get("sha")
        reason = ""
        if branch.get("protected") is not False:
            reason = "protected_or_unknown"
        elif name in active:
            reason = "active_worktree"
        elif name in opened:
            reason = "open_pr"
        elif not isinstance(sha, str) or not SHA.fullmatch(sha):
            reason = "invalid_head"
        if reason:
            skipped.append({"branch": name, "reason": reason})
            continue
        assert isinstance(sha, str)
        proof = next((pr for pr in merged if merge_matches(pr, name, sha, now)), None)
        if proof is None:
            skipped.append({"branch": name, "reason": "no_old_exact_main_merge"})
            continue
        committed = commit_time(api, sha)
        if now - stamp(committed) <= AGE:
            skipped.append({"branch": name, "reason": "recent_commit"})
            continue
        number = proof.get("number")
        if type(number) is not int or number <= 0:
            raise ValueError("Invalid pull request identity")
        candidates.append(
            {"branch": name, "sha": sha, "pr": number, "merged_at": proof["merged_at"], "committed_at": committed}
        )
    return {
        "schema": SCHEMA,
        "repository": REPOSITORY,
        "created_at": now.isoformat(),
        "candidates": candidates,
        "skipped": skipped,
    }


def load_manifest(path: Path, now: datetime) -> tuple[list[dict[str, object]], str]:
    content = path.read_bytes()
    manifest = obj(json.loads(content))
    if set(manifest) != {"schema", "repository", "created_at", "candidates", "skipped"}:
        raise ValueError("Unexpected manifest fields")
    if manifest["schema"] != SCHEMA or manifest["repository"] != REPOSITORY:
        raise ValueError("Unexpected manifest identity")
    age = now - stamp(manifest["created_at"])
    if age < timedelta(0) or age > TTL:
        raise ValueError("Manifest expired or future dated")
    raw = manifest["candidates"]
    if not isinstance(raw, list) or not isinstance(manifest["skipped"], list):
        raise ValueError("Invalid manifest lists")
    for item in manifest["skipped"]:
        skipped = obj(item)
        if (
            set(skipped) != {"branch", "reason"}
            or not isinstance(skipped["branch"], str)
            or not BRANCH.fullmatch(skipped["branch"])
            or skipped["reason"]
            not in (
                "protected_or_unknown",
                "active_worktree",
                "open_pr",
                "invalid_head",
                "no_old_exact_main_merge",
                "recent_commit",
            )
        ):
            raise ValueError("Invalid skipped branch record")
    result: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in raw:
        row = obj(item)
        if set(row) != {"branch", "sha", "pr", "merged_at", "committed_at"}:
            raise ValueError("Unexpected candidate fields")
        branch, sha, number = row["branch"], row["sha"], row["pr"]
        if not isinstance(branch, str) or not BRANCH.fullmatch(branch) or branch in seen:
            raise ValueError("Unsafe or duplicate branch")
        if not isinstance(sha, str) or not SHA.fullmatch(sha) or type(number) is not int or number <= 0:
            raise ValueError("Invalid candidate identity")
        if now - stamp(row["merged_at"]) <= AGE or now - stamp(row["committed_at"]) <= AGE:
            raise ValueError("Candidate is not old enough")
        seen.add(branch)
        result.append(row)
    return result, hashlib.sha256(content).hexdigest()


def save(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def apply(
    api: API, manifest: Path, results: Path, now: datetime, active_worktrees: Callable[[], set[str]] = worktrees
) -> Receipt:
    if manifest.resolve() == results.resolve():
        raise ValueError("Manifest and results must be separate")
    candidates, manifest_sha256 = load_manifest(manifest, now)
    verify_repository(api)
    outcomes: list[dict[str, str]] = []
    receipt: Receipt = {
        "repository": REPOSITORY,
        "schema": SCHEMA + ".results",
        "manifest_sha256": manifest_sha256,
        "outcomes": outcomes,
    }
    save(results, receipt)
    for candidate in candidates:
        branch, sha = str(candidate["branch"]), str(candidate["sha"])
        try:
            current = obj(api.request("GET", "branches/" + quote(branch, safe="")))
            if (
                current.get("name") != branch
                or current.get("protected") is not False
                or obj(current.get("commit")).get("sha") != sha
            ):
                raise ValueError("head_or_protection_changed")
            if branch in active_worktrees():
                raise ValueError("active_worktree")
            pr = obj(api.request("GET", "pulls/" + str(candidate["pr"])))
            if not merge_matches(pr, branch, sha, now) or pr.get("merged_at") != candidate["merged_at"]:
                raise ValueError("merge_proof_changed")
            committed = commit_time(api, sha)
            if committed != candidate["committed_at"] or now - stamp(committed) <= AGE:
                raise ValueError("commit_age_changed")
            opened = pages(
                api, "pulls?" + urlencode({"state": "open", "head": REPOSITORY.split("/")[0] + ":" + branch})
            )
            if opened:
                raise ValueError("open_pr")
            # The provider has no expected-SHA precondition. This final read narrows,
            # but cannot eliminate, the read/delete race.
            final = obj(api.request("GET", "branches/" + quote(branch, safe="")))
            if (
                final.get("name") != branch
                or final.get("protected") is not False
                or obj(final.get("commit")).get("sha") != sha
                or branch in active_worktrees()
            ):
                raise ValueError("head_or_protection_changed")
            api.request("DELETE", "git/refs/heads/" + quote(branch, safe=""))
            outcomes.append({"branch": branch, "status": "deleted", "reason": "provider_confirmed"})
        except ValueError:
            outcomes.append(
                {"branch": branch, "status": "skipped", "reason": "eligibility_changed_or_invalid_response"}
            )
        except (RuntimeError, OSError, subprocess.SubprocessError):
            outcomes.append(
                {
                    "branch": branch,
                    "status": "failed",
                    "reason": "provider_or_local_request_failed_outcome_may_be_unknown",
                }
            )
        save(results, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "apply"))
    parser.add_argument("--manifest", type=Path, default=Path(".factory/branch-hygiene/manifest.json"))
    parser.add_argument("--results", type=Path, default=Path(".factory/branch-hygiene/results.json"))
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        if args.mode == "plan":
            save(args.manifest, plan(GitHub(), worktrees(), now))
        else:
            receipt = apply(GitHub(), args.manifest, args.results, now)
            if any(obj(row).get("status") == "failed" for row in receipt["outcomes"]):
                return 1
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError):
        print("Branch hygiene stopped: invalid inputs or unavailable verified provider state")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
