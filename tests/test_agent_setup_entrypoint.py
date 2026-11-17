"""Offline discovery and usable module launch without personal host mutation."""

import contextlib
import io
import json
import os
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mission_control import agent_setup
from mission_control.common import Invalid
from mission_control.desktop import dispatch
from tests import test_agent_grants as fixture


class SetupTests(unittest.TestCase):
    def test_missing_sdk_is_reported_without_token_or_network_access(self):
        with (
            patch.dict(os.environ, {"WMM_AGENT_GRANT": "PRIVATE_TOKEN_SENTINEL"}),
            patch("socket.socket", side_effect=AssertionError("network forbidden")),
            patch.object(agent_setup.util, "find_spec", return_value=None),
        ):
            value = agent_setup.report("http://127.0.0.1:8765")
        self.assertEqual(value["mcp"]["status"], "OPTIONAL_DEPENDENCIES_MISSING")
        self.assertEqual(value["server_status"], "NOT_CHECKED_OFFLINE")
        self.assertNotIn("PRIVATE_TOKEN_SENTINEL", json.dumps(value))
        config = value["mcp_config"]["mcpServers"]["wmm-local"]
        self.assertIn("--use-grant", config["args"])
        self.assertNotIn("WMM_AGENT_GRANT", config["env"])
        self.assertTrue(Path(config["command"]).is_absolute())
        self.assertTrue(Path(config["env"]["PYTHONPATH"]).is_absolute())
        self.assertEqual(value["owner_host_verification"]["server_status"], "NOT_CHECKED_OFFLINE")
        self.assertEqual(value["owner_host_verification"]["command"][-3:], ["--verify-app", "<app-id>", "--json"])

    def test_remote_alias_path_and_out_of_range_origins_are_rejected(self):
        for value in (
            "https://127.0.0.1:8765",
            "http://localhost:8765",
            "http://127.0.0.1:8765/",
            "http://example.com:8765",
            "http://127.0.0.1:65536",
            "http://127.0.0.1:0",
        ):
            with self.subTest(origin=value), self.assertRaises(Invalid):
                agent_setup.report(value)

    def test_mismatched_installed_sdk_is_separate_from_dependency_availability(self):
        with (
            patch.object(agent_setup.util, "find_spec", return_value=object()),
            patch.object(agent_setup.metadata, "version", return_value="0.0.1"),
        ):
            value = agent_setup.report("http://127.0.0.1:8765")
        self.assertEqual(value["mcp"]["status"], "DEPENDENCIES_AVAILABLE")
        self.assertFalse(value["mcp"]["matches_tested_baseline"])

    def test_generated_config_resolves_modules_from_unrelated_directory(self):
        value = agent_setup.report("http://127.0.0.1:8765")
        self.assertEqual(value["runtime_kind"], "SOURCE_PYTHON")
        config = value["mcp_config"]["mcpServers"]["wmm-local"]
        env = dict(os.environ, **config["env"])
        env.pop("WMM_AGENT_GRANT", None)
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [config["command"], *config["args"], "--help"],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--use-grant", result.stdout)
            result = subprocess.run(
                [config["command"], "-m", "mission_control.agent_cli", "catalog"],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
            # -S excludes optional site packages: a real missing-SDK launch must
            # fail clearly rather than hang on stdio, install or contact WMM.
            result = subprocess.run(
                [config["command"], "-S", *config["args"]],
                cwd=folder,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("optional dependencies", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_invalid_origin_exits_nonzero_without_configuration(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = agent_setup.main(["--origin", "https://example.com", "--json"])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("error", json.loads(err.getvalue()))

    def test_packaged_report_uses_only_frozen_executable_arguments(self):
        with patch.dict(os.environ, {"WMM_AGENT_GRANT": "PRIVATE_TOKEN_SENTINEL"}):
            value = agent_setup.report("http://127.0.0.1:8765", runtime_executable="C:/WMM/WMM.exe")
        self.assertEqual(value["runtime_kind"], "PACKAGED_DESKTOP")
        self.assertIsNone(value["python"])
        self.assertIsNone(value["repository"])
        self.assertEqual(value["cli"]["catalog"], [str(Path("C:/WMM/WMM.exe").resolve()), "--agent-cli", "catalog"])
        config = value["mcp_config"]["mcpServers"]["wmm-local"]
        self.assertEqual(config["command"], value["cli"]["catalog"][0])
        self.assertEqual(config["args"], ["--mcp", "--origin", "http://127.0.0.1:8765", "--use-grant"])
        self.assertEqual(config["env"], {})
        self.assertEqual(value["owner_host_verification"]["command"][:2], [config["command"], "--agent-setup"])
        serialized = json.dumps(value)
        for forbidden in ("PYTHONPATH", "mission_control.agent_mcp", "pip", "PRIVATE_TOKEN_SENTINEL"):
            self.assertNotIn(forbidden, serialized)

    def test_packaged_mode_reports_missing_bundled_dependencies_without_install_recipe(self):
        with patch.object(agent_setup.util, "find_spec", return_value=None):
            value = agent_setup.report("http://127.0.0.1:8765", runtime_executable="C:/WMM/WMM.exe")
        self.assertEqual(value["mcp"]["status"], "OPTIONAL_DEPENDENCIES_MISSING")
        self.assertNotIn("install", value["mcp"])

    def test_packaged_cli_entrypoint_uses_frozen_runtime_only_when_frozen(self):
        out = io.StringIO()
        with (
            patch.object(agent_setup.sys, "frozen", True, create=True),
            patch.object(agent_setup.sys, "executable", "C:/WMM/WMM.exe"),
            contextlib.redirect_stdout(out),
        ):
            code = agent_setup.main(["--origin", "http://127.0.0.1:8765", "--json"])
        self.assertEqual(code, 0)
        value = json.loads(out.getvalue())
        self.assertEqual(value["runtime_kind"], "PACKAGED_DESKTOP")
        self.assertEqual(value["cli"]["catalog"][1:], ["--agent-cli", "catalog"])

    def test_missing_grant_never_contacts_local_service(self) -> None:
        with (
            patch.dict(os.environ, {"WMM_AGENT_GRANT": ""}),
            patch.object(agent_setup, "OperatorClient") as client,
            contextlib.redirect_stderr(io.StringIO()) as error,
        ):
            self.assertEqual(agent_setup.main(["--origin", "http://127.0.0.1:8765", "--verify-app", "sample-one"]), 2)
            client.assert_not_called()
        self.assertIn("WMM_AGENT_GRANT", error.getvalue())

    def test_no_server_returns_actionable_redacted_error(self) -> None:
        # Reserve the address without listening so another process cannot answer the probe.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            origin = "http://127.0.0.1:" + str(listener.getsockname()[1])
            token = "wmmg_" + "A" * 43
            with patch.dict(os.environ, {"WMM_AGENT_GRANT": token}), contextlib.redirect_stderr(io.StringIO()) as error:
                self.assertEqual(agent_setup.main(["--origin", origin, "--verify-app", "sample-one"]), 3)
        value = json.loads(error.getvalue())
        self.assertEqual(value["status"], "OWNER_HOST_ACCESS_UNVERIFIED")
        self.assertEqual(value["error"]["code"], "TRANSPORT_UNAVAILABLE")
        self.assertNotIn(token, error.getvalue())


class OwnerHostVerificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = fixture.GrantTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_source_and_packaged_dispatch_use_grants_and_emit_only_receipt(self) -> None:
        issued = self.fixture.issue(["operations.read"], max_calls=2)
        assert issued is not None
        token = issued["token"]
        for packaged, expected_remaining in ((False, 1), (True, 0)):
            out = io.StringIO()
            args = ["--origin", self.fixture.origin, "--verify-app", "sample-one", "--json"]
            with (
                patch.dict(os.environ, {"WMM_AGENT_GRANT": token}),
                patch.object(agent_setup.sys, "frozen", packaged, create=True),
                patch.object(agent_setup.OperatorClient, "bootstrap", side_effect=AssertionError("no fallback")),
                contextlib.redirect_stdout(out),
            ):
                if packaged:
                    self.assertTrue(dispatch(["--agent-setup", *args]))
                else:
                    self.assertEqual(agent_setup.main(args), 0)
            value = json.loads(out.getvalue())
            self.assertEqual(value["status"], "VERIFIED_OWNER_HOST_ACCESS")
            self.assertEqual(value["runtime_kind"], "PACKAGED_DESKTOP" if packaged else "SOURCE_PYTHON")
            self.assertEqual(value["app_id"], "sample-one")
            self.assertEqual(value["manifest_version"], 1)
            self.assertEqual(value["remaining_calls"], expected_remaining)
            self.assertFalse(value["remote_mcp_verified"])
            for private in (token, issued["grant"]["id"], "Synthetic grant app", "local_catalog", "app_hash"):
                self.assertNotIn(private, out.getvalue())

    def test_wrong_app_and_revoked_grant_fail_closed(self) -> None:
        issued = self.fixture.issue(["operations.read"])
        assert issued is not None
        token = issued["token"]
        for app in ("sample-two", "sample-one"):
            if app == "sample-one":
                self.fixture.owner.request(
                    "POST", "/api/apps/sample-one/agent-grants/revoke", dict(id=issued["grant"]["id"], version=1)
                )
            with (
                patch.dict(os.environ, {"WMM_AGENT_GRANT": token}),
                patch.object(agent_setup.OperatorClient, "bootstrap", side_effect=AssertionError("no fallback")),
                contextlib.redirect_stderr(io.StringIO()) as error,
            ):
                self.assertEqual(agent_setup.main(["--origin", self.fixture.origin, "--verify-app", app]), 3)
            self.assertEqual(json.loads(error.getvalue())["error"]["code"], "GRANT_REJECTED")
            self.assertNotIn(token, error.getvalue())


if __name__ == "__main__":
    unittest.main()
