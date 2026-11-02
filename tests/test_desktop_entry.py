"""Private packaged entry and actual loopback server, without GUI or provider access."""

import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

from mission_control.desktop import DesktopRuntime, data_directory, dispatch, main
from mission_control.workspace_lock import WorkspaceBusy


class DesktopEntryTests(unittest.TestCase):
    def test_private_data_paths_and_relative_xdg_rejection(self):
        home = Path(tempfile.gettempdir()) / "synthetic-user"
        self.assertEqual(
            data_directory("win32", {}, home),
            home / "AppData" / "Local" / "Wize Marketing Machine",
        )
        self.assertEqual(
            data_directory("darwin", {}, home),
            home / "Library" / "Application Support" / "Wize Marketing Machine",
        )
        self.assertEqual(
            data_directory("linux", {"XDG_DATA_HOME": "relative"}, home),
            home / ".local" / "share" / "Wize Marketing Machine",
        )
        self.assertNotEqual(data_directory("linux", {}, home), Path(__file__).parent)

    def test_occupied_port_opens_real_loopback_and_close_preserves_data(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            runtime = DesktopRuntime(Path(folder), occupied.getsockname()[1])
            try:
                origin = runtime.start(workers=False)
                self.assertEqual(runtime.server.server_address[0], "127.0.0.1")
                self.assertNotEqual(
                    runtime.server.server_port, occupied.getsockname()[1]
                )
                self.assertEqual(runtime.start(workers=False), origin)
                with urlopen(origin + "/api/bootstrap", timeout=5) as response:
                    self.assertIn("apps", json.load(response))
                with urlopen(origin, timeout=5) as response:
                    self.assertIn(b"Set your goal", response.read())
            finally:
                runtime.close()
            self.assertFalse(runtime.thread.is_alive())
            self.assertTrue((Path(folder) / "mission-control.sqlite3").is_file())
            self.assertEqual(runtime.server.fileno(), -1)
            runtime.close()
            with self.assertRaises(RuntimeError):
                runtime.start()

    def test_fixed_adapter_dispatch_preserves_arguments_and_failure_status(self):
        before = sys.argv
        adapter = Mock()
        adapter.main.return_value = 0
        with patch("importlib.import_module", return_value=adapter) as imported:
            adapter.main.side_effect = lambda: self.assertEqual(
                sys.argv[1:], ["catalog"]
            )
            self.assertTrue(dispatch(["--agent-cli", "catalog"]))
            imported.assert_called_once_with(".agent_cli", "mission_control")
        self.assertIs(sys.argv, before)
        adapter.main.side_effect = None
        adapter.main.return_value = 2
        with patch("importlib.import_module", return_value=adapter):
            with self.assertRaises(SystemExit) as error:
                dispatch(["--mcp", "--origin", "http://127.0.0.1:8765"])
        self.assertEqual(error.exception.code, 2)
        self.assertIs(sys.argv, before)
        self.assertFalse(dispatch(["--arbitrary-module"]))

    def test_controller_starts_and_stops_actual_existing_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = DesktopRuntime(Path(folder), 0)
            with (
                patch.object(runtime.server.runner, "start") as worker_start,
                patch.object(runtime.server.audit_runner, "start") as audit_start,
            ):
                runtime.start()
                worker_start.assert_called_once()
                audit_start.assert_called_once()
            runtime.close()

    def test_fixed_port_fails_closed_and_releases_workspace(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen()
            with self.assertRaises(OSError):
                DesktopRuntime(Path(folder), occupied.getsockname()[1], fixed_port=True)
            runtime = DesktopRuntime(Path(folder), 0, fixed_port=True)
            runtime.close()

    def test_same_workspace_rejected_before_second_worker_starts(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = DesktopRuntime(Path(folder), 0)
            try:
                with self.assertRaises(WorkspaceBusy):
                    DesktopRuntime(Path(folder), 0)
            finally:
                runtime.close()
            resumed = DesktopRuntime(Path(folder), 0)
            resumed.close()

    def test_competing_runtime_subprocess_cannot_start_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = DesktopRuntime(Path(folder), 0)
            try:
                code = (
                    "import sys; from mission_control.desktop import DesktopRuntime; "
                    "r=DesktopRuntime(sys.argv[1],0); r.start(); print('WORKERS_STARTED')"
                )
                result = subprocess.run(
                    [sys.executable, "-c", code, folder],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("WORKERS_STARTED", result.stdout)
                self.assertIn("WorkspaceBusy", result.stderr)
            finally:
                runtime.close()

    def test_worker_start_failure_releases_workspace(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = DesktopRuntime(Path(folder), 0)
            with patch.object(
                runtime.server.runner, "start", side_effect=RuntimeError("synthetic")
            ):
                with self.assertRaises(RuntimeError):
                    runtime.start()
            resumed = DesktopRuntime(Path(folder), 0)
            resumed.close()

    def test_failed_worker_stop_retains_lock_until_process_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = DesktopRuntime(Path(folder), 0)
            runtime.start()
            with patch.object(
                runtime.server.runner, "stop", side_effect=RuntimeError("synthetic")
            ):
                with self.assertRaises(RuntimeError):
                    runtime.close()
            with self.assertRaises(WorkspaceBusy):
                DesktopRuntime(Path(folder), 0)
            runtime.server.runner.stop()
            runtime.lock.release()

    def test_headless_waits_for_stop_without_browser(self):
        from mission_control.desktop import headless

        runtime = Mock()
        runtime.start.return_value = "http://127.0.0.1:8765"
        with (
            patch(
                "mission_control.desktop.DesktopRuntime", return_value=runtime
            ) as factory,
            patch("mission_control.desktop.threading.Event") as event,
            patch("mission_control.desktop.signal.signal", return_value=None),
            patch("webbrowser.open") as browser,
        ):
            headless()
        factory.assert_called_once_with(fixed_port=True)
        event.return_value.wait.assert_called_once()
        runtime.close.assert_called_once()
        browser.assert_not_called()

    def test_headless_installs_and_restores_termination_handlers(self):
        from mission_control.desktop import headless

        handlers = {}

        def register(sig, callback):
            old = handlers.get(sig, "previous")
            handlers[sig] = callback
            return old

        runtime = Mock()
        runtime.start.return_value = "http://127.0.0.1:8765"
        stop = Mock()

        def interrupt():
            handlers[__import__("signal").SIGTERM](__import__("signal").SIGTERM, None)

        stop.wait.side_effect = interrupt
        with (
            patch("mission_control.desktop.DesktopRuntime", return_value=runtime),
            patch("mission_control.desktop.threading.Event", return_value=stop),
            patch("mission_control.desktop.signal.signal", side_effect=register),
        ):
            headless()
        stop.set.assert_called_once()
        runtime.close.assert_called_once()
        self.assertTrue(all(value == "previous" for value in handlers.values()))

    def test_locked_native_vault_remains_failure_without_fallback(self):
        from mission_control.linux_vault import LinuxVault
        from mission_control.common import Invalid

        vault = LinuxVault.__new__(LinuxVault)
        vault.library = Mock()
        vault.library.Collection.return_value.is_locked.return_value = True
        with self.assertRaisesRegex(Invalid, "Unlock"):
            vault.get("synthetic-scope")
        vault.library.Collection.return_value.create_item.assert_not_called()

    def test_headless_dispatch_avoids_browser_and_tk(self):
        with (
            patch("mission_control.desktop.headless") as run,
            patch("webbrowser.open") as browser,
        ):
            main(["--headless"])
            run.assert_called_once()
            browser.assert_not_called()

    def test_headless_runtime_uses_user_path_and_process_exit_releases_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = dict(__import__("os").environ)
            if sys.platform == "win32":
                environment["LOCALAPPDATA"] = folder
            else:
                environment["XDG_DATA_HOME"] = folder
            child = subprocess.Popen(
                [sys.executable, "-u", "-m", "mission_control.desktop", "--headless"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=environment,
            )
            try:
                line = child.stdout.readline()
                data = json.loads(line)
                self.assertEqual(data["origin"], "http://127.0.0.1:8765")
                self.assertEqual(data["mode"], "HEADLESS")
                if sys.platform == "win32":
                    child.terminate()
                else:
                    child.send_signal(__import__("signal").SIGTERM)
                child.wait(timeout=30)
                self.assertTrue(
                    (
                        Path(folder)
                        / "Wize Marketing Machine"
                        / "mission-control.sqlite3"
                    ).exists()
                )
                runtime = DesktopRuntime(
                    Path(folder) / "Wize Marketing Machine", 0, fixed_port=True
                )
                runtime.close()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
                child.stdout.close()
                child.stderr.close()

    def test_build_manifest_includes_explicit_public_assets_not_workspace_data(self):
        import runpy

        command = runpy.run_path(
            str(Path(__file__).resolve().parents[1] / "tools/build_desktop.py")
        )["command"]
        argv = command()
        data = [argv[i + 1] for i, value in enumerate(argv) if value == "--add-data"]
        self.assertEqual(len(data), 7)
        self.assertTrue(
            any("mission_control/static" in item.replace("\\", "/") for item in data)
        )
        self.assertFalse(
            any("mission_control/data" in item.replace("\\", "/") for item in data)
        )
        self.assertIn("--onedir", argv)
        self.assertNotIn("--onefile", argv)
        self.assertIn("mcp", argv)

    def test_disposable_vault_probe_verifies_cleanup_without_secret_output(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from mission_control.desktop import vault_self_test
        saved = {}
        vault = Mock()
        vault.get.side_effect = lambda key: saved.get(key)
        vault.put.side_effect = lambda key, value: saved.__setitem__(key, value)
        vault.delete.side_effect = lambda key: saved.pop(key, None)
        output = StringIO()
        with patch('mission_control.credential_vault.Vault', return_value=vault), redirect_stdout(output):
            vault_self_test()
        self.assertFalse(saved)
        self.assertEqual(vault.put.call_count, 1)
        self.assertEqual(vault.delete.call_count, 1)
        self.assertTrue(vault.put.call_args.args[0].startswith('WMM/disposable-package-test/'))
        self.assertNotIn('synthetic-private-', output.getvalue())
        self.assertTrue(json.loads(output.getvalue())['synthetic_item_removed'])

    def test_disposable_vault_probe_cleans_up_failed_readback(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from mission_control.desktop import vault_self_test
        vault = Mock()
        vault.get.side_effect = [None, {'wrong': 'value'}]
        output = StringIO()
        with patch('mission_control.credential_vault.Vault', return_value=vault), redirect_stdout(output):
            with self.assertRaises(RuntimeError):
                vault_self_test()
        vault.delete.assert_called_once()
        self.assertEqual(output.getvalue(), '')

    def test_linux_bundle_explicitly_collects_protected_storage(self):
        import runpy
        with patch('sys.platform', 'linux'):
            argv = runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/build_desktop.py'))['command']()
        self.assertIn('secretstorage', argv)
        self.assertIn('jeepney', argv)



if __name__ == "__main__":
    unittest.main()
