"""Offline Apple metrics parsing and correction-aware persistence tests."""
import gzip
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from mission_control.apple_metrics import (parse_partitions,
    reconcile_offline_instance)
from mission_control.apple_metrics_store import read_partition
from mission_control.common import Invalid, canonical
from mission_control.db import connection, initialize


def identity(**changes):
    return dict(dict(app_id='synthetic-app', store_app_id='123',
        connection_id='synthetic-connection', connection_version=1,
        report_id='synthetic-report', report_family='App Downloads Standard',
        granularity='DAILY'), **changes)


def segment(rows, identity='synthetic-segment', extra=None):
    body = ('Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n'
            + ''.join('%s\t123\t%s\t%s\tUS\n' % row for row in rows)).encode()
    compressed = gzip.compress(body)
    value = dict(id=identity, size=len(compressed),
                 checksum=hashlib.md5(compressed, usedforsecurity=False).hexdigest(),
                 data=compressed)
    if extra:
        value.update(extra)
    return value


def one_day(day='2026-01-01', count='7', label='First-time download'):
    return segment([(day, label, count)])


def persist(path, rows, processing='2026-01-02', report_identity=None):
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        return reconcile_offline_instance(db, identity() if report_identity is None
            else report_identity, processing, [segment(rows)], True)


class AppleMetricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'metrics.sqlite3'
        initialize(self.path)
        with connection(self.path) as db:
            db.execute("INSERT INTO apps(id,data,updated) VALUES('synthetic-app','{}','test')")

    def read(self, day='2026-01-01'):
        return read_partition(self.path, dict(identity(), event_date=day))

    def test_splits_multi_day_instance_and_preserves_event_meanings_and_zero(self):
        value = parse_partitions(identity(), '2026-01-04', [segment([
            ('2026-01-01', 'First-time download', '3'),
            ('2026-01-01', 'Redownload', '2'),
            ('2026-01-02', 'Manual update', '4'),
            ('2026-01-02', 'Auto-update', '5'),
            ('2026-01-03', 'Restore', '0'),
            ('2026-01-03', 'Future event label', '1')])], True)
        self.assertEqual([item['partition']['event_date'] for item in value],
                         ['2026-01-01', '2026-01-02', '2026-01-03'])
        observed = [[row['type'] for row in item['instance']['rows']] for item in value]
        self.assertEqual(observed, [['first_download', 'redownload'],
                                    ['update', 'update'], ['restore', 'unknown']])
        self.assertEqual(value[2]['instance']['rows'][0]['count'], 0)
        self.assertIsNone(self.read('2026-01-04'))

    def test_reconciliation_is_idempotent_and_new_processing_date_replaces(self):
        first = persist(self.path, [('2026-01-01', 'First-time download', '7')])
        self.assertEqual([row['status'] for row in first], ['INSERTED'])
        original = self.read()
        same = persist(self.path, [('2026-01-01', 'First-time download', '7')])
        self.assertEqual([row['status'] for row in same], ['UNCHANGED'])
        corrected = persist(self.path, [('2026-01-01', 'First-time download', '2')],
                            processing='2026-01-03')
        self.assertEqual([row['status'] for row in corrected], ['REPLACED'])
        self.assertEqual(self.read()['instance']['rows'][0]['count'], 2)
        self.assertNotEqual(self.read(), original)
        stale = persist(self.path, [('2026-01-01', 'First-time download', '9')])
        self.assertEqual([row['status'] for row in stale], ['STALE'])
        self.assertEqual(self.read()['instance']['rows'][0]['count'], 2)

    def test_multiday_sql_failure_rolls_back_entire_savepoint(self):
        with connection(self.path) as db:
            db.execute("CREATE TRIGGER fail_second_day BEFORE INSERT ON apple_metric_partitions "
                       "WHEN NEW.event_date='2026-01-02' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic failure'):
                reconcile_offline_instance(db, identity(), '2026-01-03', [segment([
                    ('2026-01-01', 'First-time download', '1'),
                    ('2026-01-02', 'First-time download', '2')])], True)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM apple_metric_partitions').fetchone()[0], 0)

    def test_rejects_malformed_foreign_partial_and_unsupported_observations(self):
        valid = one_day()
        malformed = dict(valid, data=b'not gzip')
        wrong_checksum = dict(valid, checksum='0' * 32)
        with self.assertRaisesRegex(Invalid, 'identity'):
            parse_partitions(identity(extra='rejected'), '2026-01-02', [valid], True)
        for processing in (None, 'not-a-date'):
            with self.subTest(processing=processing), self.assertRaises(Invalid):
                parse_partitions(identity(), processing, [valid], True)
        for report, complete in (([malformed], True), ([wrong_checksum], True),
                                 ([dict(valid, data=gzip.compress(
                                     b'Date\tApp Apple Identifier\tDownload Type\tCounts\n'
                                     b'2026-01-01\t999\tRedownload\t1\n'))], True),
                                 ([valid], False)):
            with self.subTest(report=report, complete=complete), self.assertRaises(Invalid):
                parse_partitions(identity(), '2026-01-02', report, complete)

    def test_rejects_duplicate_segment_identity_and_private_dimension_values(self):
        value = one_day()
        with self.assertRaisesRegex(Invalid, 'Repeated Apple report segment identity'):
            parse_partitions(identity(), '2026-01-02', [value, value], True)
        private = segment([('2026-01-01', 'First-time download', '1')],
                          extra={'signed_url': 'https://signed.invalid/private'})
        result = parse_partitions(identity(), '2026-01-02', [private], True)
        self.assertNotIn('signed_url', canonical(result))
        unsafe = segment([('2026-01-01', 'First-time download', '1')])
        raw = gzip.decompress(unsafe['data']).replace(b'\tUS\n', b'\thttps://signed.invalid\n')
        unsafe['data'] = gzip.compress(raw)
        unsafe['size'] = len(unsafe['data'])
        unsafe['checksum'] = hashlib.md5(unsafe['data'], usedforsecurity=False).hexdigest()
        with self.assertRaises(Invalid):
            parse_partitions(identity(), '2026-01-02', [unsafe], True)

    def test_requires_existing_transaction_and_existing_local_app(self):
        with connection(self.path) as db:
            with self.assertRaisesRegex(Invalid, 'transaction'):
                reconcile_offline_instance(db, identity(), '2026-01-02', [one_day()], True)
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(sqlite3.IntegrityError):
                reconcile_offline_instance(db, identity(app_id='foreign-local-app'),
                    '2026-01-02', [one_day()], True)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM apple_metric_partitions').fetchone()[0], 0)

    def test_initialized_schema_is_idempotent(self):
        initialize(self.path)
        initialize(self.path)
        self.assertIsNone(self.read())


if __name__ == '__main__':
    unittest.main()
