"""Downloaded release verification is local, complete and source-bound."""

import hashlib
import json
from shutil import copyfile
from pathlib import Path
from tests.test_desktop_release import ReleaseTests, release
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
        producer = ReleaseTests()
        producer.setUp()
        self.addCleanup(producer.doCleanups)
        for path in release.validate_assets(producer.folder, SHA):
            copyfile(path, self.folder / path.name)

    def reseal(self):
        rows = sorted(path for path in self.folder.iterdir() if path.name != "SHA256SUMS.txt")
        (self.folder / "SHA256SUMS.txt").write_text(
            "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in rows),
            encoding="ascii",
        )

    def test_complete_folder_passes_for_exact_source(self):
        value = verify_release.verify(self.folder, SHA)
        self.assertEqual(value["status"], "PASS")
        self.assertEqual(value["files"], 6)

    def test_changed_installer_and_missing_coverage_are_rejected(self):
        (self.folder / "WMM-Setup.exe").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder, SHA)

    def test_resealed_incomplete_or_extra_bundle_is_rejected(self):
        path = self.folder / "Windows.json"
        receipt = json.loads(path.read_text())
        receipt.pop("sha256")
        path.write_text(json.dumps(receipt))
        (self.folder / "WMM-Setup.exe").unlink()
        self.reseal()
        with self.assertRaisesRegex(ValueError, "exactly"):
            verify_release.verify(self.folder, SHA)

    def test_present_installer_with_missing_hash_is_rejected(self):
        path = self.folder / "Windows.json"
        data = json.loads(path.read_text())
        data.pop("sha256")
        path.write_text(json.dumps(data))
        self.reseal()
        with self.assertRaisesRegex(ValueError, "receipt mismatch"):
            verify_release.verify(self.folder, SHA)

    def test_extra_directory_and_missing_source_are_rejected(self):
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder)
        (self.folder / "extra").mkdir()
        with self.assertRaisesRegex(ValueError, "exactly"):
            verify_release.verify(self.folder, SHA)

    def test_lifecycle_receipt_is_checked_after_checksum(self):
        path = self.folder / "Windows.json"
        data = json.loads(path.read_text())
        data["lifecycle"]["upgrade"] = "FAILED"
        path.write_text(json.dumps(data))
        self.reseal()
        with self.assertRaisesRegex(ValueError, "lifecycle"):
            verify_release.verify(self.folder, SHA)

    def test_wrong_source_or_sbom_scope_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder, "b" * 40)
        path = self.folder / "sbom-Linux.json"
        value = json.loads(path.read_text())
        value["metadata"]["component"]["properties"][1]["value"] = "runtime"
        path.write_text(json.dumps(value))
        self.reseal()
        with self.assertRaises(ValueError):
            verify_release.verify(self.folder, SHA)
