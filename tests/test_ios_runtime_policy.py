"""Isolated desktop process-policy checks, not native iOS acceptance."""
import subprocess
import sys
import textwrap
import unittest


class IOSRuntimePolicyTests(unittest.TestCase):
    def child(self, source):
        result = subprocess.run([sys.executable, '-c', textwrap.dedent(source)],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_desktop_import_is_inert_and_activation_rejected(self):
        self.child('''
            import subprocess, sys
            from mission_control.ios_runtime_policy import activate
            try: activate()
            except RuntimeError: pass
            else: raise AssertionError('Desktop activation accepted')
            subprocess.run([sys.executable, '-c', 'pass'], check=True)
        ''')

    def test_actual_process_launches_are_denied_without_exposing_arguments(self):
        self.child('''
            import os, subprocess, sys
            from mission_control.ios_runtime_policy import activate
            sys.platform = 'ios'
            activate()
            activate()
            for launch in (lambda: subprocess.run([sys.executable, '-c', 'raise SystemExit(99)']),
                           lambda: os.system('WMM_SECRET_ARGUMENT')):
                try: launch()
                except PermissionError as error:
                    assert 'WMM_SECRET_ARGUMENT' not in str(error)
                else: raise AssertionError('Process launch permitted')
        ''')

    def test_all_declared_routes_deny_and_local_engine_work_continues(self):
        self.child('''
            import json, sqlite3, sys
            from mission_control.ios_runtime_policy import activate, _PROCESS_EVENTS
            sys.platform = 'ios'
            activate()
            for event in _PROCESS_EVENTS:
                try: sys.audit(event, 'PRIVATE_ARG')
                except PermissionError as error: assert 'PRIVATE_ARG' not in str(error)
                else: raise AssertionError(event)
            from mission_control.ios_capabilities import inventory
            assert inventory()['operation_count'] >= 60
            with sqlite3.connect(':memory:') as db:
                assert db.execute('select 42').fetchone()[0] == 42
            assert json.loads('{"local":true}')['local']
        ''')

    def test_silently_rejected_hook_fails_startup(self):
        self.child('''
            import sys
            from mission_control.ios_runtime_policy import activate
            def reject(event, args):
                if event == 'sys.addaudithook': raise RuntimeError('registration refused')
            sys.addaudithook(reject)
            sys.platform = 'ios'
            try: activate()
            except RuntimeError: pass
            else: raise AssertionError('Unregistered policy accepted')
        ''')


if __name__ == '__main__':
    unittest.main()
