"""Synthetic source observations; no network or provider state."""
import copy
from datetime import datetime, timedelta, timezone
import unittest

from mission_control.common import Invalid, digest
from mission_control.operation_catalog import catalog
from mission_control.organic_video_discovery import discovery_task, qualify_submission, validate_submission
from mission_control.viral_policy import qualify


def task():
    expires = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    return discovery_task({'id': 'sample-one', 'version': 1, 'hash': 'a' * 64},
        {'recipient_grant_id': 'grant-one', 'platforms': ['tiktok'], 'hosts': ['www.tiktok.com'],
         'expires': expires, 'max_candidates': 5, 'max_reads': 100, 'max_seconds': 600,
         'access': 'PUBLIC_WEB'}, {'genre': 'personal growth', 'app_type': 'AI life coach',
                                  'search_terms': 'habit coaching'})


def bundle(task_value, count=10, collected=None):
    stamp = collected or datetime.now(timezone.utc)
    def obs(identity, days, views):
        return {'platform': 'tiktok', 'post_id': identity, 'creator_id': 'creator-one',
                'format': 'video', 'url': 'https://www.tiktok.com/@creator/video/' + identity,
                'views': views, 'published_at': (stamp - timedelta(days=days)).isoformat(),
                'observed_at': stamp.isoformat()}
    candidate = obs('candidate', 1, 100000)
    history = [obs(str(index), index + 2, 10000) for index in range(count)]
    def evidence(row):
        return {'post_id': row['post_id'], 'url': row['url'], 'observed_at': row['observed_at'],
                'observation_hash': digest(row), 'source_sha256': 'b' * 64}
    return {'task_id': 'task-one', 'task_hash': digest(task_value), 'claim_id': 'claim-one',
            'collected_at': stamp.isoformat(), 'read_count': 1,
            'candidates': [{'candidate': candidate, 'history': history,
                            'evidence': [evidence(row) for row in [candidate, *history]],
                            'relevance': 'MATCH', 'kind': 'REFERENCE', 'rights': 'UNKNOWN'}],
            'failures': [], 'execution': 'LIVE_EXTERNAL_AGENT'}


