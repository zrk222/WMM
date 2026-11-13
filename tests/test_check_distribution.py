import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import importlib.util

spec = importlib.util.spec_from_file_location(
    "check_distribution", Path(__file__).resolve().parents[1] / "tools/check_distribution.py"
)
assert spec is not None and spec.loader is not None
distribution = importlib.util.module_from_spec(spec)
spec.loader.exec_module(distribution)
decode_text = distribution.decode_text


class DistributionTextEncodingTests(unittest.TestCase):
    def test_resolves_root_alias_without_allowing_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            root = base / "repo"
            root.mkdir()
            source = root / "safe.txt"
            source.write_text("safe", encoding="utf-8")
            alias = root / ".." / "repo"
            with (
                patch.object(distribution, "ROOT", alias),
                patch.object(distribution, "files", return_value=[alias / "safe.txt"]),
            ):
                distribution.check()
            outside = base / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            with (
                patch.object(distribution, "ROOT", root),
                patch.object(distribution, "files", return_value=[root / ".." / "outside.txt"]),
                self.assertRaisesRegex(SystemExit, "escaping path"),
            ):
                distribution.check()

    def test_synthetic_screenshots_require_current_manifest_and_known_path(self):
        for name in ("overview.png", "sample-workflow.png", "agent-task-setup.png", "goal-to-proof.png"):
            with self.subTest(name=name):
                self.check_synthetic_screenshot(name)

    def check_synthetic_screenshot(self, name):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "docs/images" / name
            image.parent.mkdir(parents=True)
            data = b"\x89PNG\r\n\x1a\nsynthetic-test"
            image.write_bytes(data)
            manifest = image.parent / "provenance.json"
            manifest.write_text(json.dumps({"synthetic": True, "images": {name: hashlib.sha256(data).hexdigest()}}))
            with patch.object(distribution, "ROOT", root), patch.object(distribution, "files", return_value=[image]):
                distribution.check()
                image.write_bytes(data + b"tampered")
                with self.assertRaisesRegex(SystemExit, "mismatched"):
                    distribution.check()
                manifest.unlink()
                with self.assertRaisesRegex(SystemExit, "provenance"):
                    distribution.check()
            private = root / "private.png"
            private.write_bytes(data)
            with (
                patch.object(distribution, "ROOT", root),
                patch.object(distribution, "files", return_value=[private]),
                self.assertRaisesRegex(SystemExit, "operational/binary"),
            ):
                distribution.check()

    def test_preview_video_requires_exact_path_hash_and_synthetic_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            media = root / "docs/media"
            media.mkdir(parents=True)
            video = media / "video-production.mp4"
            data = b"\x00\x00\x00\x18ftypisom-synthetic"
            video.write_bytes(data)
            proof = {
                "schema": "wmm.preview-video-provenance.v1",
                "synthetic": True,
                "classification": "ACTUAL_WMM_UI_SYNTHETIC_WORKSPACE",
                "social_publication": "NOT_RUN",
                "marketing_result": "NOT_ESTABLISHED",
                "assets": {video.name: hashlib.sha256(data).hexdigest()},
            }
            manifest = media / "provenance.json"
            manifest.write_text(json.dumps(proof), encoding="utf-8")
            with patch.object(distribution, "ROOT", root), patch.object(distribution, "files", return_value=[video]):
                distribution.check()
                video.write_bytes(data + b"changed")
                with self.assertRaisesRegex(SystemExit, "provenance"):
                    distribution.check()
                video.write_bytes(data)
                proof["synthetic"] = False
                manifest.write_text(json.dumps(proof), encoding="utf-8")
                with self.assertRaisesRegex(SystemExit, "provenance"):
                    distribution.check()
                manifest.unlink()
                with self.assertRaisesRegex(SystemExit, "provenance"):
                    distribution.check()

    def test_decodes_utf8_utf8_bom_and_bom_marked_utf16(self):
        self.assertEqual(decode_text("plain".encode("utf-8")), "plain")
        self.assertEqual(decode_text("bom".encode("utf-8-sig")), "bom")
        self.assertEqual(decode_text("little".encode("utf-16")), "little")
        self.assertEqual(decode_text(b"\xfe\xff" + "big".encode("utf-16-be")), "big")

    def test_rejects_unmarked_non_text_bytes(self):
        with self.assertRaises(UnicodeDecodeError):
            decode_text(b"\xff\x00\xfe\x00")


if __name__ == "__main__":
    unittest.main()
