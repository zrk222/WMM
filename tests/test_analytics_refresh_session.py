"""Scoped connection reuse preserves durable phases, authority and unlocked provider I/O."""
from contextlib import contextmanager
import sqlite3
import time
import unittest
from unittest.mock import patch
from mission_control import db
from mission_control.insights import Insights
from tests import test_measurement_connectors as measurement


class RefreshSessionTests(unittest.TestCase):
    setUp = measurement.MeasurementTests.setUp
    create = measurement.MeasurementTests.create

    @contextmanager
    def tracked(self, handles):
        with db.session(self.store.path) as handle:
            handles.append(handle); yield handle

    def test_refresh_commits_reserve_before_unlocked_provider_and_closes_same_handle(self):
        sid = self.create()['source_id']; handles = []; events = []
        def opened(path):return self.tracked(handles)
        def provider(data, key):
            self.assertEqual(len(handles), 1); handle = handles[0]
            self.assertFalse(handle.in_transaction)
            self.assertEqual(handle.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(handle.execute('PRAGMA busy_timeout').fetchone()[0], 15000)
            self.assertEqual(handle.execute('PRAGMA synchronous').fetchone()[0], 2)
            with db.connection(self.store.path) as other:
                other.execute('BEGIN IMMEDIATE')
                row = other.execute('SELECT lease FROM insight_sources WHERE id=?', (sid,)).fetchone()
                self.assertGreater(row['lease'], time.time())
                other.execute("UPDATE insight_sources SET last_error='concurrent-writer' WHERE id=?", (sid,))
            events.append('provider-outside-transaction'); return dict(rows=[], scope='synthetic')
        with patch('mission_control.insights.session', side_effect=opened), patch('mission_control.insights.read', side_effect=provider):
            result = self.insights.refresh('sample-one', sid, dict(confirm_read=True))
        self.assertEqual(result['status'], 'CONNECTED'); self.assertEqual(events, ['provider-outside-transaction'])
        with self.assertRaises(sqlite3.ProgrammingError):handles[0].execute('SELECT 1')
        with db.connection(self.store.path) as other:
            self.assertEqual(other.execute('SELECT lease FROM insight_sources WHERE id=?', (sid,)).fetchone()[0], 0)

    def test_provider_crash_preserves_committed_attempt_and_closes_connection(self):
        sid = self.create()['source_id']; handles = []
        with patch('mission_control.insights.session', side_effect=lambda path:self.tracked(handles)), \
             patch('mission_control.insights.read', side_effect=RuntimeError('synthetic crash')):
            with self.assertRaises(RuntimeError):self.insights.refresh('sample-one', sid, dict(confirm_read=True))
        with self.assertRaises(sqlite3.ProgrammingError):handles[0].execute('SELECT 1')
        with db.connection(self.store.path) as other:
            self.assertGreater(other.execute('SELECT lease FROM insight_sources WHERE id=?', (sid,)).fetchone()[0], time.time())
            self.assertEqual(other.execute('SELECT COUNT(*) FROM insight_reports WHERE source_id=?', (sid,)).fetchone()[0], 1)

    def test_transaction_entry_and_commit_guards_roll_back_revoked_write(self):
        calls = []
        def authority(path, handle):
            calls.append('operation')
            if len(calls) == 2:raise PermissionError('synthetic authority revoked before commit')
        with patch('mission_control.operation_authority.guard_connection', side_effect=authority), \
             patch('mission_control.automation_execution.guard_connection') as automation:
            with self.assertRaises(PermissionError):
                with db.connection(self.store.path) as handle:
                    handle.execute("UPDATE apps SET version=version+1 WHERE id='sample-one'")
            self.assertEqual([call.kwargs for call in automation.call_args_list], [{}, {'committing':True}])
        self.assertEqual(calls, ['operation', 'operation'])
        self.assertEqual(self.store.app('sample-one')['version'], 1)

    def test_reused_completion_rechecks_authority_and_keeps_original_report(self):
        sid = self.create()['source_id']; operation_calls = []
        def guard(path, handle):
            operation_calls.append(handle)
            if len(operation_calls) == 4:raise PermissionError('synthetic completion revocation')
        with patch('mission_control.operation_authority.guard_connection', side_effect=guard), \
             patch('mission_control.insights.read', return_value=dict(rows=[], scope='synthetic')):
            with self.assertRaises(PermissionError):self.insights.refresh('sample-one', sid, dict(confirm_read=True))
        self.assertEqual(len(operation_calls), 4)
        self.assertTrue(all(handle is operation_calls[0] for handle in operation_calls))
        with db.connection(self.store.path) as other:
            self.assertGreater(other.execute('SELECT lease FROM insight_sources WHERE id=?', (sid,)).fetchone()[0], time.time())
            self.assertEqual(other.execute('SELECT COUNT(*) FROM insight_reports WHERE source_id=?', (sid,)).fetchone()[0], 1)

    def test_not_due_closes_session_without_provider_or_completion(self):
        sid = self.create()['source_id']; handles = []
        with patch('mission_control.insights.session', side_effect=lambda path:self.tracked(handles)), \
             patch('mission_control.insights.read') as provider:
            result = self.insights.refresh('sample-one', sid, dict(confirm_read=True), automatic=True)
        self.assertEqual(result, dict(status='NOT_DUE')); provider.assert_not_called()
        with self.assertRaises(sqlite3.ProgrammingError):handles[0].execute('SELECT 1')
