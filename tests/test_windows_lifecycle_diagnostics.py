"""Keep exact Windows package failures diagnosable without exposing child output."""

import json
import subprocess
import unittest
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

lifecycle = run_path(str(Path(__file__).resolve().parents[1] / "tools/test_windows_installer.py"))
verify_window = lifecycle["_verify_window"]
window_failure = lifecycle["_window_failure"]


class WindowsLifecycleDiagnosticsTests(unittest.TestCase):
    def test_upgrade_failure_names_the_actual_gate_and_retains_safe_evidence(self) -> None:
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            private = "synthetic-credential-that-must-not-appear"
            child = subprocess.CalledProcessError(
                1,
                [private],
                output=private,
                stderr=private
                + "\nRuntimeError: Mission Control native window or disposable workspace was unavailable",
            )
            with (
                patch.dict(verify_window.__globals__, ROOT=folder, run=Mock(side_effect=child)),
                self.assertRaises(AssertionError) as failure,
            ):
                verify_window(
                    folder / "verifier.py",
                    folder,
                    folder,
                    {"GITHUB_SHA": "f" * 40},
                    "windows-upgrade",
                    {"status": "PASS"},
                )
            self.assertEqual(
                str(failure.exception),
                "Native window verification failed during windows-upgrade: WINDOW_OR_WORKSPACE_TIMEOUT",
            )
            self.assertTrue(failure.exception.__suppress_context__)
            saved = (folder / ".factory/packaged-native-window/windows-upgrade/evidence.json").read_text(
                encoding="utf-8"
            )
            self.assertNotIn(private, saved)
            receipt = json.loads(saved)
            self.assertEqual(receipt["source_sha"], "f" * 40)
            self.assertEqual(
                receipt["window"],
                dict(status="FAIL", phase="windows-upgrade", failure="WINDOW_OR_WORKSPACE_TIMEOUT"),
            )

    def test_unknown_child_errors_and_deadlines_do_not_echo_process_arguments(self) -> None:
        private = "synthetic-private-command"
        result = subprocess.CalledProcessError(127, [private], stderr=private)
        self.assertEqual(window_failure(result), "VERIFIER_EXIT_NONZERO")
        timeout = subprocess.TimeoutExpired([private], 90, stderr=private)
        self.assertEqual(window_failure(timeout), "VERIFIER_DEADLINE")

    def test_success_still_requires_native_window_verification(self) -> None:
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            invalid = subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"status": "PASS", "exit_code": 1})
            )
            with (
                patch.dict(verify_window.__globals__, ROOT=folder, run=Mock(return_value=invalid)),
                self.assertRaisesRegex(AssertionError, "Installed native window verification failed"),
            ):
                verify_window(folder / "verifier.py", folder, folder, {}, "windows-fresh", {"status": "PASS"})
            self.assertFalse((folder / ".factory/packaged-native-window/windows-fresh/evidence.json").exists())

    def test_verified_window_preserves_the_existing_success_receipt(self) -> None:
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            observed = {"status": "PASS", "exit_code": 0}
            completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(observed))
            check = Mock(return_value=completed)
            with patch.dict(verify_window.__globals__, ROOT=folder, run=check):
                result = verify_window(
                    folder / "verifier.py",
                    folder,
                    folder,
                    {"GITHUB_SHA": "a" * 40},
                    "windows-fresh",
                    {"status": "PASS"},
                )
            self.assertEqual(result, observed)
            check.assert_called_once()
            artifact = folder / ".factory/packaged-native-window/windows-fresh/evidence.json"
            data = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(data, dict(source_sha="a" * 40, pair={"status": "PASS"}, window=observed))


if __name__ == "__main__":
    unittest.main()
