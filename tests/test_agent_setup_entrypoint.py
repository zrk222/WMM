"""Offline discovery and usable module launch without personal host mutation."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from mission_control import agent_setup
from mission_control.common import Invalid


class SetupTests(unittest.TestCase):
    def test_missing_sdk_is_reported_without_token_or_network_access(self):
        with patch.dict(os.environ, {'WMM_AGENT_GRANT': 'PRIVATE_TOKEN_SENTINEL'}), \
             patch('socket.socket', side_effect=AssertionError('network forbidden')), \
             patch.object(agent_setup.util, 'find_spec', return_value=None):
            value = agent_setup.report('http://127.0.0.1:8765')
        self.assertEqual(value['mcp']['status'], 'OPTIONAL_DEPENDENCIES_MISSING')
        self.assertEqual(value['server_status'], 'NOT_CHECKED_OFFLINE')
        self.assertNotIn('PRIVATE_TOKEN_SENTINEL', json.dumps(value))
        config = value['mcp_config']['mcpServers']['wmm-local']
        self.assertIn('--use-grant', config['args'])
        self.assertNotIn('WMM_AGENT_GRANT', config['env'])
        self.assertTrue(Path(config['command']).is_absolute())
        self.assertTrue(Path(config['env']['PYTHONPATH']).is_absolute())

    def test_remote_alias_path_and_out_of_range_origins_are_rejected(self):
        for value in ('https://127.0.0.1:8765', 'http://localhost:8765',
                      'http://127.0.0.1:8765/', 'http://example.com:8765',
                      'http://127.0.0.1:65536', 'http://127.0.0.1:0'):
            with self.subTest(origin=value), self.assertRaises(Invalid):
                agent_setup.report(value)

    def test_mismatched_installed_sdk_is_separate_from_dependency_availability(self):
        with patch.object(agent_setup.util, 'find_spec', return_value=object()), \
             patch.object(agent_setup.metadata, 'version', return_value='0.0.1'):
            value = agent_setup.report('http://127.0.0.1:8765')
        self.assertEqual(value['mcp']['status'], 'DEPENDENCIES_AVAILABLE')
        self.assertFalse(value['mcp']['matches_tested_baseline'])

    def test_generated_config_resolves_modules_from_unrelated_directory(self):
        value = agent_setup.report('http://127.0.0.1:8765')
        config = value['mcp_config']['mcpServers']['wmm-local']
        env = dict(os.environ, **config['env'])
        env.pop('WMM_AGENT_GRANT', None)
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([config['command'], *config['args'], '--help'],
                                    cwd=folder, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--use-grant', result.stdout)
            result = subprocess.run([config['command'], '-m', 'mission_control.agent_cli', 'catalog'],
                                    cwd=folder, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsInstance(json.loads(result.stdout), dict)
            # -S excludes optional site packages: a real missing-SDK launch must
            # fail clearly rather than hang on stdio, install or contact WMM.
            result = subprocess.run([config['command'], '-S', *config['args']],
                                    cwd=folder, env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 2)
            self.assertIn('optional dependencies', result.stderr)
            self.assertEqual(result.stdout, '')

    def test_invalid_origin_exits_nonzero_without_configuration(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = agent_setup.main(['--origin', 'https://example.com', '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), '')
        self.assertIn('error', json.loads(err.getvalue()))


if __name__ == '__main__':
    unittest.main()
