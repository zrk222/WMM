"""Adversarial package discovery and bounded Google Play read projection."""
import json
import unittest
from mission_control.common import Invalid
from mission_control.play_contract import package_candidates, target
from mission_control.play_reports import read

TARGET = dict(package_name='com.example.synthetic', track='production')


class Reader:
    def __init__(self, *pages):
        self.pages = list(pages); self.urls = []

    def read(self, url):
        self.urls.append(url)
        return self.pages.pop(0)


def release(state='PUBLISHED', **fields):
    return dict(track='production', releaseName='Synthetic 2.0',
                activeArtifacts=[dict(versionCode=42)],
                releaseLifecycleState='RELEASE_LIFECYCLE_STATE_' + state, **fields)


def product(identity='synthetic_monthly', package='com.example.synthetic'):
    return dict(packageName=package, productId=identity,
                basePlans=[dict(basePlanId='monthly', state='ACTIVE')],
                listings=[dict(languageCode='en-US', title='Synthetic')])


class DiscoveryTests(unittest.TestCase):
    def test_explicit_expo_and_plain_android_json(self):
        for data in ({'expo': {'android': {'package': TARGET['package_name']}}},
                     {'android': {'package': TARGET['package_name']}}):
            value = package_candidates('app.json', json.dumps(data))
            self.assertEqual(value['package_candidates'], [TARGET['package_name']])
            self.assertFalse(value['executed_project_code'])

    def test_manifest_and_gradle_literals_without_comments(self):
        value = package_candidates('AndroidManifest.xml', '<manifest package="com.example.synthetic"/>')
        self.assertEqual(value['package_candidates'], [TARGET['package_name']])
        text = '/* applicationId "com.other.comment" */\napplicationId = "com.example.synthetic"\n// applicationId "com.other.comment"'
        self.assertEqual(package_candidates('build.gradle.kts', text)['package_candidates'], [TARGET['package_name']])

    def test_flavors_and_computed_identity_require_review(self):
        v = package_candidates('build.gradle', 'applicationId "com.example.first"\napplicationId "com.example.second"')
        self.assertTrue(v['requires_selection']); self.assertEqual(len(v['package_candidates']), 2)
        v = package_candidates('build.gradle', 'applicationId "com.example.synthetic"\napplicationIdSuffix ".demo"')
        self.assertTrue(v['unresolved_variants']); self.assertTrue(v['requires_selection'])
        self.assertEqual(package_candidates('build.gradle', 'applicationId = project.applicationId')['package_candidates'], [])

    def test_untrusted_metadata_and_duplicate_fields_fail(self):
        cases = [('app.config.js', 'export default {}'), ('app.json', '{"android":{},"android":{}}'),
                 ('app.json', '['), ('app.json', 'x' * 131073),
                 ('AndroidManifest.xml', '<!DOCTYPE manifest [<!ENTITY x "unsafe">]><manifest/>')]
        for kind, text in cases:
            with self.subTest(kind=kind), self.assertRaises(Invalid):
                package_candidates(kind, text)

    def test_target_rejects_path_query_and_extra_authority(self):
        self.assertEqual(target(TARGET), TARGET)
        for value in ({**TARGET, 'package_name': 'com.example/evil'}, {**TARGET, 'track': '../production'},
                      {**TARGET, 'track': 'production?token=bad'}, {**TARGET, 'publish': True}):
            with self.subTest(value=value), self.assertRaises(Invalid):target(value)


