"""Replay historical WMM proof receipts without changing the checkout."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PureWindowsPath
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/evidence/archive-index.json"


class ArchiveEntry(TypedDict):
    path: str
    archive_commit: str
    replay_commit: str
    size_bytes: int
    sha256: str
    observations_sha256: str


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def checked_path(value: object) -> str:
    if not isinstance(value, str) or any(
        not re.fullmatch(r"[A-Za-z0-9_.-]+", part)
        or part in {".", ".."}
        or part.endswith(".")
        or PureWindowsPath(part).is_reserved()
        for part in value.split("/")
    ):
        raise ValueError(f"invalid archive path: {value!r}")
    return value


def require_hex(value: object, length: int) -> str:
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError(f"invalid {length}-character hexadecimal identity")
    return value


def bound_bytes(data: bytes, expected: str, *, normalize: bool = False) -> bytes:
    require_hex(expected, 64)
    if digest(data) == expected:
        return data
    if normalize and b"\0" not in data:
        lf = data.replace(b"\r\n", b"\n")
        for variant in (lf, lf.replace(b"\n", b"\r\n")):
            if digest(variant) == expected:
                return variant
    raise ValueError("SHA-256 mismatch")


def git_blob(repo: Path, commit: str, path: str) -> bytes:
    require_hex(commit, 40)
    checked_path(path)
    result = subprocess.run(
        ["git", "--no-replace-objects", "cat-file", "blob", f"{commit}:{path}"],
        cwd=repo,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"missing Git history: {commit}:{path}; use a full clone")
    return result.stdout


def replay(repo: Path, item: ArchiveEntry) -> dict[str, object]:
    path = checked_path(item["path"])
    parent = path.rsplit("/", 1)[0]
    contract_path = f"{parent}/workflow-contract.json"
    obs_path = f"{parent}/workflow-observations.json"
    revision = item["replay_commit"]
    archived = bound_bytes(git_blob(repo, item["archive_commit"], path), item["sha256"])
    if type(item["size_bytes"]) is not int or len(archived) != item["size_bytes"]:
        raise ValueError("archived size mismatch")

    obs_bytes = bound_bytes(git_blob(repo, revision, obs_path), item["observations_sha256"])
    obs = json.loads(obs_bytes)
    contract_bytes = bound_bytes(
        git_blob(repo, revision, contract_path),
        obs["contract_sha256"],
        normalize=True,
    )
    contract = json.loads(contract_bytes)
    refs = list(contract["candidate"])
    refs.extend(
        row["review_evidence"] for row in contract["applicability"] if "review_evidence" in row
    )
    refs.extend(ref for row in obs["observations"] for ref in row["artifacts"])
    expected = {}
    folded = {p.casefold(): p for p in (contract_path, obs_path)}
    for ref in refs:
        name = checked_path(ref["path"])
        sha = require_hex(ref["sha256"], 64)
        if (
            name in (contract_path, obs_path)
            or folded.setdefault(name.casefold(), name) != name
            or expected.setdefault(name, sha) != sha
        ):
            raise ValueError(f"conflicting evidence path: {name}")
    if expected.get(path) != item["sha256"]:
        raise ValueError("historical observations do not bind the archived blob")

    with tempfile.TemporaryDirectory(prefix="wmm-evidence-") as folder:
        temp = Path(folder)
        for name in (*expected, contract_path, obs_path):
            if name == path:
                data = archived
            elif name == contract_path:
                data = contract_bytes
            elif name == obs_path:
                data = obs_bytes
            else:
                data = bound_bytes(git_blob(repo, revision, name), expected[name], normalize=True)
            destination = temp / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as output:
                output.write(data)
        check = subprocess.run(
            [
                "factory",
                "audit",
                "workflows",
                "--root",
                ".",
                "--contract",
                contract_path,
                "--observations",
                obs_path,
                "--json",
            ],
            cwd=temp,
            capture_output=True,
            timeout=120,
            check=False,
        )
        receipt = json.loads(check.stdout)
        passed = check.returncode == 0 and receipt["state"] == "PASS"
        return {
            "path": path,
            "state": "PASS" if passed else "FAIL",
            "exit": check.returncode,
            "verifier_state": receipt["state"],
            "errors": receipt.get("errors", []),
            "replay_commit": revision,
            "inputs": len(expected),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    index = json.loads(INDEX.read_bytes())
    entries = index.get("artifacts") if isinstance(index, dict) else None
    if (
        not isinstance(entries, list)
        or not 1 <= len(entries) <= 32
        or index.get("schema") != "wmm.evidence-archive.v1"
        or not all(isinstance(item, dict) for item in entries)
    ):
        parser.error("unsupported or empty archive index")
    results = []
    for item in entries:
        try:
            results.append(replay(ROOT, item))
        except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
            results.append({"path": item.get("path"), "state": "FAIL", "error": str(error)})
    print(
        json.dumps({"scope": "Historical receipt verification only", "results": results}, indent=2)
    )
    return 0 if all(row["state"] == "PASS" for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
