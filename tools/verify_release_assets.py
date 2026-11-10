"""Verify a downloaded WMM release folder without network or publishing access."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

EXPECTED = {"Windows": "WMM-Setup.exe", "Linux": "wize-marketing-machine_0.1.0_amd64.deb"}
HEX = re.compile(r"[0-9a-f]{64}")
LINE = re.compile(r"([0-9a-f]{64})  ([A-Za-z0-9._-]+)")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checksums(folder: Path) -> dict[str, str]:
    manifest = folder / "SHA256SUMS.txt"
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


def verify(folder: Path, source_sha: str | None = None) -> dict:
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError("Release folder is missing")
    if source_sha is not None and not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Use a lowercase 40-character source SHA")
    listed = checksums(folder)
    present = {path.name for path in folder.iterdir() if path.is_file() and path.name != "SHA256SUMS.txt"}
    if present != set(listed):
        missing = sorted(set(listed) - present)
        extra = sorted(present - set(listed))
        raise ValueError("Checksum coverage mismatch; missing=" + str(missing) + " extra=" + str(extra))
    for name, expected in listed.items():
        path = folder / name
        if path.is_symlink() or digest(path) != expected:
            raise ValueError("Checksum mismatch: " + name)
    for platform, asset in EXPECTED.items():
        receipt_path = folder / (platform + ".json")
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if (receipt.get("schema") != "wmm.desktop-release.v1" or receipt.get("platform") != platform
                or receipt.get("status") != "PASS" or receipt.get("asset") != asset
                or receipt.get("sha256") != listed.get(asset)):
            raise ValueError("Installer receipt mismatch: " + platform)
        if source_sha and receipt.get("source_sha") != source_sha:
            raise ValueError("Installer source SHA mismatch: " + platform)
        sbom_path = folder / ("sbom-" + platform + ".json")
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))
        component = sbom.get("metadata", {}).get("component", {})
        properties = {row.get("name"): row.get("value") for row in component.get("properties", [])}
        if (sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.5"
                or properties.get("wmm:platform") != platform
                or properties.get("wmm:inventory_scope") != "build_environment"
                or not isinstance(sbom.get("components"), list)):
            raise ValueError("SBOM mismatch: " + platform)
        if source_sha and component.get("version") != source_sha:
            raise ValueError("SBOM source SHA mismatch: " + platform)
    return {"status": "PASS", "folder": str(folder), "files": len(listed),
            "source_sha": source_sha or "NOT_SUPPLIED", "platforms": sorted(EXPECTED)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--source-sha")
    args = parser.parse_args(argv)
    print(json.dumps(verify(Path(args.folder), args.source_sha), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
