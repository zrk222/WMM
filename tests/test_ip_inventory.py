import json
import tomllib
import unittest
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/ip-inventory.json"


class IpInventoryTests(unittest.TestCase):
    def load(self) -> dict[str, object]:
        return cast(
            dict[str, object],
            json.loads(INVENTORY.read_text(encoding="utf-8")),
        )

    def test_every_locked_rust_crate_is_inventoried(self) -> None:
        value = self.load()
        components = cast(list[dict[str, object]], value["components"])
        rust = {
            (cast(str, item["name"]), cast(str, item["version"])) for item in components if item["kind"] == "rust-crate"
        }
        for relative in (
            "desktop/src-tauri/Cargo.lock",
            "desktop/launcher/Cargo.lock",
        ):
            lock = cast(
                dict[str, object],
                tomllib.loads((ROOT / relative).read_text(encoding="utf-8")),
            )
            for package in cast(list[dict[str, object]], lock["package"]):
                key = (cast(str, package["name"]), cast(str, package["version"]))
                self.assertIn(key, rust, relative)

    def test_shipped_components_have_declared_licenses(self) -> None:
        value = self.load()
        components = cast(list[dict[str, object]], value["components"])
        for item in components:
            if item["shipped"]:
                self.assertNotIn(
                    cast(str, item["license"]),
                    ("", "UNKNOWN"),
                    cast(str, item["name"]),
                )
        self.assertEqual(value["component_count"], len(components))

    def test_open_items_are_explicit(self) -> None:
        value = self.load()
        open_items = cast(list[dict[str, object]], value["open_items"])
        ids = {cast(str, item["id"]) for item in open_items}
        for required in (
            "OWNERSHIP-CHAIN",
            "AGENT-ASSISTED",
            "SHIPPED-SBOM",
        ):
            self.assertIn(required, ids)


if __name__ == "__main__":
    unittest.main()
