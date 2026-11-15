"""Validate exact dependency pins and prepare only reviewed official FFmpeg pin changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import runpy
from pathlib import Path
from typing import TypedDict

ROOT = Path(__file__).resolve().parents[1]
PIN = "tools/ffmpeg-pin.json"
VERSION = r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
LOCKS = (
    "requirements.txt",
    "docs/requirements-dev.txt",
    "docs/requirements-properties.txt",
    "docs/requirements-audit.txt",
)


class Update(TypedDict):
    changed: bool
    version: str
    sha256: str
    url: str
    pin_before: str
    pin_after: str


def object_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("Expected metadata object")
    return value


def validate_pins(root: Path) -> int:
    direct = [
        line
        for line in (root / "docs/requirements-audit.in").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    if (
        len(direct) != 1
        or not re.fullmatch(r"pip-audit==[0-9]+\.[0-9]+\.[0-9]+", direct[0])
        or re.search(
            r"^" + re.escape(direct[0]) + r"(?:\s|$)", (root / "docs/requirements-audit.txt").read_text(), re.MULTILINE
        )
        is None
    ):
        raise ValueError("Audit tool input and lock must retain the same exact version")
    count = 0
    for relative in LOCKS:
        source = (root / relative).read_text(encoding="utf-8").replace("\\\n", " ")
        for line in source.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*==[A-Za-z0-9][A-Za-z0-9.+_-]*(?:\s|;|$)", line):
                raise ValueError("Requirements must retain exact package versions")
            hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})(?=\s|$)", line)
            if not hashes or line.count("--hash=") != len(hashes):
                raise ValueError("Every locked requirement needs valid SHA256 hashes")
            remainder = re.sub(r"\s*--hash=sha256:[0-9a-f]{64}", "", line)
            if "--" in remainder or " @ " in remainder:
                raise ValueError("Unexpected requirements options")
            count += 1
    package = object_value(json.loads((root / "package.json").read_text(encoding="utf-8")))
    lock = object_value(json.loads((root / "package-lock.json").read_text(encoding="utf-8")))
    packages = object_value(lock.get("packages"))
    locked_root = object_value(packages.get(""))
    for section in ("dependencies", "devDependencies"):
        declared = object_value(package.get(section, {}))
        if declared != object_value(locked_root.get(section, {})):
            raise ValueError("npm root pins and lock differ")
        for version in declared.values():
            if not isinstance(version, str) or not re.fullmatch(VERSION + r"(?:[-+][A-Za-z0-9.-]+)?", version):
                raise ValueError("npm dependencies require exact versions")
    for name, item in packages.items():
        if name and not re.fullmatch(r"sha(?:256|512)-[A-Za-z0-9+/]+=*", str(object_value(item).get("integrity", ""))):
            raise ValueError("npm package lock integrity is missing")
    return count


def load_pin(root: Path) -> dict[str, str]:
    path = root / PIN
    if path.is_symlink() or not path.is_file():
        raise ValueError("FFmpeg pin must be a regular data file")
    value = object_value(json.loads(path.read_text(encoding="utf-8")))
    version, digest = value.get("version"), value.get("sha256")
    if (
        set(value) != {"version", "sha256"}
        or not isinstance(version, str)
        or not re.fullmatch(VERSION, version)
        or not isinstance(digest, str)
        or not re.fullmatch(r"[0-9a-f]{64}", digest)
    ):
        raise ValueError("Expected only a stable FFmpeg version and lowercase SHA256")
    return {"version": version, "sha256": digest}


def metadata_pin(metadata: object) -> tuple[str, str, str]:
    value = object_value(metadata)
    version = value.get("tag_name")
    if (
        not isinstance(version, str)
        or not re.fullmatch(VERSION, version)
        or value.get("draft") is not False
        or value.get("prerelease") is not False
    ):
        raise ValueError("Expected an official stable FFmpeg release")
    if value.get("html_url") != "https://github.com/GyanD/codexffmpeg/releases/tag/" + version:
        raise ValueError("Unexpected FFmpeg release origin")
    assets = value.get("assets")
    name = f"ffmpeg-{version}-full_build.zip"
    if not isinstance(assets, list):
        raise ValueError("Missing FFmpeg assets")
    selected = [object_value(asset) for asset in assets if object_value(asset).get("name") == name]
    if len(selected) != 1:
        raise ValueError("Missing or ambiguous exact FFmpeg asset")
    url = f"https://github.com/GyanD/codexffmpeg/releases/download/{version}/{name}"
    digest = selected[0].get("digest")
    if (
        selected[0].get("browser_download_url") != url
        or not isinstance(digest, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
    ):
        raise ValueError("FFmpeg requires an official versioned URL and asset SHA256")
    return version, digest.removeprefix("sha256:"), url


def prepare(root: Path, metadata: object) -> Update:
    validate_pins(root)
    reviewed = runpy.run_path(str(root / "tests/test_ci_current_candidate.py"))
    if reviewed["job_digest"](".github/workflows/checks.yml") != reviewed["BASELINES"][".github/workflows/checks.yml"]:
        raise ValueError("Unreviewed workflow baseline drift")
    current = load_pin(root)
    path = root / PIN
    before = path.read_bytes()
    version, digest, url = metadata_pin(metadata)
    old, new = tuple(map(int, current["version"].split("."))), tuple(map(int, version.split(".")))
    if new < old or (new == old and digest != current["sha256"]):
        raise ValueError("Downgrades and same-version digest changes are rejected")
    changed = new > old
    after = (json.dumps({"version": version, "sha256": digest}, indent=2) + "\n").encode("utf-8") if changed else before
    if changed:
        try:
            path.write_bytes(after)
            if path.read_bytes() != after or load_pin(root) != {"version": version, "sha256": digest}:
                raise ValueError("FFmpeg pin write validation failed")
        except (OSError, ValueError):
            path.write_bytes(before)
            raise
    return {
        "changed": changed,
        "version": version,
        "sha256": digest,
        "url": url,
        "pin_before": hashlib.sha256(before).hexdigest(),
        "pin_after": hashlib.sha256(after).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("validate", "validate-pin", "prepare"))
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--receipt", type=Path, default=ROOT / ".factory/ffmpeg-update.json")
    args = parser.parse_args()
    try:
        if args.mode == "validate":
            validate_pins(ROOT)
        elif args.mode == "validate-pin":
            print(json.dumps(load_pin(ROOT), sort_keys=True))
        else:
            if args.metadata is None:
                raise ValueError("Missing official metadata file")
            result = prepare(ROOT, json.loads(args.metadata.read_text(encoding="utf-8")))
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print("changed=" + str(result["changed"]).lower())
            print("version=" + result["version"])
    except (ValueError, OSError, RuntimeError):
        print("Dependency freshness blocked by invalid pins, metadata or pin data")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
