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

    def test_occupied_port_refuses_without_spawning_or_stopping_listener(self):
        with socket.socket() as listener:
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
            workspace = dict(app_ids=['sample-one'], empty_effect_tables={'jobs': 0})
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
                 patch.object(harness, '_workspace_state', side_effect=[{'app_ids':['one']}, {'app_ids':['changed']}]):
                with self.assertRaises(AssertionError):
                    harness.verify_frozen_first_packet(binary, folder, {}, 'unit')
            self.assertEqual([c.args[0] for c in stop.call_args_list], [first, second])

    def test_lazy_tables_are_absent_not_zero_and_reader_releases_database(self):
        import tempfile
        import sqlite3
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'mission-control.sqlite3'
            with harness.closing(sqlite3.connect(database)) as db:
                db.executescript("CREATE TABLE apps(id TEXT); INSERT INTO apps VALUES('sample-one'); CREATE TABLE jobs(id TEXT);")
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
                db.executescript("CREATE TABLE apps(id TEXT); INSERT INTO apps VALUES('sample-one'); CREATE TABLE jobs(id TEXT); INSERT INTO jobs VALUES('unexpected');")
                db.commit()
            with self.assertRaises(AssertionError):
                harness._workspace_state(folder)
            database.unlink()


if __name__ == '__main__':
    unittest.main()
