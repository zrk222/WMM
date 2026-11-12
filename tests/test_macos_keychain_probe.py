"""Synthetic command-boundary coverage; actual native acceptance runs on Mac CI."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'mac_probe', Path(__file__).resolve().parents[1] / 'tools/check_macos_bundle.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class KeychainProbeTests(unittest.TestCase):
    def exercise(self, fail=None, body_failure=False):
        calls = []
        environment = {'HOME': '/synthetic', 'PATH': '/usr/bin'}

        def run(argv, **kwargs):
            calls.append(argv[1:])
            self.assertEqual(kwargs['env'], environment)
            self.assertEqual(kwargs['timeout'], 15)
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            output = ''
            if len(calls) == 1:
                output = '    "/Users/runner/Library/Keychains/login.keychain-db"\n'
            if len(calls) == 2:
                output = '"/Users/runner/Library/Keychains/login.keychain-db"\n"/tmp/other keychain"\n'
            return subprocess.CompletedProcess(argv, int(argv[1] == fail), output, 'private')

        with patch.object(probe, 'require_disposable_runner'), patch.object(
                probe.subprocess, 'run', side_effect=run), patch.object(
                probe.secrets, 'token_urlsafe', return_value='secret-password'):
            try:
                with probe.temporary_native_keychain(Path('/synthetic'), environment):
                    self.assertIsNone(fail)
                    if body_failure:
                        raise ValueError('probe failure')
            except (RuntimeError, ValueError) as error:
                self.assertNotIn('secret-password', str(error))
                if not fail and not body_failure:
                    raise
            else:
                self.assertFalse(fail or body_failure)
        return calls

    def assert_cleanup(self, calls):
        self.assertEqual(calls[-3], ['default-keychain', '-d', 'user', '-s',
                                    '/Users/runner/Library/Keychains/login.keychain-db'])
        self.assertEqual(calls[-2], ['list-keychains', '-d', 'user', '-s',
                                    '/Users/runner/Library/Keychains/login.keychain-db',
                                    '/tmp/other keychain'])
        self.assertEqual(calls[-1][0], 'delete-keychain')

    def test_success_restores_and_deletes(self):
        calls = self.exercise()
        self.assertEqual([c[0] for c in calls[:6]], ['default-keychain', 'list-keychains',
                         'create-keychain', 'unlock-keychain', 'list-keychains', 'default-keychain'])
        self.assertEqual(calls[2][1:3], ['-p', 'secret-password'])
        self.assert_cleanup(calls)

    def test_probe_failure_restores_and_deletes(self):
        self.assert_cleanup(self.exercise(body_failure=True))

    def test_setup_failures_are_closed_and_cleaned(self):
        for command in ('create-keychain', 'unlock-keychain'):
            with self.subTest(command=command):
                calls = self.exercise(fail=command)
                self.assert_cleanup(calls)
                self.assertFalse(any(c[0] == 'default-keychain' and len(c) > 3
                                     for c in calls[:-3]))

    def test_guard_precedes_any_native_command(self):
        with patch.object(probe.sys, 'platform', 'win32'), patch.object(
                probe.subprocess, 'run') as run:
            with self.assertRaises(SystemExit):
                with probe.temporary_native_keychain(Path('/synthetic'), {}):
                    self.fail('guard allowed execution')
            run.assert_not_called()

    def test_timeout_is_redacted_and_all_cleanup_is_attempted(self):
        calls = []

        def run(argv, **kwargs):
            calls.append(argv[1:])
            if argv[1] == 'unlock-keychain':
                raise subprocess.TimeoutExpired(argv, 15, output='secret-password')
            output = '"/tmp/original"' if len(calls) <= 2 else ''
            # Also fail restoration of the default: list and delete must still run.
            code = int(len(calls) > 4 and argv[1] == 'default-keychain')
            return subprocess.CompletedProcess(argv, code, output, '')

        with patch.object(probe, 'require_disposable_runner'), patch.object(
                probe.subprocess, 'run', side_effect=run):
            with self.assertRaisesRegex(RuntimeError, 'cleanup failed') as caught:
                with probe.temporary_native_keychain(Path('/synthetic'), {}):
                    self.fail('timeout allowed probe')
            self.assertNotIn('secret-password', str(caught.exception))
        self.assertEqual([c[0] for c in calls[-3:]],
                         ['default-keychain', 'list-keychains', 'delete-keychain'])


if __name__ == '__main__':
    unittest.main()
