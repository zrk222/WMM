"""Public installer sign-in configuration; no provider or private workspace access."""

import json
import os
import runpy
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from mission_control.device_signin import DeviceSignIns, bundled_client_id
from mission_control.operator_identity import Identities

ROOT = Path(__file__).resolve().parents[1]
CLIENT = "synthetic_device_client"


class PublicClientTests(unittest.TestCase):
    def test_bundle_fallback_and_explicit_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public-config.json"
            path.write_text(json.dumps({"github_device_client_id": CLIENT}), encoding="utf-8")
            with patch("mission_control.device_signin.PUBLIC_CONFIG", path), patch.dict(os.environ, {}, clear=True):
                self.assertEqual(bundled_client_id(), CLIENT)
                self.assertEqual(DeviceSignIns(Identities()).client_id, CLIENT)
                self.assertFalse(DeviceSignIns(Identities(), "").available)
                self.assertEqual(DeviceSignIns(Identities(), "explicit_client").client_id, "explicit_client")
                for override in ("", "invalid!", "runtime_client"):
                    with patch.dict(os.environ, {"WMM_GITHUB_DEVICE_CLIENT_ID": override}):
                        device = DeviceSignIns(Identities())
                        self.assertEqual(device.client_id, "runtime_client" if override == "runtime_client" else "")

    def test_missing_or_malformed_bundle_disables_only_browser_signin(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public-config.json"
            with patch("mission_control.device_signin.PUBLIC_CONFIG", path), patch.dict(os.environ, {}, clear=True):
                self.assertFalse(DeviceSignIns(Identities()).available)
                for body in (
                    b"{",
                    b"null",
                    b"[]",
                    b"{}",
                    b"x" * 1025,
                    b"\xff",
                    json.dumps({"github_device_client_id": 42}).encode(),
                    json.dumps({"github_device_client_id": CLIENT, "token": "not-allowed"}).encode(),
                    json.dumps({"github_device_client_id": "invalid!"}).encode(),
                ):
                    with self.subTest(body=body[:32]):
                        path.write_bytes(body)
                        self.assertFalse(DeviceSignIns(Identities()).available)

    def test_build_serializes_only_public_id_and_clears_stale_value(self) -> None:
        write = runpy.run_path(str(ROOT / "tools/build_desktop.py"))["write_public_config"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "generated/public-config.json"
            with patch.dict(write.__globals__, {"PUBLIC_CONFIG": path}):
                with patch.dict(os.environ, {"WMM_GITHUB_DEVICE_CLIENT_ID": CLIENT, "GITHUB_TOKEN": "never-bundle"}):
                    write()
                self.assertEqual(json.loads(path.read_text()), {"github_device_client_id": CLIENT})
                self.assertNotIn("never-bundle", path.read_text())
                with patch.dict(os.environ, {}, clear=True):
                    write()
                self.assertEqual(json.loads(path.read_text()), {"github_device_client_id": ""})
                with (
                    patch.dict(os.environ, {"WMM_GITHUB_DEVICE_CLIENT_ID": "invalid!"}),
                    self.assertRaisesRegex(ValueError, "valid public"),
                ):
                    write()
                with (
                    patch.dict(os.environ, {"WMM_GITHUB_DEVICE_CLIENT_ID": "ghp_" + "x" * 36}),
                    self.assertRaisesRegex(ValueError, "valid public"),
                ):
                    write()
                self.assertEqual(json.loads(path.read_text()), {"github_device_client_id": ""})

    def test_release_requires_nonempty_public_id(self) -> None:
        validate = runpy.run_path(str(ROOT / "tools/build_desktop.py"))["public_device_client"]
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(ValueError, "valid public"):
            validate(required=True)
        with patch.dict(os.environ, {"WMM_GITHUB_DEVICE_CLIENT_ID": CLIENT}):
            self.assertEqual(validate(required=True), CLIENT)

    def test_build_plan_contains_config_without_writing_it(self) -> None:
        command = runpy.run_path(str(ROOT / "tools/build_desktop.py"))["command"]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "public-config.json"
            with patch.dict(command.__globals__, {"PUBLIC_CONFIG": path}):
                self.assertIn(str(path) + ":mission_control", command())
                self.assertFalse(path.exists())

    def test_package_probe_removes_environment_and_stops_on_mismatch(self) -> None:
        probe = runpy.run_path(str(ROOT / "tools/smoke_desktop_bundle.py"))["public_signin_smoke"]
        harness = {"preflight": Mock(), "_start": Mock(), "_stop": Mock(), "ORIGIN": "http://127.0.0.1:1"}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / ".factory/desktop-config/public-config.json"
            config.parent.mkdir(parents=True)
            config.write_text(json.dumps({"github_device_client_id": CLIENT}), encoding="utf-8")
            with (
                patch.dict(probe.__globals__, {"ROOT": root}),
                patch("runpy.run_path", return_value=harness),
                patch("urllib.request.urlopen") as read,
                patch.dict(os.environ, {"WMM_GITHUB_DEVICE_CLIENT_ID": CLIENT, "WMM_AGENT_GRANT": "secret"}),
                redirect_stdout(StringIO()),
            ):
                response = read.return_value.__enter__.return_value
                response.read.return_value = json.dumps(
                    {"device_signin_available": True, "identity": {"status": "SIGNED_OUT"}}
                )
                self.assertEqual(probe(root / "WMM", folder)["status"], "PASS")
                env = harness["_start"].call_args.args[2]
                self.assertNotIn("WMM_GITHUB_DEVICE_CLIENT_ID", env)
                self.assertNotIn("WMM_AGENT_GRANT", env)
                self.assertNotEqual(env["LOCALAPPDATA"], os.environ.get("LOCALAPPDATA"))
                harness["_stop"].assert_called_once_with(harness["_start"].return_value)
                harness["_stop"].reset_mock()
                response.read.return_value = json.dumps(
                    {"device_signin_available": False, "identity": {"status": "SIGNED_OUT"}}
                )
                with self.assertRaisesRegex(AssertionError, "Frozen sign-in readiness"):
                    probe(root / "WMM", folder)
                harness["_stop"].assert_called_once_with(harness["_start"].return_value)


if __name__ == "__main__":
    unittest.main()
