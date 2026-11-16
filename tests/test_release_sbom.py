import importlib.util
import json
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_release_sbom", ROOT / "tools/build_release_sbom.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build = cast(Callable[[str, str], dict[str, object]], MODULE.build)

SHA = "a" * 40


class ReleaseSbomTests(unittest.TestCase):
    def test_all_shipped_inventory_components_are_in_the_sbom(self) -> None:
        inventory = cast(
            dict[str, object],
            json.loads((ROOT / "docs/ip-inventory.json").read_text(encoding="utf-8")),
        )
        items = cast(list[dict[str, object]], inventory["components"])
        shipped = [item for item in items if item.get("shipped") is True]
        value = build(SHA, "Linux")
        components = cast(list[dict[str, object]], value["components"])
        self.assertGreaterEqual(len(components), len(shipped) - 1)
        refs = [cast(str, item["bom-ref"]) for item in components]
        self.assertEqual(len(refs), len(set(refs)))
        for item in components:
            self.assertTrue(item["name"])
            self.assertTrue(item["version"])
            self.assertTrue(item["licenses"], item["name"])

    def test_metadata_is_bound_to_the_candidate_and_inventory(self) -> None:
        value = build(SHA, "Windows")
        metadata = cast(dict[str, object], value["metadata"])
        component = cast(dict[str, object], metadata["component"])
        self.assertEqual(component["version"], SHA)
        properties = {
            cast(str, item["name"]): cast(str, item["value"])
            for item in cast(list[dict[str, object]], component["properties"])
        }
        self.assertEqual(properties["wmm:inventory_scope"], "shipped_components")
        self.assertEqual(len(properties["wmm:ip_inventory_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
