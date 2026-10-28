import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from check_distribution import decode_text


class DistributionTextEncodingTests(unittest.TestCase):
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
