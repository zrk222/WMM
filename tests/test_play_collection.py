"""Agent collection binds Android and Apple identities separately and keeps approval fingerprints current."""
import copy
from unittest.mock import patch
from mission_control.campaign_inputs import CampaignInputs, build_plan
from mission_control.common import Invalid, digest
from mission_control.marketing_agent_manifest import authorize_read, operating_manifest
from mission_control.worker import jobs, run_once
from tests.test_play_worker import PlayFixture


class PlayCollectionTests(PlayFixture):
    def test_google_and_apple_reads_coexist_with_distinct_identifiers(self):
        self.store.save_record('sample-one', dict(kind='connection', title='Synthetic Apple', source='Synthetic setup',
            data=dict(provider='app_store', store_app_id='123', account_id='0', env_ref='SYNTHETIC_REFERENCE')))
        plan = CampaignInputs(self.store).preview('sample-one')
        operations = {(t['provider'],t['operation']) for t in plan['tasks']}
        self.assertEqual(operations, {('google_play','play_releases'), ('google_play','play_subscriptions'),
                                     ('app_store','identity_inventory'), ('app_store','reviews'), ('app_store','subscription_catalog')})
        self.assertEqual(self.store.app('sample-one')['data']['store_app_id'], '123')
        self.assertEqual(len(plan['tasks']), 5); self.assertFalse(plan['external_writes'])
        self.assertEqual(plan['operating_manifest']['policy_version'], 8)
        self.assertIn('discover_setup', plan['operating_manifest']['supported_resolution_tools'])
        self.assertEqual(plan['operating_manifest']['supported_execution']['provider_writes'], [])

    def test_google_reads_do_not_require_an_apple_store_id(self):
        app = self.store.app('sample-one'); data = dict(app['data']); data.pop('store_app_id')
        self.store.save_app('sample-one', data, app['version'])
        self.assertEqual(len(CampaignInputs(self.store).preview('sample-one')['tasks']), 2)

    def test_wrong_android_target_and_disconnection_are_visible_exclusions(self):
        app = self.store.app('sample-one'); self.store.save_app('sample-one', dict(app['data'], android_track='internal'), app['version'])
        plan = CampaignInputs(self.store).preview('sample-one')
        self.assertEqual(plan['tasks'], []); self.assertEqual(len(plan['excluded']), 1)
        self.assertEqual(plan['status'], 'SOURCE_ACCESS_REQUIRED')

    def test_old_policy_and_cross_provider_operations_cannot_reuse_approval(self):
        app = self.store.app('sample-one'); policy = operating_manifest(app)
        data = dict(connection_id=self.record['id'], connection_version=self.record['version'], manifest_version=app['version'],
                    agent_policy_sha256=digest(policy), options={'operation':'play_releases'})
        authorize_read(app, self.data, data)
        prior = copy.deepcopy(policy); prior['policy_version'] = 6
        with self.assertRaises(Invalid):authorize_read(app, self.data, dict(data, agent_policy_sha256=digest(prior)))
        for options in ({'operation':'reviews'}, {'operation':'play_releases','publish':True}):
            with self.assertRaises(Invalid):authorize_read(app, self.data, dict(data, options=options))

    def test_stale_collection_plan_and_foreign_records_reject_before_queue(self):
        collector = CampaignInputs(self.store); plan = collector.preview('sample-one')
        app = self.store.app('sample-one'); self.store.save_app('sample-one', dict(app['data'], release='2'), app['version'])
        with self.assertRaises(Invalid):collector.start('sample-one', {k:plan[k] for k in ('manifest_version','source_hash')})
        self.assertEqual(jobs(self.store,'sample-one'), [])
        with self.assertRaises(Invalid):build_plan(self.store.app('sample-two'), [self.record], 'synthetic-hour')

    def test_actual_collection_queue_completes_bounded_reads_without_claiming_outcomes(self):
        collector = CampaignInputs(self.store); plan = collector.preview('sample-one')
        started = collector.start('sample-one', {k:plan[k] for k in ('manifest_version','source_hash')})
        self.assertEqual(len(started['tasks']), 2)
        run_once(self.store); run_once(self.store)
        rows = jobs(self.store, 'sample-one'); self.assertEqual(len(rows), 2)
        self.assertTrue(all(r['status']=='SUCCEEDED' for r in rows))
        self.assertTrue(all(r['result']['authority']=='NO_EXECUTION_AUTHORITY' for r in rows))
        self.assertTrue(all(r['result']['attribution']=='NOT_ASSESSED' for r in rows))
        self.assertEqual(self.network.call_count, 2); self.assertEqual(self.token.call_count, 1)
