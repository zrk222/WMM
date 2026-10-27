"""Synthetic contract proofs; these do not attest Apple delivery or authority."""
from copy import deepcopy
import gzip
import hashlib
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.apple_analytics_parser import parse_instance
from mission_control.apple_metrics_contract import (
    complete_instance, observation_fingerprint, partition,
)


def key():
    return dict(app_id='app-local', store_app_id='123', connection_id='conn-1',
                connection_version=1, report_id='report-1',
                report_family='App Downloads Standard', granularity='DAILY',
                event_date='2026-01-01')


def instance():
    raw = gzip.compress(b'Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n'
                        b'2026-01-01\t123\tFirst-time download\t0\tUS\n'
                        b'2026-01-01\t123\tFuture download\t7\tCA\n')
    return parse_instance('123', '2026-01-02', [dict(id='segment-1', data=raw,
        size=len(raw), checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest())], True)


class AppleMetricsContractTests(unittest.TestCase):
    def test_parser_envelope_zero_unknown_and_defensive_copy(self):
        original = instance()
        validated = complete_instance(key(), original)
        self.assertEqual(validated['rows'][0]['count'], 0)
        self.assertEqual(validated['rows'][1]['type'], 'unknown')
        self.assertEqual(validated['rows'][1]['count'], 7)
        validated['rows'][0]['dimensions']['territory'] = 'GB'
        self.assertEqual(original['rows'][0]['dimensions']['territory'], 'US')
        self.assertEqual({r['date'] for r in original['rows']}, {'2026-01-01'})

    def test_partition_identity_is_closed_typed_and_source_scoped(self):
        expected = key()
        self.assertEqual(partition(expected), expected)
        for field, bad in [('app_id', ''), ('store_app_id', 'app-local'),
            ('connection_id', 'https://host'), ('report_id', []),
            ('connection_version', True), ('connection_version', 0),
            ('connection_version', 2147483648), ('event_date', '20260101'),
            ('event_date', '2026-02-30'), ('granularity', 'WEEKLY'),
            ('report_family', 'App Sessions Standard')]:
            with self.subTest(field=field, bad=bad), self.assertRaises(Invalid):
                partition(dict(expected, **{field: bad}))
        with self.assertRaises(Invalid):
            partition(dict(expected, credential='secret'))
        for field in ('app_id', 'store_app_id', 'connection_id', 'connection_version', 'report_id', 'event_date'):
            other = deepcopy(expected)
            other[field] = 2 if field == 'connection_version' else ('456' if field == 'store_app_id' else ('2026-01-02' if field == 'event_date' else 'other'))
            self.assertNotEqual(partition(other), expected)

    def test_incomplete_foreign_empty_or_malformed_envelopes_rejected(self):
        for changes in [dict(complete=False), dict(complete=1), dict(app_id='999'),
                        dict(rows=[]), dict(rows=None), dict(sources=[]),
                        dict(processing_date='2025-12-31'), dict(processing_date=None),
                        dict(extra='unexpected')]:
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                complete_instance(key(), dict(instance(), **changes))
        value = instance()
        del value['complete']
        with self.assertRaises(Invalid):
            complete_instance(key(), value)

    def test_bad_rows_do_not_partially_validate(self):
        cases = [('date', '2026-01-02'), ('processing_date', '2026-01-03'),
                 ('count', -1), ('count', True), ('count', 1.5),
                 ('count', 1000000000000000), ('type', 'redownload'),
                 ('source_type', ''), ('source_type', 'https://signed.example'),
                 ('source_sha256', 'f' * 64), ('segment_id', 'other'),
                 ('dimensions', {'token': 'private'}),
                 ('dimensions', {'territory': 'bearer: abc'}),
                 ('dimensions', {'territory': 'x' * 201}),
                 ('dimensions', {'territory': None}),
                 ('dimensions', {str(n): 'x' for n in range(33)})]
        for field, bad in cases:
            value = instance()
            value['rows'][1][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(Invalid):
                complete_instance(key(), value)
        value = instance()
        value['rows'][0]['extra'] = 'unexpected'
        with self.assertRaises(Invalid):
            complete_instance(key(), value)

    def test_provenance_is_required_bounded_and_unique(self):
        for field, bad in [('id', 'bad/id'), ('size', True), ('size', 0),
                           ('size', 16777217), ('checksum', 'x' * 32),
                           ('sha256', 'a' * 63), ('sha256', 'A' * 64)]:
            value = instance()
            value['sources'][0][field] = bad
            with self.subTest(field=field), self.assertRaises(Invalid):
                complete_instance(key(), value)
        value = instance()
        value['sources'] *= 2
        with self.assertRaises(Invalid):
            complete_instance(key(), value)
        with patch('mission_control.apple_metrics_contract.MAX_SEGMENTS', 0):
            with self.assertRaises(Invalid):
                complete_instance(key(), instance())

    def test_documented_standard_dimensions_allow_realistic_labels_only(self):
        value = instance()
        value['rows'][0]['dimensions'] = {
            'app name': "Rick's URL Tracker, Maps & Routes / Trips",
            'app version': '1.2.3 (4)', 'device': 'iPhone',
            'platform version': 'iOS 18.1', 'source type': 'App Store search',
            'page type': 'In-App event', 'pre-order': 'false',
            'territory': "Côte d’Ivoire",
        }
        self.assertEqual(complete_instance(key(), value), value)
        for name in ('source info', 'campaign', 'page title', 'arbitrary'):
            value['rows'][0]['dimensions'] = {name: 'ordinary label'}
            with self.subTest(name=name), self.assertRaises(Invalid):
                complete_instance(key(), value)
        for bad in ('https://example.com/?signature=abc', 'Bearer abc',
                    'password=abc', 'bad\nlabel'):
            value['rows'][0]['dimensions'] = {'app name': bad}
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                complete_instance(key(), value)
        with patch('mission_control.apple_metrics_contract.MAX_ROWS', 1):
            with self.assertRaises(Invalid):
                complete_instance(key(), instance())

    def test_fingerprint_is_order_independent_and_preserves_multiplicity(self):
        rows = complete_instance(key(), instance())['rows']
        fingerprint = observation_fingerprint(rows)
        self.assertEqual(fingerprint, observation_fingerprint(list(reversed(rows))))
        self.assertNotEqual(fingerprint, observation_fingerprint(rows + [rows[0]]))
        value = instance()
        value['rows'].append(deepcopy(value['rows'][0]))
        self.assertEqual(len(complete_instance(key(), value)['rows']), 3)
        for bad in ([], None, [dict(count=float('nan'))]):
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                observation_fingerprint(bad)


if __name__ == '__main__':
    unittest.main()
