"""Synthetic Apple report parsing; no provider or device acceptance is implied."""
import gzip
import hashlib
import unittest
from unittest.mock import patch

from mission_control.common import Invalid


def segment(text, identity='s1', normalize_fixture=True):
    # Historical fixtures use simple comma separators; feed the documented TSV format.
    if normalize_fixture and '\t' not in text.partition('\n')[0]:
        text = text.replace(',', '\t')
    raw = gzip.compress(text.encode('utf-8'), mtime=0)
    return dict(id=identity, data=raw, size=len(raw), checksum=hashlib.md5(raw, usedforsecurity=False).hexdigest())


HEADER = 'Date,App Apple Identifier,Download Type,Counts\n'


class AppleAnalyticsParserTests(unittest.TestCase):
    def parse(self, content, processing='2026-01-03', complete=True):
        from mission_control.apple_analytics_parser import parse_instance
        return parse_instance('123', processing, [segment(content)], complete)

    def test_documented_tsv_and_download_categories(self):
        data = ('Counts\tDownload Type\tApp Apple Identifier\tDate\tTerritory\n'
                '2\tAuto-update\t123\t2026-01-01\tUS, CA\n'
                '1\tRestore\t123\t2026-01-01\tUS\n')
        rows = self.parse(data)['rows']
        self.assertEqual([(r['type'], r['source_type'], r['count']) for r in rows],
                         [('update', 'Auto-update', 2), ('restore', 'Restore', 1)])
        self.assertEqual(rows[0]['dimensions']['territory'], 'US, CA')

    def test_unsupported_comma_delimiter_is_rejected(self):
        from mission_control.apple_analytics_parser import parse_instance
        source = segment(HEADER + '2026-01-01,123,Redownload,1\n', normalize_fixture=False)
        with self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [source], True)

    def test_named_columns_categories_and_unknown_values(self):
        data = ('Counts,Download Type,App Apple Identifier,Date\n'
                '3,First-time Download,123,2026-01-01\n'
                '2,Redownload,123,2026-01-01\n'
                '4,Manual update,123,2026-01-01\n'
                '1,New future type,123,2026-01-01\n')
        rows = self.parse(data)['rows']
        self.assertEqual([(r['type'], r['count']) for r in rows],
                         [('first_download', 3), ('redownload', 2), ('update', 4), ('unknown', 1)])
        self.assertEqual(rows[-1]['source_type'], 'New future type')
        parsed = self.parse(data)
        self.assertEqual(parsed['sources'][0]['id'], 's1')
        self.assertEqual(len(parsed['sources'][0]['sha256']), 64)
        self.assertEqual(parsed['rows'][0]['source_sha256'], parsed['sources'][0]['sha256'])
        self.assertEqual(parsed['rows'][0]['processing_date'], '2026-01-03')

    def test_invalid_checksum_size_or_incomplete_never_parse(self):
        from mission_control.apple_analytics_parser import parse_instance
        source = segment(HEADER + '2026-01-01,123,First-time Download,1\n')
        previous = parse_instance('123', '2026-01-02', [source], True)
        for mutation in (dict(source, checksum='0' * 32), dict(source, size=source['size'] + 1)):
            with self.subTest(mutation=mutation), self.assertRaises(Invalid):
                parse_instance('123', '2026-01-03', [mutation], True)
        with self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [source], False)
        with self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [], True)
        self.assertEqual(previous['rows'][0]['count'], 1)

    def test_foreign_app_invalid_rows_and_duplicate_headers_rejected(self):
        for data in (HEADER + '2026-01-01,999,Redownload,1\n',
                     HEADER + 'not-a-date,123,Redownload,1\n',
                     HEADER + '2026-01-01,123,Redownload,-1\n',
                     'Date,Date,App Apple Identifier,Download Type,Counts\n2026-01-01,2026-01-01,123,Redownload,1\n'):
            with self.subTest(data=data), self.assertRaises(Invalid):
                self.parse(data)

    def test_reconcile_replaces_whole_older_date_and_keeps_other_dates(self):
        from mission_control.apple_analytics_parser import reconcile
        before = self.parse(HEADER + '2026-01-01,123,First-time Download,3\n2026-01-02,123,Redownload,2\n')
        newer = self.parse(HEADER + '2026-01-01,123,First-time Download,5\n', '2026-01-04')
        rows = reconcile([before, newer])
        self.assertEqual([(r['date'], r['count']) for r in rows], [('2026-01-01', 5), ('2026-01-02', 2)])
        self.assertEqual(reconcile([before, before]), reconcile([before]))
        conflict = self.parse(HEADER + '2026-01-01,123,First-time Download,6\n', '2026-01-04')
        with self.assertRaises(Invalid):
            reconcile([newer, conflict])
        foreign = dict(newer, app_id='999')
        with self.assertRaises(Invalid):
            reconcile([before, foreign])

    def test_multiple_segments_and_segment_identity(self):
        from mission_control.apple_analytics_parser import parse_instance
        one = segment(HEADER + '2026-01-01,123,Redownload,1\n', 'a')
        two = segment(HEADER + '2026-01-01,123,Redownload,2\n', 'b')
        parsed = parse_instance('123', '2026-01-03', [one, two], True)
        self.assertEqual([row['count'] for row in parsed['rows']], [1, 2])
        with self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [one, one], True)

    def test_header_only_instance_is_unknown_not_complete(self):
        from mission_control.apple_analytics_parser import parse_instance
        with self.assertRaisesRegex(Invalid, 'contains no observations'):
            self.parse(HEADER)
        with self.assertRaisesRegex(Invalid, 'contains no observations'):
            parse_instance('123', '2026-01-03', [segment(HEADER, 'a'), segment(HEADER, 'b')], True)
        rows = parse_instance('123', '2026-01-03', [segment(HEADER, 'a'),
            segment(HEADER + '2026-01-01,123,Redownload,1\n', 'b')], True)['rows']
        self.assertEqual(rows[0]['count'], 1)

    def test_bounds_and_bad_gzip_are_rejected(self):
        from mission_control.apple_analytics_parser import parse_instance
        with self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [segment(HEADER, str(i)) for i in range(51)], True)
        broken = b'not-gzip'
        with self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [dict(id='bad', data=broken, size=len(broken), checksum=hashlib.md5(broken, usedforsecurity=False).hexdigest())], True)
        source = segment(HEADER + '2026-01-01,123,Redownload,1\n')
        with patch('mission_control.apple_analytics_parser.MAX_COMPRESSED', len(source['data']) - 1), self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [source], True)
        with patch('mission_control.apple_analytics_parser.MAX_DECOMPRESSED', 8), self.assertRaises(Invalid):
            parse_instance('123', '2026-01-03', [source], True)


if __name__ == '__main__':
    unittest.main()
