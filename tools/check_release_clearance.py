"""Bind an official release-environment approval to prepared, signed artifacts."""

import argparse
import hashlib
import json
import os
import re
import runpy
import stat
from collections.abc import Callable
from pathlib import Path
from typing import cast

PUBLISHER = Path(__file__).with_name("publish_desktop_release.py")
PROVENANCE = Path(__file__).with_name("verify_release_provenance.py")
DIGEST = re.compile(r"[a-f0-9]{64}")
COMMIT = re.compile(r"[a-f0-9]{40}")
TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+-preview\.[0-9]+")
REVIEW_ENVIRONMENT = "release"


def snapshot(folder: Path, sha: str, tag: str, run_id: int, attempt: int, thumbprint: str) -> dict[str, object]:
    """Hash each attested payload and both proof files after checking Windows signing."""
    if not COMMIT.fullmatch(sha) or not TAG.fullmatch(tag) or min(run_id, attempt) < 1:
        raise ValueError("Invalid release candidate, tag or workflow invocation")
    publisher = runpy.run_path(str(PUBLISHER))
    provenance = runpy.run_path(str(PROVENANCE))
    payload_names = cast(Callable[[], set[str]], provenance["payload_names"])
    names = payload_names() | {provenance["BUNDLE_NAME"], provenance["RECEIPT_NAME"]}
    if folder.is_symlink() or not folder.is_dir() or {path.name for path in folder.iterdir()} != names:
        raise ValueError("Stage exactly the installer, lifecycle, SBOM and provenance assets")
    paths = [folder / name for name in sorted(names)]
    for path in paths:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            raise ValueError("Invalid prepared asset: " + path.name)
    publisher["require_windows_signature"](folder, thumbprint)
    hashes = {path.name: publisher["digest"](path) for path in paths}
    return {
        "schema": "wmm.prepared-desktop-release.v1",
        "source": sha,
        "tag": tag,
        "run_id": run_id,
        "attempt": attempt,
        "signer": thumbprint,
        "assets": hashes,
    }


def fingerprint(manifest: dict[str, object]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def candidate_author(metadata: object, sha: str) -> int:
    """Accept an associated GitHub author only for the exact candidate commit."""
    author = metadata.get("author") if isinstance(metadata, dict) and metadata.get("sha") == sha else None
    identity = author.get("id") if isinstance(author, dict) else None
    if type(identity) is not int or identity < 1:
        raise ValueError("GitHub did not identify the author of the exact candidate commit")
    return identity


def require_approval(
    history: object,
    reviewer_id: int,
    actor_id: int,
    candidate_author_id: int,
    triggering_actor: str,
    prepared_digest: str,
) -> str:
    """Return the private IP inventory digest reviewed for this exact preparation."""
    if (
        min(reviewer_id, actor_id, candidate_author_id) < 1
        or reviewer_id in (actor_id, candidate_author_id)
        or not triggering_actor
        or not DIGEST.fullmatch(prepared_digest)
    ):
        raise ValueError("Configure a reviewer independent of the candidate author and release dispatch")
    if not isinstance(history, list):
        raise ValueError("Invalid GitHub deployment review history")
    approved = set()
    for review in history:
        if not isinstance(review, dict):
            continue
        user = review.get("user")
        if (
            not isinstance(user, dict)
            or user.get("type") != "User"
            or type(user.get("id")) is not int
            or user["id"] != reviewer_id
            or not isinstance(user.get("login"), str)
            or not user["login"]
            or user["login"].casefold() == triggering_actor.casefold()
        ):
            continue
        environments = review.get("environments")
        if not isinstance(environments, list) or not any(
            isinstance(item, dict) and item.get("name") == REVIEW_ENVIRONMENT for item in environments
        ):
            continue
        if review.get("state") == "rejected":
            raise ValueError("Independent reviewer rejected this deployment")
        if review.get("state") != "approved":
            continue
        comment = review.get("comment")
        if not isinstance(comment, str):
            continue
        match = re.fullmatch(r"wmm-preview " + prepared_digest + r" IP-CLEARED ([a-f0-9]{64})", comment.strip())
        if match:
            approved.add(match.group(1))
    if len(approved) != 1:
        raise ValueError("Missing or inconsistent independent approval of these signed bytes")
    return approved.pop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "verify"))
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--expected")
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--candidate-metadata", type=Path)
    args = parser.parse_args()
    manifest = snapshot(
        args.folder,
        args.sha,
        args.tag,
        int(os.environ["GITHUB_RUN_ID"]),
        int(os.environ["GITHUB_RUN_ATTEMPT"]),
        os.environ["WMM_WINDOWS_SIGNER_THUMBPRINT"],
    )
    prepared = fingerprint(manifest)
    if args.mode == "prepare":
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"digest={prepared}\n")
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as summary:
            summary.write(
                f"### Prepared signed desktop release\n\nSource: {args.sha}\n\nTag: {args.tag}\n\n"
                f"Review fingerprint: {prepared}\n\n"
                f"Approve this deployment with: wmm-preview {prepared} IP-CLEARED <private inventory SHA-256>\n\n"
                + json.dumps(manifest, indent=2)
                + "\n"
            )
        return
    if prepared != args.expected:
        raise ValueError("Prepared release bytes or invocation no longer match")
    if args.reviews is None or args.reviews.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Missing or oversized deployment review history")
    if args.candidate_metadata is None or args.candidate_metadata.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Missing or oversized GitHub candidate metadata")
    author = candidate_author(json.loads(args.candidate_metadata.read_text(encoding="utf-8")), args.sha)
    inventory_digest = require_approval(
        json.loads(args.reviews.read_text(encoding="utf-8")),
        int(os.environ["WMM_RELEASE_REVIEWER_ID"]),
        int(os.environ["GITHUB_ACTOR_ID"]),
        author,
        os.environ["GITHUB_TRIGGERING_ACTOR"],
        prepared,
    )
    print(json.dumps({"prepared_release_sha256": prepared, "reviewed_inventory_sha256": inventory_digest}))


if __name__ == "__main__":
    main()
