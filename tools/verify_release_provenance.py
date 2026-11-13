"""Verify official GitHub provenance for the six staged desktop release payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

REPOSITORY = "zrk222/WMM"
SIGNER_WORKFLOW = REPOSITORY + "/.github/workflows/desktop-release.yml"
PREDICATE = "https://slsa.dev/provenance/v1"
BUNDLE_NAME = "release-attestation.sigstore.json"
RECEIPT_NAME = "release-provenance.json"


class AssetProof(TypedDict):
    name: str
    sha256: str
    verification_count: int
    verification_output_sha256: str
    verification_output: str


class Receipt(TypedDict):
    schema: str
    repository: str
    signer_workflow: str
    source_sha: str
    verified_at: str
    assets: list[AssetProof]
    bundle: dict[str, str]
    deny_self_hosted_runners: bool


def payload_names() -> set[str]:
    """Reuse the publisher's platform contract without creating SHA256SUMS.txt."""
    assets = runpy.run_path(str(Path(__file__).with_name("publish_desktop_release.py")))["ASSETS"]
    if not isinstance(assets, dict) or set(assets) != {"Windows", "Linux"}:
        raise ValueError("Unsupported publisher platform contract")
    names: set[str] = set()
    for platform, name in assets.items():
        if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("Unsafe publisher payload name")
        names.update((name, platform + ".json", "sbom-" + platform + ".json"))
    if len(names) != 6:
        raise ValueError("Expected six publisher payloads")
    return names


def staged_files(folder: Path) -> list[Path]:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("Expected a regular staging directory")
    paths = sorted(folder.iterdir())
    if {path.name for path in paths} != payload_names():
        raise ValueError("Stage exactly the six publisher payloads before checksum creation")
    for path in paths:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size == 0:
            raise ValueError("Release payloads must be nonempty regular files")
    return paths


def digest(path: Path) -> str:
    if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
        raise ValueError("Release payload type changed")
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verification_count(output: str, checksum: str) -> int:
    value = json.loads(output)
    if not isinstance(value, list) or not value:
        raise ValueError("No successful verification results")
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("attestation"), dict) or not item["attestation"]:
            raise ValueError("Missing verified attestation")
        verified = item.get("verificationResult")
        statement = verified.get("statement") if isinstance(verified, dict) else None
        subjects = statement.get("subject") if isinstance(statement, dict) else None
        if (
            not isinstance(statement, dict)
            or statement.get("predicateType") != PREDICATE
            or not isinstance(subjects, list)
            or not any(
                isinstance(subject, dict)
                and isinstance(subject.get("digest"), dict)
                and subject["digest"].get("sha256") == checksum
                for subject in subjects
            )
        ):
            raise ValueError("Verification result does not bind the payload digest")
    return len(value)


def verify_asset(path: Path, sha: str, checksum: str, bundle: Path | None = None) -> AssetProof:
    args = [
        "gh",
        "attestation",
        "verify",
        str(path.resolve()),
        "--hostname",
        "github.com",
        "--repo",
        REPOSITORY,
        "--signer-workflow",
        SIGNER_WORKFLOW,
        "--source-digest",
        sha,
        "--deny-self-hosted-runners",
        "--format",
        "json",
    ]
    if bundle is not None:
        args.extend(("--bundle", str(bundle.resolve())))
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=120, check=False)
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise RuntimeError("Official provenance verifier failed") from None
    if result.returncode != 0 or not isinstance(result.stdout, str):
        # Provider output can contain private authentication details. Do not relay it.
        raise RuntimeError("Official provenance verifier failed")
    try:
        count = verification_count(result.stdout, checksum)
    except (ValueError, UnicodeError):
        raise RuntimeError("Official provenance verifier returned no valid payload proof") from None
    return {
        "name": path.name,
        "sha256": checksum,
        "verification_count": count,
        "verification_output_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        "verification_output": result.stdout,
    }


def verify(folder: Path, sha: str, receipt: Path, bundle: Path | None = None) -> Receipt:
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("Expected exact lowercase source commit SHA")
    if receipt.resolve().is_relative_to(folder.resolve()):
        raise ValueError("Keep the proof receipt outside the staged release assets")
    if receipt.exists() or receipt.is_symlink():
        raise ValueError("An existing proof receipt cannot be overwritten")
    paths = staged_files(folder)
    bundle_bytes = None
    bundle_hash = None
    if bundle is not None:
        if bundle.resolve().is_relative_to(folder.resolve()) or bundle.is_symlink():
            raise ValueError("Keep original action bundle outside the release stage")
        bundle_hash = digest(bundle)
        bundle_bytes = bundle.read_bytes()
        if not bundle_bytes or hashlib.sha256(bundle_bytes).hexdigest() != bundle_hash:
            raise ValueError("Action bundle is empty or changed")
    before = {path.name: digest(path) for path in paths}
    proofs: list[AssetProof] = []
    for path in paths:
        if digest(path) != before[path.name]:
            raise ValueError("Release payload changed before verification")
        proofs.append(verify_asset(path, sha, before[path.name], bundle))
        if digest(path) != before[path.name]:
            raise ValueError("Release payload changed during verification")
    if {path.name: digest(path) for path in staged_files(folder)} != before:
        raise ValueError("Release stage changed before receipt creation")
    value: Receipt = {
        "schema": "wmm.release-provenance.v1",
        "repository": REPOSITORY,
        "signer_workflow": SIGNER_WORKFLOW,
        "source_sha": sha,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "assets": proofs,
        "bundle": {},
        "deny_self_hosted_runners": True,
    }
    if bundle is not None:
        assert bundle_hash is not None and bundle_bytes is not None
        if digest(bundle) != bundle_hash:
            raise ValueError("Action bundle changed during verification")
        value["schema"] = "wmm.release-provenance.v2"
        value["bundle"] = {"name": BUNDLE_NAME, "sha256": bundle_hash}
        # Stage only after every verification passed. Never attest or hash a self-reference.
        with (folder / BUNDLE_NAME).open("xb") as stream:
            stream.write(bundle_bytes)
        with (folder / RECEIPT_NAME).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(value, indent=2) + "\n")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    with receipt.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--receipt", type=Path, default=Path(".factory/release-provenance.json"))
    parser.add_argument("--bundle", type=Path, help="Exact bundle-path output from actions/attest-build-provenance")
    args = parser.parse_args()
    try:
        verify(args.folder, args.sha, args.receipt, args.bundle)
    except (ValueError, RuntimeError, OSError):
        print("Release provenance verification failed; publication is blocked")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
