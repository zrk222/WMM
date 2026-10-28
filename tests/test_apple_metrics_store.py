"""Trusted synthetic/offline core tests; no provider or scheduler authority."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from mission_control import apple_metrics_store as metrics
from mission_control.common import Invalid, canonical
from mission_control.db import connection, initialize


def key(**changes):
    return dict(dict(app_id='synthetic-app', store_app_id='123',
        connection_id='synthetic-connection', connection_version=1,
        report_id='synthetic-report', report_family='App Downloads Standard',
        granularity='DAILY', event_date='2026-01-01'), **changes)


def instance(processing='2026-01-02', count=7, app_id='123', event='2026-01-01'):
    return dict(app_id=app_id, processing_date=processing, complete=True,
        sources=[dict(id='synthetic-segment', size=100, checksum='a' * 32, sha256='b' * 64)],
        rows=[dict(date=event, type='first_download', source_type='First-time download',
            count=count, dimensions={'territory': 'US'}, segment_id='synthetic-segment',
            processing_date=processing, source_sha256='b' * 64)])


def offline_commit(path, partition, envelope):
    # Test-only admission. This helper is deliberately absent from runtime code.
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        return metrics._reconcile(db, partition, envelope)


class AppleMetricsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.sqlite3'
        initialize(self.path)
        with connection(self.path) as db:
            for app in ('synthetic-app', 'other-app'):
                db.execute('INSERT INTO apps(id,data,updated) VALUES(?,?,?)', (app, '{}', 'synthetic'))

    def read(self, partition=None):
        return metrics.read_partition(self.path, key() if partition is None else partition)

    def write(self, envelope=None, partition=None):
        return offline_commit(self.path, key() if partition is None else partition,
                              instance() if envelope is None else envelope)

    def test_disabled_ingestion_does_not_open_database_or_validate_input(self):
        with patch.object(metrics, 'connection', side_effect=AssertionError('database touched')):
            for arguments in [({}, {}), (self.path, key(), instance())]:
                with self.assertRaisesRegex(Invalid, '^APPLE_METRICS_INGESTION_DISABLED$'):
                    metrics.ingest(*arguments, trusted=True, lease=True, authorize=lambda: True)
        self.assertIsNone(self.read())

    def test_complete_partition_survives_reopen_with_provenance(self):
        self.assertEqual(self.write(), 'INSERTED')
        result = self.read()
        self.assertEqual(result['partition'], key())
        self.assertEqual(result['instance'], instance())
        self.assertEqual(result['event_data_finality'], 'UNKNOWN')
        initialize(self.path)
        self.assertEqual(self.read(), result)

    def test_newer_processing_date_replaces_without_summing(self):
        self.write()
        self.assertEqual(self.write(instance('2026-01-03', 2)), 'REPLACED')
        self.assertEqual(self.read()['instance'], instance('2026-01-03', 2))
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM apple_metric_partitions').fetchone()[0], 1)

    def test_older_processing_result_is_noop_including_timestamp(self):
        self.write(instance('2026-01-03', 2))
        before = self.read()
        self.assertEqual(self.write(), 'STALE')
        self.assertEqual(self.read(), before)

    def test_multiset_idempotence_ignores_order_preserves_multiplicity(self):
        value = instance()
        value['rows'] += [dict(value['rows'][0], count=0), deepcopy(value['rows'][0])]
        self.write(value)
        before = self.read()
        reordered = deepcopy(value)
        reordered['rows'].reverse()
        self.assertEqual(self.write(reordered), 'UNCHANGED')
        self.assertEqual(self.read(), before)
        value['rows'].pop()
        with self.assertRaisesRegex(Invalid, 'Conflicting'):
            self.write(value)
        self.assertEqual(self.read(), before)

    def test_conflicting_same_version_preserves_data_and_timestamp(self):
        self.write()
        before = self.read()
        with self.assertRaisesRegex(Invalid, 'Conflicting'):
            self.write(instance(count=8))
        self.assertEqual(self.read(), before)

    def test_changed_same_version_source_provenance_rejected(self):
        self.write()
        before = self.read()
        value = instance()
        value['sources'][0]['checksum'] = 'c' * 32
        with self.assertRaisesRegex(Invalid, 'Conflicting'):
            self.write(value)
        self.assertEqual(self.read(), before)

    def test_all_identity_components_isolate_partitions(self):
        self.write()
        variants = [key(app_id='other-app'), key(store_app_id='456'),
                    key(connection_id='other-connection'), key(connection_version=2),
                    key(report_id='other-report'), key(event_date='2026-01-02')]
        for partition in variants:
            with self.subTest(partition=partition):
                self.assertIsNone(self.read(partition))
                value = instance(count=3, app_id=partition['store_app_id'], event=partition['event_date'])
                self.write(value, partition)
                self.assertEqual(self.read(partition)['instance'], value)
                self.assertEqual(self.read()['instance'], instance())
        # Only DAILY downloads are supported; unsupported families cannot alias.
        for changes in (dict(granularity='WEEKLY'), dict(report_family='App Sessions Standard')):
            with self.assertRaises(Invalid):
                self.write(partition=key(**changes))

    def test_missing_dates_remain_absent_and_explicit_zero_is_stored(self):
        self.write(instance(count=0))
        self.assertEqual(self.read()['instance']['rows'][0]['count'], 0)
        self.assertIsNone(self.read(key(event_date='2026-01-02')))

    def test_partial_empty_foreign_and_invalid_refresh_preserve_prior(self):
        self.write()
        before = self.read()
        for changes in (dict(complete=False), dict(rows=[]), dict(app_id='456'),
                        dict(processing_date='broken'), dict(sources=[])):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                self.write(dict(instance(), **changes))
            self.assertEqual(self.read(), before)
        for bad in ('https://signed.example', 'token=synthetic'):
            value = instance('2026-01-03')
            value['rows'][0]['dimensions']['territory'] = bad
            with self.assertRaises(Invalid):
                self.write(value)
            self.assertEqual(self.read(), before)

    def test_requires_transaction_and_existing_app(self):
        with connection(self.path) as db:
            with self.assertRaisesRegex(Invalid, 'transaction'):
                metrics._reconcile(db, key(), instance())
        with self.assertRaises(sqlite3.IntegrityError):
            self.write(partition=key(app_id='missing-app'))
        self.assertIsNone(self.read())

    def test_transaction_exception_rolls_back_replacement_and_other_partition(self):
        self.write()
        before = self.read()
        with self.assertRaisesRegex(RuntimeError, 'synthetic interruption'):
            with connection(self.path) as db:
                db.execute('BEGIN IMMEDIATE')
                metrics._reconcile(db, key(), instance('2026-01-03', 1))
                metrics._reconcile(db, key(report_id='other'), instance())
                raise RuntimeError('synthetic interruption')
        self.assertEqual(self.read(), before)
        self.assertIsNone(self.read(key(report_id='other')))

    def test_sql_failure_rolls_back_and_preserves_timestamp(self):
        self.write()
        before = self.read()
        with connection(self.path) as db:
            db.execute("CREATE TRIGGER synthetic_fail BEFORE UPDATE ON apple_metric_partitions "
                       "BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.write(instance('2026-01-03', 1))
        self.assertEqual(self.read(), before)

    def test_partition_count_limit_is_per_app_and_replacements_do_not_grow_history(self):
        with patch.object(metrics, 'MAX_PARTITIONS_PER_APP', 1):
            self.write()
            before = self.read()
            with self.assertRaisesRegex(Invalid, 'storage limit'):
                self.write(partition=key(report_id='other'))
            self.assertEqual(self.read(), before)
            self.write(partition=key(app_id='other-app'))
            for day in range(3, 20):
                self.write(instance('2026-01-%02d' % day, day))
            with connection(self.path) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM apple_metric_partitions').fetchone()[0], 2)

    def test_partition_and_total_byte_limits_preserve_existing_data(self):
        self.write()
        before = self.read()
        for limit in ('MAX_PARTITION_BYTES', 'MAX_APP_BYTES'):
            with patch.object(metrics, limit, 1), self.assertRaisesRegex(Invalid, 'storage limit'):
                self.write(instance('2026-01-03', 1))
            self.assertEqual(self.read(), before)

    def test_concurrent_offline_transactions_serialize_exact_duplicate(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.write(), range(2)))
        self.assertCountEqual(results, ['INSERTED', 'UNCHANGED'])
        self.assertEqual(self.read()['instance'], instance())

    def test_read_rejects_corrupt_payload_metadata_hashes_and_timestamps(self):
        self.write()
        with connection(self.path) as db:
            original = dict(db.execute('SELECT * FROM apple_metric_partitions').fetchone())
        changed = instance()
        changed['rows'][0]['count'] = 8
        for field, value in [('data', '{}'), ('data', '{'),
            ('data', canonical(changed)), ('data', canonical(dict(instance(), app_id='456'))),
            ('fingerprint', '0' * 64), ('source_hash', '0' * 64),
            ('processing_date', '2026-01-03'), ('byte_count', 1),
            ('ingested_at', 'https://signed.invalid')]:
            with self.subTest(field=field, value=value):
                with connection(self.path) as db:
                    db.execute('UPDATE apple_metric_partitions SET ' + field + '=?', (value,))
                with self.assertRaisesRegex(Invalid, '^Stored Apple metrics partition failed integrity validation$'):
                    self.read()
                with connection(self.path) as db:
                    db.execute('UPDATE apple_metric_partitions SET ' + field + '=?', (original[field],))
        self.assertEqual(self.read()['instance'], instance())


if __name__ == '__main__':
    unittest.main()
