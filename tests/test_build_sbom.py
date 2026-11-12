"""SBOM generation is deterministic and source-bound; it is not a runtime file inventory."""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wmm_build_sbom", ROOT / "tools" / "build_sbom.py")
sbom = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sbom)

SHA = "a" * 40


class FakeMetadata(dict):
    def get_all(self, key):
        return []


class FakeDistribution:
    def __init__(self, name, version, license_value=None):
        self.metadata = FakeMetadata({"Name": name, "License": license_value} if license_value else {"Name": name})
        self.version = version


class BuildSBOMTests(unittest.TestCase):
    def test_components_are_sorted_normalized_and_deduplicated(self):
        value = sbom.build(
            SHA, "Linux", [FakeDistribution("demo_app", "2.0", "MIT"), FakeDistribution("Demo.App", "2.0", "MIT")]
        )
        self.assertEqual(value["bomFormat"], "CycloneDX")
        self.assertEqual(value["metadata"]["component"]["version"], SHA)
        self.assertEqual([row["purl"] for row in value["components"]], ["pkg:pypi/demo-app@2.0"])
        self.assertEqual(value["components"][0]["licenses"], [{"license": {"name": "MIT"}}])

    def test_scope_and_platform_are_explicit(self):
        value = sbom.build(SHA, "Windows", [FakeDistribution("tzdata", "2025.3")])
        properties = {row["name"]: row["value"] for row in value["metadata"]["component"]["properties"]}
        self.assertEqual(properties["wmm:platform"], "Windows")
        self.assertEqual(properties["wmm:inventory_scope"], "build_environment")

    def test_invalid_source_identity_rejects(self):
        with self.assertRaises(ValueError):
            sbom.build("not-a-sha", "Linux", [])
        with self.assertRaises(ValueError):
            sbom.build(SHA, "", [])
