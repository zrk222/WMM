"""Synthetic Shorts research through authenticated task, review, intake and brief."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, digest
from mission_control.organic_video_discovery import discovery_task, qualify_submission
from mission_control.hypit_jobs import resolve_inputs
from mission_control.db import connection
from mission_control.creative_briefs import Briefs
from mission_control.creative_library import Library
from tests import test_organic_video_discovery as discovery
from tests import test_organic_video_collector as collector
from tests import test_organic_video_intake as intake
from tests.production_fixtures import ready_capabilities


def youtube_bundle(task, count=10, collected=None):
    result = discovery.bundle(task, count, collected)
    item = result['candidates'][0]
    for index, row in enumerate([item['candidate'], *item['history']]):
        row.update(platform='youtube', post_id=f'QAshort{index:04d}', format='short',
                   url=f'https://www.youtube.com/shorts/QAshort{index:04d}')
    item['evidence'] = [dict(post_id=row['post_id'], url=row['url'], observed_at=row['observed_at'],
        observation_hash=digest(row), source_sha256='b'*64) for row in [item['candidate'], *item['history']]]
    return result


def youtube_task():
    old = discovery.task()
    policy = dict(old['policy'], platforms=['youtube'], hosts=['youtube.com', 'www.youtube.com'])
    return discovery_task(old['app'], policy, old['query'])


class YouTubeShortResearchTests(unittest.TestCase):
    def test_thresholds_missing_baseline_and_separate_permissions(self):
        task = youtube_task()
        for count, views, expected in ((10, 100000, 'QUALIFIED_BY_REPORTED_COUNTS'),
            (10, 99999, 'NOT_QUALIFIED'), (9, 1000000, 'INSUFFICIENT_BASELINE'),
            (0, 1000000, 'INSUFFICIENT_BASELINE')):
            value = youtube_bundle(task, count)
            value['candidates'][0]['rights'] = 'ALLOWED'  # A collector assertion cannot confer reuse.
            value['candidates'][0]['candidate']['views'] = views
            value['candidates'][0]['evidence'][0]['observation_hash'] = digest(value['candidates'][0]['candidate'])
            result = qualify_submission(task, value)['items'][0]
            self.assertEqual(result['qualification']['qualification'], expected)
            self.assertEqual(result['reuse_permission'], 'NOT_ESTABLISHED')
            self.assertEqual(result['publication'], 'NOT_RUN')
        value = youtube_bundle(task)
        for row in value['candidates'][0]['history']:
            row['views'] = 10001
        for row, evidence in zip(value['candidates'][0]['history'], value['candidates'][0]['evidence'][1:]):
            evidence['observation_hash'] = digest(row)
        self.assertEqual(qualify_submission(task, value)['items'][0]['qualification']['qualification'], 'NOT_QUALIFIED')

    def test_exact_short_hosts_paths_identity_and_baseline_format(self):
        task = youtube_task()
        for url in ('http://www.youtube.com/shorts/QAshort0000',
            'https://youtube.com.evil.invalid/shorts/QAshort0000', 'https://youtu.be/QAshort0000',
            'https://www.youtube.com/watch?v=QAshort0000', 'https://www.youtube.com/shorts/QAshort0000?x=1',
            'https://www.youtube.com/shorts/QAshort0000#x', 'https://www.youtube.com/shorts/QAshort0000/',
            'https://www.youtube.com/shorts/DIFFERENT00', 'https://www.youtube.com/shorts/%51Ashort0000'):
            value = youtube_bundle(task)
            value['candidates'][0]['candidate']['url'] = url
            with self.subTest(url=url), self.assertRaises(Invalid):
                qualify_submission(task, value)
        value = youtube_bundle(task)
        value['candidates'][0]['history'][0]['format'] = 'long'
        with self.assertRaises(Invalid):
            qualify_submission(task, value)

    def test_true_task_submit_owner_adoption_brief_and_hypit_input_roundtrip(self):
        fixture = intake.IntakeTests()
        original_owner = collector.CollectorTests.owner_call
        def owner_call(instance, body=None, **kwargs):
            selected = deepcopy(instance.body if body is None else body)
            selected['policy'].update(platforms=['youtube'], hosts=['www.youtube.com'])
            return original_owner(instance, selected, **kwargs)
        with patch.object(collector.CollectorTests, 'owner_call', owner_call), patch.object(collector, 'bundle', youtube_bundle):
            fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bad = deepcopy(fixture.body)
        bad['source_metadata']['permission_confirmed'] = False
        with self.assertRaises(Invalid):
            fixture.call(bad)
        adopted = fixture.call()
        identity = adopted['data']
        source = next(row for row in Library(fixture.store).list(fixture.app) if row['id'] == identity['source']['id'])
        self.assertEqual(source['current']['data']['platform'], 'youtube')
        self.assertEqual(source['current']['data']['rights'], 'REFERENCE_ONLY')
        self.assertEqual(identity['foreign_bytes'], 'NOT_AUTHORIZED')
        ready_capabilities(fixture.store, fixture.app, [source])
        data = dict(fixture.brief, analysis_id=identity['analysis']['id'], analysis_hash=identity['analysis']['hash'],
            discovery=dict(schema='wmm.brief-discovery.v1', mode='ORIGINAL_RECREATION',
                manifest_version=fixture.store.app(fixture.app)['version'],
                collection_id=identity['collection']['id'], collection_hash=identity['collection']['hash'],
                reference_id=identity['source']['id'], review_hash=identity['review']['hash']))
        brief = Briefs(fixture.store).save(fixture.app, dict(data=data))
        with connection(fixture.store.path) as db:
            inputs, _ = resolve_inputs(db, fixture.store, fixture.app,
                dict(brief_id=brief['id'], brief_hash=brief['hash'], shape='PORTRAIT'))
        self.assertEqual(inputs['request']['brief']['data']['source']['data']['platform'], 'youtube')
        self.assertEqual(brief['data']['discovery']['collection_provenance'], identity['provenance'])
        self.assertEqual(brief['data']['publication'], 'NOT_RUN')


if __name__ == '__main__':
    unittest.main()
