"""Negative contracts never spawn a frozen runtime or touch owner data."""
import copy
import importlib.util
from pathlib import Path
import socket
import unittest
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('packaged_packet_harness',
    Path(__file__).resolve().parents[1] / 'tools' / 'test_packaged_first_packet.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


class PackagedFirstPacketTests(unittest.TestCase):
    def test_failure_boundaries_drop_secrets_foreign_urls_and_unknown_routes(self):
        value = harness.read_boundary(harness.ORIGIN+'/api/research?token=never-record', harness.ORIGIN, 'GET', 503)
        self.assertEqual(value, dict(path='/api/research', method='GET', status=503))
        for url in ('https://example.invalid/api/research', harness.ORIGIN+'/api/oauth/private-token',
                    harness.ORIGIN+'/api/apps/private-customer'):
            self.assertIsNone(harness.read_boundary(url, harness.ORIGIN, 'GET', 500))
        self.assertIsNone(harness.read_boundary(harness.ORIGIN+'/api/research', harness.ORIGIN, 'DELETE'))

    def test_failure_snapshot_is_allowlisted_and_bounded(self):
        import tempfile, json
        from unittest.mock import Mock
        page = Mock()
        page.evaluate.return_value = dict(boot_loaded=True, research_loaded=False, document_ready='complete',
            selected_app='private-customer', csrf='never-record', token='never-record', workspace_error='raw-private-error')
        error = TimeoutError('private exception text')
        with tempfile.TemporaryDirectory() as folder:
            harness.capture_packet_failure(page, folder, 1440, error, [dict(path='/api/research', status=503)]*100, ['private error'])
            raw = (Path(folder)/'failure-1440.json').read_text()
            report = json.loads(raw)
        self.assertEqual(len(report['api_boundaries']), 32)
        self.assertEqual(report['readiness']['selected_app'], 'UNEXPECTED_APP')
        self.assertEqual(report['exception_type'], 'TimeoutError')
        self.assertEqual(report['page_error_count'], 1)
        for secret in ('never-record', 'private-customer', 'raw-private-error', 'private exception text', 'private error'):
            self.assertNotIn(secret, raw)
        self.assertIn('Packaged startup diagnostics:', error.__notes__[0])

    def test_diagnostic_errors_preserve_original_failure(self):
        import tempfile, json
        from unittest.mock import Mock
        page = Mock();page.evaluate.side_effect = RuntimeError('private browser detail')
        error = TimeoutError('original timeout')
        with tempfile.TemporaryDirectory() as folder:
            harness.capture_packet_failure(page, folder, 390, error, [], [])
            report = json.loads((Path(folder)/'failure-390.json').read_text())
        self.assertEqual(report['snapshot_error_type'], 'RuntimeError')
        self.assertNotIn('private browser detail', str(report))
        with patch.object(harness.Path, 'write_text', side_effect=OSError('private path')):
            harness.capture_packet_failure(page, '.', 390, error, [], [])
        self.assertIn('could not be retained', error.__notes__[-1])

    def test_packet_binding_rejects_foreign_stale_and_wrong_subset(self):
        expected = dict(app_id='sample-one', version=1, source_hash='source')
        value = dict(schema='wmm.goal-evidence-packet.v1', classification='LOCAL_DRAFT_NO_AUTHORITY',
                     app_id='sample-one', manifest_version=1, source_hash='source', goal='creative',
                     outputs=[dict(stage=6, output=None)])
        harness.validate_packet(value, expected, 'creative', [6])
        for key, wrong in [('app_id', 'foreign'), ('manifest_version', 2), ('source_hash', ''),
                           ('goal', 'campaign'), ('outputs', [dict(stage=7)])]:
            changed = copy.deepcopy(value)
            changed[key] = wrong
            with self.subTest(key=key), self.assertRaises(AssertionError):
                harness.validate_packet(changed, expected, 'creative', [6])

    def test_opt_in_is_required_before_any_process_launch(self):
        for env in ({}, {'CI': 'true'}, {'WMM_PACKAGED_FIRST_PACKET_TEST': '1'}):
            with patch.object(harness.subprocess, 'Popen') as spawn:
                with self.assertRaises(RuntimeError):
                    harness.verify_frozen_first_packet('absent', '.', env)
                spawn.assert_not_called()

    def test_browser_write_guard_allows_only_exact_synthetic_setup(self):
        from types import SimpleNamespace
        app_id, fields = harness.first_app_fixture(390)
        body = dict(id=app_id, data=dict(fields, growth_mode='AUTO'), version=None)
        exact = SimpleNamespace(method='POST', url=harness.ORIGIN+'/api/apps', post_data_json=body)
        self.assertTrue(harness.exact_app_creation(exact, harness.ORIGIN, app_id, fields))
        for changes in ({'id': 'sample-one'}, {'version': 1}, {'data': dict(fields, credential='')},
                        {'data': dict(fields, website='https://example.invalid')},
                        {'data': dict(fields, growth_mode='OFF')}, {'data': []}):
            request = SimpleNamespace(method=exact.method, url=exact.url, post_data_json=dict(body, **changes))
            with self.subTest(changes=changes):
                self.assertFalse(harness.exact_app_creation(request, harness.ORIGIN, app_id, fields))
        for url in (harness.ORIGIN+'/api/apps?mode=overwrite', harness.ORIGIN+'/api/jobs',
                    'https://example.invalid/api/apps'):
            request = SimpleNamespace(method='POST', url=url, post_data_json=body)
            self.assertFalse(harness.exact_app_creation(request, harness.ORIGIN, app_id, fields))

    def test_occupied_port_refuses_without_spawning_or_stopping_listener(self):
        with socket.socket() as listener:
            if harness.os.name != 'nt':
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(('127.0.0.1', 8765))
            except OSError:
                # An existing owner listener must also cause refusal, never cleanup.
                pass
            else:
                listener.listen()
            with patch.object(harness.subprocess, 'Popen') as spawn:
                with self.assertRaises(OSError):
                    harness.verify_frozen_first_packet('absent', '.',
                        dict(CI='true', WMM_PACKAGED_FIRST_PACKET_TEST='1'))
                spawn.assert_not_called()

    def test_unix_preflight_reuses_closed_connections_without_reusing_listeners(self):
        from unittest.mock import Mock
        probe = Mock()
        probe.__enter__ = Mock(return_value=probe)
        probe.__exit__ = Mock(return_value=False)
        with patch.object(harness.os, 'name', 'posix'), \
             patch.object(harness.socket, 'socket', return_value=probe):
            harness.preflight(dict(CI='true', WMM_PACKAGED_FIRST_PACKET_TEST='1'))
        probe.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind.assert_called_once_with(('127.0.0.1', 8765))

    def test_cleanup_joins_real_reader_before_closing_pipe(self):
        import subprocess
        import sys
        import threading
        child = subprocess.Popen([sys.executable, '-u', '-c',
            "import time; print('READY', flush=True); time.sleep(30)"],
            stdout=subprocess.PIPE, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if harness.os.name == 'nt' else 0)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'READY')
            reader = threading.Thread(target=child.stdout.read, daemon=True)
            child._wmm_stdout_reader = reader
            reader.start()
            harness._stop(child)
            self.assertFalse(reader.is_alive())
            self.assertTrue(child.stdout.closed)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)

    def test_startup_timeout_cleans_up_only_owned_child(self):
        from unittest.mock import Mock
        child = Mock()
        child.stdout.readline.return_value = ''
        child.poll.return_value = None
        with patch.object(harness.subprocess, 'Popen', return_value=child), \
             patch.object(harness.time, 'monotonic', side_effect=[0, 46]), \
             patch.object(harness, '_stop') as stop:
            with self.assertRaises(TimeoutError):
                harness._start('binary', '.', {})
            stop.assert_called_once_with(child)

    def test_cleanup_escalates_and_verifies_exit(self):
        from unittest.mock import Mock
        child = Mock()
        child.poll.side_effect = [None, -9]
        child.wait.side_effect = [harness.subprocess.TimeoutExpired('owned', 10), -9]
        harness._stop(child)
        child.terminate.assert_called_once()
        child.kill.assert_called_once()
        child.stdout.close.assert_called_once()

    def test_restart_reuses_private_workspace_and_browser_storage_without_effects(self):
        import tempfile
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'synthetic-binary'
            binary.write_bytes(b'synthetic executable identity')
            first, second = Mock(), Mock()
            first.poll.return_value = second.poll.return_value = None
            workspace = dict(apps=[dict(id='sample-one',version=1,data_sha256='a')], records=[], empty_effect_tables={'jobs': 0})
            with patch.object(harness, 'ROOT', Path(folder)), \
                 patch.object(harness, 'preflight') as preflight, \
                 patch.object(harness, '_start', side_effect=[first, second]) as start, \
                 patch.object(harness, '_stop') as stop, \
                 patch.object(harness, '_workspace_state', return_value=workspace), \
                 patch.object(harness, 'verify_packet_browser', return_value=[]) as browser:
                evidence = harness.verify_frozen_first_packet(binary, folder, {}, 'unit')
            self.assertEqual(preflight.call_count, 2)
            self.assertEqual(start.call_count, 2)
            self.assertEqual(start.call_args_list[0], start.call_args_list[1])
            self.assertEqual([c.args[0] for c in stop.call_args_list], [first, second])
            self.assertEqual(browser.call_args_list[0].args[2], browser.call_args_list[1].args[2])
            self.assertEqual(browser.call_args_list[1].args[3], 'measurement')
            self.assertEqual(evidence['network'], 'BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE')
            self.assertEqual(evidence['provider_data'], 'NOT_RUN')

    def test_restart_workspace_change_fails_and_stops_second_owned_child(self):
        import tempfile
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'binary'
            binary.write_bytes(b'fixture')
            first, second = Mock(), Mock()
            first.poll.return_value = second.poll.return_value = None
            with patch.object(harness, 'ROOT', Path(folder)), patch.object(harness, 'preflight'), \
                 patch.object(harness, '_start', side_effect=[first, second]), \
                 patch.object(harness, '_stop') as stop, \
                 patch.object(harness, 'verify_packet_browser', return_value=[]), \
                 patch.object(harness, '_workspace_state', side_effect=[{'apps':['one'],'records':[]}, {'apps':['changed'],'records':[]}]):
                with self.assertRaises(AssertionError):
                    harness.verify_frozen_first_packet(binary, folder, {}, 'unit')
            self.assertEqual([c.args[0] for c in stop.call_args_list], [first, second])

    def test_lazy_tables_are_absent_not_zero_and_reader_releases_database(self):
        import tempfile
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'mission-control.sqlite3'
            with harness.closing(sqlite3.connect(database)) as db:
                db.executescript("CREATE TABLE apps(id TEXT,version INTEGER,data TEXT); INSERT INTO apps VALUES('sample-one',1,'{}'); CREATE TABLE jobs(id TEXT);")
                db.commit()
            value = harness._workspace_state(folder)
            self.assertEqual(len(value['empty_effect_tables']), 4)
            self.assertEqual(value['empty_effect_tables']['jobs'], dict(status='PRESENT', count=0))
            self.assertEqual(value['empty_effect_tables']['campaign_intents'], dict(status='ABSENT', count=None))
            database.unlink()  # Windows refuses this while a sqlite reader remains open.
            self.assertFalse(database.exists())

    def test_nonzero_effects_fail_and_failed_read_still_releases_database(self):
        import tempfile
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'mission-control.sqlite3'
            with harness.closing(sqlite3.connect(database)) as db:
                db.executescript("CREATE TABLE apps(id TEXT,version INTEGER,data TEXT); INSERT INTO apps VALUES('sample-one',1,'{}'); CREATE TABLE jobs(id TEXT); INSERT INTO jobs VALUES('unexpected');")
                db.commit()
            with self.assertRaises(AssertionError):
                harness._workspace_state(folder)
            database.unlink()

    def test_same_app_id_does_not_hide_reset_manifest_or_source_records(self):
        before = dict(apps=[dict(id='sample-one', version=2, data_sha256='original')],
                      records=[dict(app_id='sample-one', id='source', version=3, hash='original')])
        for field, changed in [('version', 1), ('data_sha256', 'reset')]:
            after = copy.deepcopy(before)
            after['apps'][0][field] = changed
            with self.subTest(field=field), self.assertRaises(AssertionError):
                harness._same_bindings(after, before)
        after = copy.deepcopy(before)
        after['records'][0]['hash'] = 'changed'
        with self.assertRaises(AssertionError):
            harness._same_bindings(after, before)

    def test_profile_upgrade_checkpoint_rejects_replacement_and_unmarked_database(self):
        import tempfile
        import json
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / 'profile'
            profile.mkdir()
            actual, checkpoint, prior = harness._profile(profile, folder)
            self.assertIsNone(prior)
            (profile / 'mission-control.sqlite3').touch()
            with self.assertRaises(AssertionError):
                harness._profile(profile, folder)
            state = dict(apps=[dict(id='sample-one', version=2, data_sha256='original')], records=[])
            checkpoint.write_text(json.dumps(dict(schema='wmm.first-packet-profile.v1', workspace=state)))
            with patch.object(harness, '_workspace_state', return_value=state):
                self.assertIsNotNone(harness._profile(profile, folder)[2])
            changed = copy.deepcopy(state)
            changed['apps'][0]['data_sha256'] = 'reset'
            with patch.object(harness, '_workspace_state', return_value=changed), self.assertRaises(AssertionError):
                harness._profile(profile, folder)
            with self.assertRaises(AssertionError):
                harness._profile(Path(folder).parent, folder)

    def test_upgrade_reuses_profile_and_requires_prior_browser_goal(self):
        import tempfile
        import json
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'binary'
            binary.write_bytes(b'fixture')
            profile = Path(folder) / 'profile'
            profile.mkdir()
            state = dict(apps=[dict(id='sample-one',version=1,data_sha256='original')], records=[])
            children = [Mock(), Mock(), Mock(), Mock()]
            for child in children:
                child.poll.return_value = None
            with patch.object(harness, 'ROOT', Path(folder)), patch.object(harness, 'preflight'), \
                 patch.object(harness, '_start', side_effect=children), patch.object(harness, '_stop'), \
                 patch.object(harness, '_workspace_state', return_value=state), \
                 patch.object(harness, 'verify_packet_browser', return_value=[]) as browser:
                first = harness.verify_frozen_first_packet(binary, folder, {}, 'fresh', profile_dir=profile)
                upgraded = harness.verify_frozen_first_packet(binary, folder, {}, 'upgrade', profile_dir=profile)
            self.assertFalse(first['profile_reused'])
            self.assertTrue(upgraded['profile_reused'])
            self.assertIsNone(browser.call_args_list[0].args[3])
            self.assertEqual(browser.call_args_list[2].args[3], 'measurement')
            self.assertEqual(browser.call_args_list[0].args[2], browser.call_args_list[2].args[2])


if __name__ == '__main__':
    unittest.main()
