import hashlib
import importlib.util
import json
import re
import shutil
import tempfile
import tomllib
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

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

    def test_published_digest_matches_canonical_inventory_bytes(self) -> None:
        guide = (ROOT / "docs/IP-INVENTORY.md").read_text(encoding="utf-8")
        recorded = re.search(r"Inventory SHA-256 \(UTF-8, LF\): `([a-f0-9]{64})`", guide)
        assert recorded is not None
        canonical_bytes = INVENTORY.read_text(encoding="utf-8").encode("utf-8")
        self.assertEqual(recorded.group(1), hashlib.sha256(canonical_bytes).hexdigest())

    def test_unbundled_ubuntu_requirements_match_installer_control(self) -> None:
        value = self.load()
        observed = cast(dict[str, object], value["ubuntu_declared_runtime_dependencies"])
        self.assertEqual(observed["source"], "packaging/linux/control")
        self.assertEqual(observed["native_builder_source"], "tools/build_linux_package.py")
        self.assertEqual(observed["exact_installed_versions_and_licenses"], "RELEASE_HOST_RECONCILIATION_OPEN")

        def verify(stage: Path, _destination: Path) -> None:
            metadata = (stage / "DEBIAN/control").read_text(encoding="utf-8")
            declared = next(
                line.removeprefix("Depends: ") for line in metadata.splitlines() if line.startswith("Depends: ")
            )
            self.assertEqual(observed[key], [item.strip() for item in declared.split(",")])

        spec = importlib.util.spec_from_file_location(
            "wmm_linux_inventory_builder", ROOT / "tools/build_linux_package.py"
        )
        assert spec is not None and spec.loader is not None
        build_linux_package = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build_linux_package)
        build = cast(Callable[[], None], vars(build_linux_package)["main"])
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            shutil.copytree(ROOT / "packaging/linux", base / "packaging/linux")
            bundle = base / "dist/desktop/WMM"
            bundle.mkdir(parents=True)
            (bundle / "WMM").touch()
            with (
                patch.object(build_linux_package, "ROOT", base),
                patch.object(build_linux_package, "sys", SimpleNamespace(platform="linux")),
                patch.object(build_linux_package, "platform", SimpleNamespace(machine=lambda: "amd64")),
                patch.object(build_linux_package, "archive", side_effect=verify) as archive,
            ):
                key = "baseline_template_packages"
                build()
                (bundle / "WMM-Mission-Control").touch()
                key = "native_public_installer_packages"
                build()
                self.assertEqual(archive.call_count, 2)
        components = cast(list[dict[str, object]], value["components"])
        by_name = {item["name"]: item for item in components}
        self.assertIn("ffmpeg", cast(list[str], observed["native_public_installer_packages"]))
        self.assertFalse(by_name["FFmpeg"]["shipped"])
        self.assertEqual(by_name["FFmpeg"]["distribution"], "SYSTEM_RUNTIME")
        self.assertFalse(by_name["tauri-build"]["shipped"])

    def test_open_items_are_explicit(self) -> None:
        value = self.load()
        open_items = cast(list[dict[str, object]], value["open_items"])
        ids = {cast(str, item["id"]) for item in open_items}
        for required in (
            "OWNERSHIP-CHAIN",
            "AGENT-ASSISTED",
            "ICON-PROVENANCE",
            "SHIPPED-SBOM",
        ):
            self.assertIn(required, ids)


if __name__ == "__main__":
    unittest.main()
