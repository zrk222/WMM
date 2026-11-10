"""Build a deterministic CycloneDX 1.5 inventory of installed build dependencies."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import re


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def license_name(metadata) -> str | None:
    value = metadata.get("License-Expression") or metadata.get("License")
    if value and value.strip() and value.strip().upper() != "UNKNOWN":
        return value.strip()
    for classifier in metadata.get_all("Classifier") or []:
        prefix = "License ::"
        if classifier.startswith(prefix):
            return classifier[len(prefix):].strip()
    return None


def component(distribution) -> dict:
    metadata = distribution.metadata
    name = metadata.get("Name") or "unknown"
    version = distribution.version or "unknown"
    purl = f"pkg:pypi/{normalize(name)}@{version}"
    value = {
        "type": "library",
        "bom-ref": purl,
        "name": name,
        "version": version,
        "purl": purl,
    }
    license_value = license_name(metadata)
    if license_value:
        value["licenses"] = [{"license": {"name": license_value}}]
    return value


def build(source_sha: str, platform: str, distributions=None) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("A lowercase 40-character source SHA is required")
    if not platform or not re.fullmatch(r"[A-Za-z0-9._-]+", platform):
        raise ValueError("A simple platform label is required")
    if distributions is None:
        distributions = importlib.metadata.distributions()
    components = {}
    for distribution in distributions:
        value = component(distribution)
        components[value["bom-ref"]] = value
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "wmm",
                "version": source_sha,
                "properties": [
                    {"name": "wmm:platform", "value": platform},
                    {"name": "wmm:inventory_scope", "value": "build_environment"},
                ],
            },
        },
        "components": [components[key] for key in sorted(components)],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--platform", required=True)
    args = parser.parse_args(argv)
    path = Path(args.output)
    if not path.parent.is_dir():
        raise SystemExit("Output directory does not exist: " + str(path.parent))
    value = build(args.source_sha, args.platform)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SBOM {path} components={len(value['components'])} platform={args.platform}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
