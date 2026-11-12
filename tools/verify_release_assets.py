"""Verify a downloaded WMM release folder without network or publishing access."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

EXPECTED = {"Windows": "WMM-Setup.exe", "Linux": "wize-marketing-machine_0.1.0_amd64.deb"}
RECEIPTS = {platform + ".json" for platform in EXPECTED}
SBOMS = {"sbom-" + platform + ".json" for platform in EXPECTED}
PAYLOADS = set(EXPECTED.values()) | RECEIPTS | SBOMS
LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checksums(manifest: Path) -> dict[str, str]:
    values = {}
    for number, line in enumerate(manifest.read_text(encoding="ascii").splitlines(), 1):
        match = LINE.fullmatch(line)
        if not match:
            raise ValueError(f"Invalid checksum line {number}")
        checksum, name = match.groups()
        if name in values or name in ("", ".", "..") or "/" in name or "\\" in name:
            raise ValueError("Duplicate or unsafe checksum entry: " + name)
        values[name] = checksum
    if not values:
        raise ValueError("Checksum manifest is empty")
    return values


def object_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: " + path.name)
    return value


def verify_files(paths, source_sha: str | None) -> dict:
    """Validate the exact file set used by both the publisher and offline verifier."""
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Use a lowercase 40-character source SHA")
    expected_files = PAYLOADS | {"SHA256SUMS.txt"}
    entries = {path.name: path for path in paths}
    if len(entries) != len(paths) or set(entries) != expected_files:
        raise ValueError("Release folder must contain exactly the installers, receipts, SBOMs and checksum manifest")
    for path in entries.values():
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Release asset must be a nonempty regular file: " + path.name)
    listed = checksums(entries["SHA256SUMS.txt"])
    if set(listed) != PAYLOADS:
        raise ValueError("Checksum manifest must cover exactly the six payload files")
    for name, expected in listed.items():
        path = entries[name]
        if path.is_symlink() or digest(path) != expected:
            raise ValueError("Checksum mismatch: " + name)
    for platform, asset in EXPECTED.items():
        receipt_path = entries[platform + ".json"]
        receipt = object_json(receipt_path)
        if (
            receipt.get("schema") != "wmm.desktop-release.v1"
            or receipt.get("platform") != platform
            or receipt.get("status") != "PASS"
            or receipt.get("asset") != asset
            or receipt.get("sha256") != listed[asset]
        ):
            raise ValueError("Installer receipt mismatch: " + platform)
        if receipt.get("source_sha") != source_sha:
            raise ValueError("Installer source SHA mismatch: " + platform)
        lifecycle = receipt.get("lifecycle", {})
        removal = "uninstall" if platform == "Windows" else "removal"
        checks = receipt.get("restart_checks", [])
        if (
            not isinstance(lifecycle, dict)
            or lifecycle.get("status") != "PASS"
            or lifecycle.get("workspace") != "SYNTHETIC_PRESERVED"
            or any(lifecycle.get(key) != "VERIFIED" for key in ("install", "upgrade", removal))
            or not isinstance(checks, list)
            or len(checks) != 2
            or any(not isinstance(row, dict) for row in checks)
            or [row.get("phase") for row in checks] != ["fresh", "upgrade"]
            or any(
                row.get("offline_restart") != "PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE"
                or row.get("network") != "BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE"
                or not isinstance(row.get("evidence_sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", row["evidence_sha256"])
                for row in checks
            )
        ):
            raise ValueError("Installer lifecycle receipt mismatch: " + platform)
        sbom_path = entries["sbom-" + platform + ".json"]
        sbom = object_json(sbom_path)
        metadata = sbom.get("metadata")
        component = metadata.get("component") if isinstance(metadata, dict) else None
        raw_properties = component.get("properties") if isinstance(component, dict) else None
        if not isinstance(raw_properties, list) or any(
            not isinstance(row, dict) or not isinstance(row.get("name"), str) for row in raw_properties
        ):
            raise ValueError("SBOM component properties are invalid: " + platform)
        properties = {row["name"]: row.get("value") for row in raw_properties}
        if len(properties) != len(raw_properties):
            raise ValueError("SBOM component properties are duplicated: " + platform)
        if (
            sbom.get("bomFormat") != "CycloneDX"
            or sbom.get("specVersion") != "1.5"
            or properties.get("wmm:platform") != platform
            or properties.get("wmm:inventory_scope") != "build_environment"
            or not isinstance(sbom.get("components"), list)
        ):
            raise ValueError("SBOM mismatch: " + platform)
        if component.get("version") != source_sha:
            raise ValueError("SBOM source SHA mismatch: " + platform)
    return {"status": "PASS", "files": len(listed), "source_sha": source_sha, "platforms": sorted(EXPECTED)}


def verify(folder: Path, source_sha: str | None = None) -> dict:
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError("Release folder is missing")
    return dict(verify_files(list(folder.iterdir()), source_sha), folder=str(folder))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(verify(Path(args.folder), args.source_sha), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
