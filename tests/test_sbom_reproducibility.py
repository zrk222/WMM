"""Repeated SBOM builds from shuffled inputs stay byte-identical."""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wmm_build_sbom_repeat", ROOT / "tools" / "build_sbom.py")
assert SPEC is not None and SPEC.loader is not None
sbom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sbom)

SHA = "b" * 40


class FakeMetadata(dict):
    def get_all(self, key):
        return []


class FakeDistribution:
    def __init__(self, name, version, license_value=None):
        self.metadata = FakeMetadata({"Name": name, "License": license_value} if license_value else {"Name": name})
        self.version = version


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class SBOMReproducibilityTests(unittest.TestCase):
    def test_shuffled_input_order_produces_identical_bytes(self):
        rows = [
            FakeDistribution("tzdata", "2025.3"),
            FakeDistribution("mcp", "1.30.0", "MIT"),
            FakeDistribution("cryptography", "49.0.0", "Apache-2.0"),
        ]
        first = encoded(sbom.build(SHA, "Linux", list(rows)))
        self.assertEqual(first, encoded(sbom.build(SHA, "Linux", list(reversed(rows)))))
        self.assertEqual(first, encoded(sbom.build(SHA, "Linux", rows)))


if __name__ == "__main__":
    unittest.main()
