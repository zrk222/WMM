"""Build a deterministic CycloneDX shipped-component SBOM from the IP inventory."""

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import cast
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/ip-inventory.json"
SHA = re.compile(r"[a-f0-9]{40}")


def _license(value: object) -> list[dict[str, object]]:
    if not isinstance(value, str) or not value.strip():
        return []
    return [{"license": {"name": value.strip()}}]


def _bom_ref(item: dict[str, object]) -> str:
    kind = str(item.get("kind"))
    name = quote(str(item.get("name")), safe="")
    version = quote(str(item.get("version")), safe="")
    prefixes = {
        "rust-crate": "pkg:cargo/",
        "python-package": "pkg:pypi/",
        "python-runtime": "pkg:generic/python@",
    }
    prefix = prefixes.get(kind, "urn:wmm:" + kind + ":")
    if kind in ("python-runtime", "python-package"):
        return "pkg:pypi/" + name.lower().replace("_", "-") + "@" + version
    if kind == "rust-crate":
        return prefix + name + "@" + version
    return prefix + name + "@" + version


def build(sha: str, platform: str) -> dict[str, object]:
    if not SHA.fullmatch(sha):
        raise ValueError("A lowercase 40-character source SHA is required")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", platform):
        raise ValueError("A simple platform label is required")
    raw = INVENTORY.read_bytes()
    value = cast(dict[str, object], json.loads(raw.decode("utf-8")))
    items = [item for item in cast(list[dict[str, object]], value["components"]) if item.get("shipped") is True]
    components = []
    refs = set()
    for item in items:
        ref = _bom_ref(item)
        if ref in refs:
            continue
        refs.add(ref)
        component = {
            "type": "library",
            "bom-ref": ref,
            "name": item.get("name"),
            "version": item.get("version"),
            "properties": [
                {"name": "wmm:kind", "value": item.get("kind")},
                {"name": "wmm:status", "value": item.get("status")},
                {"name": "wmm:evidence", "value": item.get("evidence")},
            ],
        }
        licenses = _license(item.get("license"))
        if licenses:
            component["licenses"] = licenses
        components.append(component)
    components.sort(key=lambda item: str(item["bom-ref"]))
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "wmm",
                "version": sha,
                "properties": [
                    {"name": "wmm:platform", "value": platform},
                    {"name": "wmm:inventory_scope", "value": "shipped_components"},
                    {
                        "name": "wmm:ip_inventory_sha256",
                        "value": hashlib.sha256(raw).hexdigest(),
                    },
                ],
            },
        },
        "components": components,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    path = Path(args.output)
    if not path.parent.is_dir():
        raise SystemExit("Output directory does not exist: " + str(path.parent))
    value = build(args.sha, args.platform)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    components = cast(list[object], value["components"])
    print(f"SBOM {path} components={len(components)} platform={args.platform}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
