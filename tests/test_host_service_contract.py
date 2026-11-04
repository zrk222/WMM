"""Portable source checks; these do not prove a Linux service lifecycle."""
import configparser
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/test_host_service.py'
HARNESS = runpy.run_path(str(SCRIPT))
WRAPPER = runpy.run_path(str(ROOT / 'tools/ci_host_user.py'))


class HostServiceContractTests(unittest.TestCase):
    def test_port_probe_keeps_active_listener_exclusion_without_time_wait_false_alarm(self):
        from unittest.mock import Mock
        import socket
        probe = Mock()
        probe.__enter__ = Mock(return_value=probe)
        probe.__exit__ = Mock(return_value=False)
        with patch.object(socket, 'socket', return_value=probe):
            HARNESS['port_available']()
        probe.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind.assert_called_once_with(('127.0.0.1', 8765))
        probe.bind.side_effect = OSError('active listener')
        with patch.object(socket, 'socket', return_value=probe):
            with self.assertRaisesRegex(RuntimeError, 'port is occupied'):
                HARNESS['port_available']()

    def test_unit_is_explicit_same_user_and_bounded(self):
        unit = configparser.ConfigParser(interpolation=None, strict=True)
        unit.read(ROOT / 'packaging/linux/wmm-worker.service', encoding='utf-8')
        self.assertEqual(unit['Service']['ExecStart'], '/usr/lib/wize-marketing-machine/WMM --headless')
        self.assertEqual(unit['Service']['UMask'], '0077')
        self.assertEqual(unit['Service']['KillSignal'], 'SIGTERM')
        self.assertEqual(unit['Service']['Restart'], 'on-failure')
        self.assertGreater(int(unit['Unit']['StartLimitIntervalSec']), 0)
        self.assertGreater(int(unit['Unit']['StartLimitBurst']), 0)
        self.assertEqual(unit['Install']['WantedBy'], 'default.target')
        self.assertNotIn('User', unit['Service'])
        self.assertNotIn('Environment', unit['Service'])
        self.assertEqual(str(HARNESS['UNIT']).replace('\\', '/'),
                         '/usr/share/wize-marketing-machine/wmm-worker.service')
        self.assertEqual(HARNESS['UNIT'], WRAPPER['UNIT'])

    def test_harness_fails_closed_without_ci_opt_in_before_writes(self):
        preflight = HARNESS['preflight']
        with patch.object(sys, 'platform', 'linux'), \
             patch.object(subprocess, 'run', side_effect=AssertionError('unexpected command')), \
             patch('tempfile.TemporaryDirectory', side_effect=AssertionError('unexpected write')):
            for env in ({}, {'CI': 'true'}, {'CI': 'true', 'GITHUB_ACTIONS': 'true',
                                              'WMM_HOST_SERVICE_CI': '1'}):
                with self.assertRaisesRegex(RuntimeError, 'explicitly isolated'):
                    preflight(env)

    def test_direct_non_ci_invocation_refuses_without_modification(self):
        env = dict(os.environ, CI='false')
        result = subprocess.run([sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('explicitly isolated', result.stderr)

    def test_ci_flags_do_not_allow_root_or_start_systemd(self):
        preflight = HARNESS['preflight']
        pwd = types.SimpleNamespace(getpwuid=lambda uid: types.SimpleNamespace(pw_name='root'))
        flags = {'CI': 'true', 'GITHUB_ACTIONS': 'true', 'WMM_HOST_SERVICE_CI': '1',
                 'WMM_ISOLATED_USER_MANAGER': '1'}
        with patch.object(sys, 'platform', 'linux'), patch.dict(sys.modules, {'pwd': pwd}), \
             patch.object(os, 'geteuid', return_value=0, create=True), \
             patch('socket.socket', side_effect=AssertionError('unexpected socket')):
            with self.assertRaisesRegex(RuntimeError, 'Disposable user'):
                preflight(flags)

    def test_privileged_wrapper_refuses_before_any_command_or_temp_directory(self):
        preflight = WRAPPER['preflight']
        with patch.object(sys, 'platform', 'linux'), \
             patch.object(os, 'geteuid', return_value=0, create=True), \
             patch.object(subprocess, 'run', side_effect=AssertionError('unexpected command')), \
             patch('tempfile.mkdtemp', side_effect=AssertionError('unexpected directory')):
            for env in ({}, {'CI': 'true', 'GITHUB_ACTIONS': 'true', 'WMM_HOST_SERVICE_CI': '1'},
                        {'CI': 'true', 'GITHUB_ACTIONS': 'true', 'WMM_HOST_SERVICE_CI': '1',
                         'WMM_LINUX_PACKAGE_TEST': '1'}):
                with self.assertRaisesRegex(RuntimeError, 'explicitly enabled root'):
                    preflight(env)

    def test_stages_only_the_standalone_script_and_runs_without_checkout_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            staged = WRAPPER['stage_harness'](folder)
            self.assertEqual(staged.read_bytes(), SCRIPT.read_bytes())
            self.assertEqual([p.name for p in folder.iterdir()], ['test_host_service.py'])
            result = subprocess.run([sys.executable, '-I', str(staged)], cwd=folder,
                                    env=dict(os.environ, CI='false'),
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('explicitly isolated', result.stderr)

    def test_child_command_uses_staged_script_and_minimal_environment(self):
        parent = Path('/tmp/wmm-host-user-example')
        home = parent / 'home'
        runtime = Path('/run/user/12345')
        staged = parent / 'test_host_service.py'
        argv = WRAPPER['child_command']('wmm-ci-example', home, runtime, parent, staged)
        self.assertEqual(argv[:6], ['runuser', '-u', 'wmm-ci-example', '--', '/usr/bin/env', '-i'])
        self.assertIn(f'RUNNER_TEMP={parent}', argv)
        self.assertIn(f'HOME={home}', argv)
        self.assertEqual(argv[-2:], [str(WRAPPER['SYSTEM_PYTHON']), str(staged)])
        self.assertFalse(any('GITHUB_TOKEN=' in item or 'WMM_ISOLATED_NATIVE_KEYRING=' in item for item in argv))


if __name__ == '__main__':
    unittest.main()
