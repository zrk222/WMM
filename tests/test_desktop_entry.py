"""Private packaged entry and actual loopback server, without GUI or provider access."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

from mission_control.desktop import DesktopRuntime, data_directory, dispatch


class DesktopEntryTests(unittest.TestCase):
    def test_private_data_paths_and_relative_xdg_rejection(self):
        home = Path(tempfile.gettempdir()) / 'synthetic-user'
        self.assertEqual(data_directory('win32', {}, home), home/'AppData'/'Local'/'Wize Marketing Machine')
        self.assertEqual(data_directory('darwin', {}, home), home/'Library'/'Application Support'/'Wize Marketing Machine')
        self.assertEqual(data_directory('linux', {'XDG_DATA_HOME':'relative'}, home), home/'.local'/'share'/'Wize Marketing Machine')
        self.assertNotEqual(data_directory('linux', {}, home), Path(__file__).parent)

    def test_occupied_port_opens_real_loopback_and_close_preserves_data(self):
        with tempfile.TemporaryDirectory() as folder, socket.socket() as occupied:
            occupied.bind(('127.0.0.1',0)); occupied.listen()
            runtime = DesktopRuntime(Path(folder), occupied.getsockname()[1])
            try:
                origin = runtime.start(workers=False)
                self.assertEqual(runtime.server.server_address[0], '127.0.0.1')
                self.assertNotEqual(runtime.server.server_port, occupied.getsockname()[1])
                self.assertEqual(runtime.start(workers=False), origin)
                with urlopen(origin+'/api/bootstrap',timeout=5) as response:
                    self.assertIn('apps',json.load(response))
                with urlopen(origin,timeout=5) as response:
                    self.assertIn(b'Set your goal',response.read())
            finally:
                runtime.close()
            self.assertFalse(runtime.thread.is_alive())
            self.assertTrue((Path(folder)/'mission-control.sqlite3').is_file())
            self.assertEqual(runtime.server.fileno(), -1)
            runtime.close()
            with self.assertRaises(RuntimeError):runtime.start()

    def test_fixed_adapter_dispatch_preserves_arguments_and_failure_status(self):
        before=sys.argv
        adapter=Mock(); adapter.main.return_value=0
        with patch('importlib.import_module',return_value=adapter) as imported:
            adapter.main.side_effect=lambda: self.assertEqual(sys.argv[1:],['catalog'])
            self.assertTrue(dispatch(['--agent-cli','catalog']))
            imported.assert_called_once_with('.agent_cli','mission_control')
        self.assertIs(sys.argv,before)
        adapter.main.side_effect=None;adapter.main.return_value=2
        with patch('importlib.import_module',return_value=adapter):
            with self.assertRaises(SystemExit) as error:dispatch(['--mcp','--origin','http://127.0.0.1:8765'])
        self.assertEqual(error.exception.code,2);self.assertIs(sys.argv,before)
        self.assertFalse(dispatch(['--arbitrary-module']))

    def test_controller_starts_and_stops_actual_existing_workers(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime=DesktopRuntime(Path(folder),0)
            with patch.object(runtime.server.runner,'start') as worker_start,patch.object(runtime.server.audit_runner,'start') as audit_start:
                runtime.start();worker_start.assert_called_once();audit_start.assert_called_once()
            runtime.close()

    def test_build_manifest_includes_explicit_public_assets_not_workspace_data(self):
        import runpy
        command=runpy.run_path(str(Path(__file__).resolve().parents[1]/'tools/build_desktop.py'))['command']
        argv=command()
        data=[argv[i+1] for i,value in enumerate(argv) if value=='--add-data']
        self.assertEqual(len(data),7)
        self.assertTrue(any('mission_control/static' in item.replace('\\','/') for item in data))
        self.assertFalse(any('mission_control/data' in item.replace('\\','/') for item in data))
        self.assertIn('--onedir',argv)
        self.assertNotIn('--onefile',argv)
        self.assertIn('mcp',argv)


if __name__=='__main__':unittest.main()