class PlayReportTests(unittest.TestCase):
    def test_published_never_means_global_availability(self):
        reader = Reader({'releases': [release()]})
        result = read(TARGET, 'play_releases', reader)
        self.assertEqual(reader.urls, ['https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.example.synthetic/tracks/production/releases'])
        self.assertEqual(result['releases'][0]['version_codes'], [42])
        self.assertEqual(result['releases'][0]['global_availability'], 'NOT_VERIFIED')
        self.assertIsNone(result['releases'][0]['rollout_fraction'])
        self.assertFalse(result['external_writes']); self.assertEqual(len(result['page_source_hashes']), 1)

    def test_lifecycle_is_preserved_without_inventing_ready(self):
        for state in ('DRAFT', 'IN_REVIEW', 'APPROVED_NOT_PUBLISHED', 'NOT_APPROVED', 'FUTURE_STATE'):
            result = read(TARGET, 'play_releases', Reader({'releases': [release(state)]}))
            r = result['releases'][0]
            self.assertEqual(r['lifecycle'], 'RELEASE_LIFECYCLE_STATE_' + state)
            self.assertEqual(r['recognized_state'], state != 'FUTURE_STATE')
            self.assertEqual(r['global_availability'], 'NOT_VERIFIED')

    def test_empty_missing_optional_and_twenty_release_limit(self):
        self.assertEqual(read(TARGET, 'play_releases', Reader({}))['releases'], [])
        r = release(); del r['releaseName']; del r['releaseLifecycleState']
        self.assertIsNone(read(TARGET, 'play_releases', Reader({'releases': [r]}))['releases'][0]['release_name'])
        v = read(TARGET, 'play_releases', Reader({'releases': [release() for _ in range(20)]}))
        self.assertEqual(v['coverage'], 'LIMITED')

    def test_foreign_track_and_invalid_artifacts_fail(self):
        for bad in ({**release(), 'track': 'internal'}, {**release(), 'activeArtifacts': [{'versionCode': True}]},
                    {**release(), 'activeArtifacts': [{'versionCode': 42}, {'versionCode': 42}]},
                    {**release(), 'releaseName': 'spoof\u202e'}, {**release(), 'activeArtifacts': 'wrong'}):
            with self.subTest(bad=bad), self.assertRaises(Invalid):
                read(TARGET, 'play_releases', Reader({'releases': [bad]}))

    def test_catalog_pagination_identity_and_public_projection(self):
        reader = Reader({'subscriptions': [product('first')], 'nextPageToken': 'abc+/='},
                        {'subscriptions': [product('second')]})
        result = read(TARGET, 'play_subscriptions', reader)
        self.assertEqual(result['pages'], 2); self.assertEqual(result['coverage'], 'COMPLETE_RETURNED_CATALOG')
        self.assertIn('pageToken=abc%2B%2F%3D', reader.urls[1])
        self.assertEqual(result['subscriptions'][0]['purchase_and_restore'], 'NOT_TESTED')
        self.assertEqual(result['subscriptions'][0]['localized_price'], 'NOT_ASSESSED')
        self.assertNotIn('title', str(result['subscriptions']))

    def test_hostile_looping_and_duplicate_pagination_fail(self):
        cases = [({'nextPageToken': 'https://evil.example'},),
                 ({'nextPageToken': 'repeat'}, {'nextPageToken': 'repeat'}),
                 ({'subscriptions': [product()], 'nextPageToken': 'next'}, {'subscriptions': [product()]})]
        for pages in cases:
            with self.subTest(pages=pages), self.assertRaises(Invalid):
                read(TARGET, 'play_subscriptions', Reader(*pages))

    def test_catalog_three_page_budget_preserves_unknown_tail(self):
        reader = Reader(*[{'subscriptions': [product(str(i))], 'nextPageToken': 'next' + str(i)} for i in range(3)])
        result = read(TARGET, 'play_subscriptions', reader)
        self.assertEqual(result['pages'], 3); self.assertEqual(result['coverage'], 'LIMITED')
        self.assertEqual(len(reader.urls), 3); self.assertEqual(result['remaining_pages'], 'NOT_READ')

    def test_foreign_package_malformed_response_and_forbidden_action_fail(self):
        for operation, payload in [('publish', {}), ('play_releases', {'error': {'secret': 'must not appear'}}),
                                   ('play_releases', {'releases': 'wrong'}),
                                   ('play_subscriptions', {'subscriptions': [product(package='com.other.app')]})]:
            with self.subTest(operation=operation), self.assertRaises(Invalid) as failure:
                read(TARGET, operation, Reader(payload))
            self.assertNotIn('must not appear', str(failure.exception))

    def test_track_path_is_encoded_not_reinterpreted(self):
        reader = Reader({})
        read({**TARGET, 'track': 'wear:production'}, 'play_releases', reader)
        self.assertIn('/tracks/wear%3Aproduction/releases', reader.urls[0])


if __name__ == '__main__':unittest.main()
