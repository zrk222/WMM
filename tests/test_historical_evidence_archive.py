import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "wmm_evidence_replay",
    Path(__file__).resolve().parents[1] / "tools/replay_historical_evidence.py",
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class HistoricalEvidenceArchiveTests(unittest.TestCase):
    def test_archive_paths_reject_escape_and_windows_aliases(self):
        for name in (
            "../file",
            "a/../b",
            "/file",
            "a//b",
            "C:/file",
            "a\\b",
            "a/b:stream",
            "a/NUL.json",
            "a/ending.",
            "a/./b",
            "",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replay.checked_path(name)
        self.assertEqual(replay.checked_path(".factory/a/report.json"), ".factory/a/report.json")

    def test_archive_hash_requires_exact_bytes_and_valid_digest(self):
        data = b"historical\r\n"
        with self.assertRaisesRegex(ValueError, "hexadecimal identity"):
            replay.bound_bytes(data, "z" * 64)
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            replay.bound_bytes(data, replay.digest(b"historical\n"))
        self.assertEqual(
            replay.bound_bytes(data, replay.digest(b"historical\n"), normalize=True),
            b"historical\n",
        )
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            replay.bound_bytes(data, replay.digest(b"unrelated\n"), normalize=True)

    def test_missing_history_fails_with_full_clone_guidance(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing Git history.*full clone"):
                replay.git_blob(Path(directory), "0" * 40, ".factory/a/report.json")