class DiscoveryContractTests(unittest.TestCase):
    def test_agent_catalog_describes_the_four_channel_submission(self):
        contract = catalog()['domain_contracts']['discovery_research']['short_video_collector']
        self.assertEqual(set(contract['direct_post_examples']), {'facebook', 'instagram', 'tiktok', 'youtube'})
        sample = bundle(task())
        self.assertEqual(set(contract['submit']['result_fields']), set(sample))
        self.assertEqual(set(contract['observation_fields']), set(sample['candidates'][0]['candidate']))
        self.assertEqual(set(contract['evidence_fields']), set(sample['candidates'][0]['evidence'][0]))

    def test_exact_existing_viral_threshold_and_history_limits(self):
        value = task()
        for count in (9, 10, 20):
            result = qualify_submission(value, bundle(value, count))['items'][0]
            expected = 'INSUFFICIENT_BASELINE' if count == 9 else 'QUALIFIED_BY_REPORTED_COUNTS'
            self.assertEqual(result['qualification']['qualification'], expected)
            self.assertEqual(result['reuse_permission'], 'NOT_ESTABLISHED')
            if count >= 10:
                self.assertEqual(result['status'], 'COLLECTION_REVIEW_REQUIRED')
        # The underlying policy selects the latest 20 of 21 without changing its median logic.
        data = bundle(value, 21)
        data['candidates'][0]['history'][-1]['views'] = 999999
        receipt = qualify(data['candidates'][0]['candidate'], data['candidates'][0]['history'], data['collected_at'])
        self.assertEqual(receipt['baseline_count'], 20)
        self.assertEqual(receipt['median'], {'numerator': 10000, 'denominator': 1})
        with self.assertRaises(Invalid):
            validate_submission(value, data)

    def test_source_receipts_scope_and_unknown_rights(self):
        value = task(); data = bundle(value)
        self.assertEqual(validate_submission(value, data), data)
        row = qualify_submission(value, data)['items'][0]
        self.assertEqual(row['collector_asserted_rights'], 'UNKNOWN')
        self.assertEqual(row['qualification']['qualification'], 'QUALIFIED_BY_REPORTED_COUNTS')
        self.assertEqual(row['reuse_permission'], 'NOT_ESTABLISHED')
        for mutate in (lambda x: x['candidates'][0]['candidate'].update(views=123456),
                       lambda x: x['candidates'][0]['evidence'][0].update(source_sha256='fake'),
                       lambda x: x.update(execution='SAVED_POOL'),
                       lambda x: x['candidates'][0]['candidate'].update(url='https://example.com/x'),
                       lambda x: x['candidates'][0]['history'][0].update(creator_id='other')):
            changed = copy.deepcopy(data); mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(Invalid):
                qualify_submission(value, changed)

    def test_post_links_are_required_for_new_observations_but_not_failure_sources(self):
        cases = (
            ('facebook', 'www.facebook.com', '/synthetic-page/videos/', '/synthetic-page'),
            ('instagram', 'www.instagram.com', '/reel/', '/synthetic-profile/'),
            ('tiktok', 'www.tiktok.com', '/@synthetic/video/', '/@synthetic'),
            ('youtube', 'www.youtube.com', '/shorts/', '/@synthetic'),
        )
        for platform, host, post_path, profile_path in cases:
            with self.subTest(platform=platform):
                value = task()
                value['policy'].update(platforms=[platform], hosts=[host])
                data = bundle(value, 1)
                item = data['candidates'][0]
                observations = [item['candidate'], *item['history']]
                for index, row in enumerate(observations):
                    identity = f'{index + 1:011d}'
                    row.update(platform=platform, post_id=identity, url=f'https://{host}{post_path}{identity}')
                    if platform == 'youtube':
                        row['format'] = 'short'
                    item['evidence'][index].update(post_id=identity, url=row['url'], observation_hash=digest(row))
                profile_url = f'https://{host}{profile_path}'
                for index in range(len(observations)):
                    invalid = copy.deepcopy(data)
                    invalid_item = invalid['candidates'][0]
                    row = [invalid_item['candidate'], *invalid_item['history']][index]
                    row['url'] = profile_url
                    invalid_item['evidence'][index].update(url=profile_url, observation_hash=digest(row))
                    with self.assertRaises(Invalid):
                        validate_submission(value, invalid)
                    if platform != 'youtube':
                        self.assertEqual(validate_submission(value, invalid, require_post_links=False), invalid)
                aliased = copy.deepcopy(data)
                aliased_item = aliased['candidates'][0]
                aliased_candidate = aliased_item['candidate']
                aliased_candidate['url'] = aliased_item['history'][0]['url']
                aliased_item['evidence'][0].update(
                    url=aliased_candidate['url'], observation_hash=digest(aliased_candidate))
                with self.assertRaises(Invalid):
                    validate_submission(value, aliased)
                if platform != 'youtube':
                    mismatched = copy.deepcopy(data)
                    wrong_item = mismatched['candidates'][0]
                    wrong_candidate = wrong_item['candidate']
                    wrong_candidate['url'] = f'https://{host}{post_path}99999999999'
                    wrong_item['evidence'][0].update(
                        url=wrong_candidate['url'], observation_hash=digest(wrong_candidate))
                    with self.assertRaisesRegex(Invalid, 'post identity must match'):
                        validate_submission(value, mismatched)
                data['failures'] = [{'source': profile_url, 'code': 'LOGIN'}]
                self.assertEqual(validate_submission(value, data), data)

    def test_fractional_median_and_both_thresholds(self):
        value = task(); data = bundle(value)
        # Five 10000-view and five 10001-view posts yield an exact half-view median.
        for index in range(5):
            row = data['candidates'][0]['history'][index]
            row['views'] = 10001
            data['candidates'][0]['evidence'][index + 1]['observation_hash'] = digest(row)
        receipt = qualify_submission(value, data)['items'][0]['qualification']
        self.assertEqual(receipt['median'], {'numerator': 20001, 'denominator': 2})
        self.assertEqual(receipt['required_views'], 100005)
        self.assertEqual(receipt['qualification'], 'NOT_QUALIFIED')
        candidate = data['candidates'][0]['candidate']
        candidate['views'] = 100005
        data['candidates'][0]['evidence'][0]['observation_hash'] = digest(candidate)
        self.assertEqual(qualify_submission(value, data)['items'][0]['qualification']['qualification'],
                         'QUALIFIED_BY_REPORTED_COUNTS')

    def test_stale_future_and_ugc_are_not_fabricated(self):
        value = task()
        data = bundle(value, 0)
        data['candidates'][0]['kind'] = 'UGC'
        data['candidates'][0]['candidate']['views'] = None
        data['candidates'][0]['evidence'][0]['observation_hash'] = digest(data['candidates'][0]['candidate'])
        item = qualify_submission(value, data)['items'][0]
        self.assertEqual(item['status'], 'UGC_OWNER_REVIEW_REQUIRED')
        self.assertEqual(item['qualification']['qualification'], 'UGC_EXEMPT')
        for shift in (-25, 1):
            data = bundle(value, collected=datetime.now(timezone.utc) + timedelta(hours=shift))
            with self.subTest(shift=shift), self.assertRaises(Invalid):
                validate_submission(value, data)


if __name__ == '__main__':
    unittest.main()
