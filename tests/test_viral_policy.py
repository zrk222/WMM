"""Exact user-selected viral cutoff, comparable creator baseline and approval boundaries."""
from datetime import datetime, timedelta, timezone
import copy
import unittest
from mission_control.common import Invalid
from mission_control.viral_policy import qualify, median_views

AS_OF = '2026-10-24T12:00:00+00:00'


def candidate(views=100000):
    return dict(platform='tiktok', post_id='candidate', creator_id='creator', format='short',
                url='https://www.tiktok.com/@creator/video/123', views=views,
                published_at='2026-10-23T12:00:00+00:00', observed_at=AS_OF)


def history(views=10000, count=10):
    rows = []
    for index in range(count):
        stamp = datetime(2026, 10, 22, tzinfo=timezone.utc) - timedelta(days=index)
        rows.append(dict(candidate(views), post_id=f'post-{index}', published_at=stamp.isoformat(),
                         url=f'https://www.tiktok.com/@creator/video/{1000+index}'))
    return rows


class ViralPolicyTests(unittest.TestCase):
    def test_both_absolute_and_relative_boundaries_are_mandatory(self):
        self.assertEqual(qualify(candidate(), history(), AS_OF)['qualification'], 'QUALIFIED_BY_REPORTED_COUNTS')
        self.assertEqual(qualify(candidate(99999), history(1), AS_OF)['reasons'], ['BELOW_100000_VIEWS'])
        self.assertEqual(qualify(candidate(100000), history(10001), AS_OF)['reasons'], ['BELOW_TENFOLD_MEDIAN'])
        self.assertEqual(qualify(candidate(100010), history(10001), AS_OF)['qualification'], 'QUALIFIED_BY_REPORTED_COUNTS')

    def test_even_median_is_exact_and_never_rounded_down(self):
        rows = history(10000)
        for row in rows[5:]:
            row['views'] = 10001
        result = qualify(candidate(100004), rows, AS_OF)
        self.assertEqual(result['median'], dict(numerator=20001, denominator=2))
        self.assertEqual(result['required_views'], 100005)
        self.assertEqual(result['qualification'], 'NOT_QUALIFIED')
        self.assertEqual(qualify(candidate(100005), rows, AS_OF)['qualification'], 'QUALIFIED_BY_REPORTED_COUNTS')
        self.assertEqual(median_views([dict(views=1), dict(views=2), dict(views=8)]), 2)

    def test_missing_and_zero_baselines_never_qualify(self):
        for rows in ([], history(count=9), history(0)):
            with self.subTest(rows=len(rows)):
                result = qualify(candidate(1000000), rows, AS_OF)
                self.assertEqual(result['qualification'], 'INSUFFICIENT_BASELINE')
                self.assertIsNone(result['required_views'])

    def test_candidate_exclusion_recent_twenty_and_order_independent_receipts(self):
        rows = history(count=25)
        rows.append(candidate())
        original = copy.deepcopy(rows)
        result = qualify(candidate(), rows, AS_OF)
        self.assertEqual(result['baseline_count'], 20)
        self.assertNotIn('candidate', [row['post_id'] for row in result['baseline']])
        self.assertNotIn('post-20', [row['post_id'] for row in result['baseline']])
        self.assertEqual(result, qualify(candidate(), list(reversed(rows)), AS_OF))
        self.assertEqual(rows, original)
        changed = copy.deepcopy(rows)
        changed[0]['views'] += 1
        self.assertNotEqual(result['receipt_hash'], qualify(candidate(), changed, AS_OF)['receipt_hash'])

    def test_wrong_scope_duplicate_invalid_and_future_observations_reject(self):
        for changes in ({'creator_id': 'other'}, {'platform': 'instagram'}, {'platform': 'youtube'}, {'format': 'long'},
                        {'views': True}, {'views': -1}, {'views': '10000'}, {'views': 1.5}, {'views': 1000000000001},
                        {'observed_at': '2026-10-25T00:00:00+00:00'}, {'url': 'http://localhost/test'}, {'extra': 'hidden'}):
            rows = history()
            rows[0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                qualify(candidate(), rows, AS_OF)
        for rows in (history() + [history()[0]], history() + [dict(candidate(), views=99)], history() * 101):
            with self.assertRaises(Invalid):
                qualify(candidate(), rows, AS_OF)

    def test_qualified_is_not_verified_collection_reuse_or_publication(self):
        result = qualify(candidate(), history(), AS_OF)
        self.assertEqual(result['collection_verification'], 'REQUIRED')
        self.assertEqual(result['human_review'], 'REQUIRED')
        self.assertEqual(result['reuse_permission'], 'NOT_ESTABLISHED')
        self.assertEqual(result['publication'], 'NOT_RUN')
        later = dict(candidate(), post_id='later', published_at='2026-10-24T00:00:00+00:00')
        self.assertEqual(qualify(candidate(), history() + [later], AS_OF)['baseline_count'], 10)
