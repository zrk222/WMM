import unittest
from pathlib import Path
import sys
import tempfile
import json
import hashlib
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_distribution import decode_text
import check_distribution as distribution


class DistributionTextEncodingTests(unittest.TestCase):
    def test_resolves_root_alias_without_allowing_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            root=base/'repo';root.mkdir()
            source=root/'safe.txt';source.write_text('safe',encoding='utf-8')
            alias=root/'..'/'repo'
            with patch.object(distribution,'ROOT',alias),patch.object(distribution,'files',return_value=[alias/'safe.txt']):
                distribution.check()
            outside=base/'outside.txt';outside.write_text('outside',encoding='utf-8')
            with patch.object(distribution,'ROOT',root),patch.object(distribution,'files',return_value=[root/'..'/'outside.txt']):
                with self.assertRaisesRegex(SystemExit,'escaping path'):
                    distribution.check()

    def test_synthetic_screenshots_require_current_manifest_and_known_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            image=root/'docs/images/overview.png'
            image.parent.mkdir(parents=True)
            data=b'\x89PNG\r\n\x1a\nsynthetic-test'
            image.write_bytes(data)
            manifest=image.parent/'provenance.json'
            manifest.write_text(json.dumps({'synthetic':True,'images':{'overview.png':hashlib.sha256(data).hexdigest()}}))
            with patch.object(distribution,'ROOT',root),patch.object(distribution,'files',return_value=[image]):
                distribution.check()
                image.write_bytes(data+b'tampered')
                with self.assertRaisesRegex(SystemExit,'mismatched'):
                    distribution.check()
                manifest.unlink()
                with self.assertRaisesRegex(SystemExit,'provenance'):
                    distribution.check()
            private=root/'private.png';private.write_bytes(data)
            with patch.object(distribution,'ROOT',root),patch.object(distribution,'files',return_value=[private]):
                with self.assertRaisesRegex(SystemExit,'operational/binary'):
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
