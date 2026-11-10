"""Downloaded release verification is local, complete and source-bound."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import importlib.util

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("wmm_verify_release", ROOT / "tools" / "verify_release_assets.py")
verify_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_release)
SHA = "a" * 40


class VerifyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        names = ["WMM-Setup.exe", "wize-marketing-machine_0.1.0_amd64.deb", "Windows.json", "Linux.json",
                 "sbom-Windows.json", "sbom-Linux.json"]
        for name in names:
            payload = name.encode("utf-8")
            (self.folder / name).write_bytes(payload)
        for platform, asset in verify_release.EXPECTED.items():
            digest = hashlib.sha256(asset.encode("utf-8")).hexdigest()
            (self.folder / (platform + ".json")).write_text(__import__("json").dumps(dict(
                schema="wmm.desktop-release.v1", platform=platform, status="PASS", source_sha=SHA,
                asset=asset, sha256=digest)))
            (self.folder / ("sbom-" + platform + ".json")).write_text(__import__("json").dumps(dict(
                bomFormat="CycloneDX", specVersion="1.5", components=[],
                metadata=dict(component=dict(version=SHA, properties=[
                    dict(name="wmm:platform", value=platform),
                    dict(name="wmm:inventory_scope", value="build_environment")])))))
        rows = [name for name in names if name != "SHA256SUMS.txt"]
        (self.folder / "SHA256SUMS.txt").write_text("".join(
            hashlib.sha256((self.folder / name).read_bytes()).hexdigest() + "  " + name + "\n" for name in rows),
            encoding="ascii")

    def test_complete_folder_passes_for_exact_source(self):
        value = verify_release.verify(self.folder, SHA)
        self.assertEqual(value["status"], "PASS")
        self.assertEqual(value["files"], 6)

    def test_changed_installer_and_missing_coverage_are_rejected(self):
        (self.folder / "WMM-Setup.exe").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder, SHA)
        (self.folder / "WMM-Setup.exe").write_bytes(b"WMM-Setup.exe")
        (self.folder / "extra.txt").write_bytes(b"extra")
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder)

    def test_wrong_source_or_sbom_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder, "b" * 40)
        path = self.folder / "sbom-Linux.json"
        value = __import__("json").loads(path.read_text())
        value["metadata"]["component"]["properties"][1]["value"] = "runtime"
        path.write_text(__import__("json").dumps(value))
        manifest = self.folder / "SHA256SUMS.txt"
        lines = []
        for line in manifest.read_text().splitlines():
            name = line.split("  ", 1)[1]
            lines.append(hashlib.sha256((self.folder / name).read_bytes()).hexdigest() + "  " + name)
        manifest.write_text("\n".join(lines) + "\n")
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder, SHA)
