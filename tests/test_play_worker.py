"""Google Play uses the real local queue with synthetic provider responses and isolated keys."""
import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from mission_control import play_auth, provider_auth
from mission_control.common import Invalid, uid
from mission_control.credential_vault import namespace, target
from mission_control.play_contract import SCOPE
from mission_control.provider_reports import report_options
from mission_control.service import Service, validate_binding
from mission_control.store import Store
from mission_control.worker import enqueue, jobs, run_once
from tests.test_play_connections import CONFIG, GRANT, MemoryVault
from tests.test_play_reports import product


class PlayFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'play.sqlite', seed=False)
        data = dict(name='Synthetic Android app', job='Test', audience='Synthetic', activation='Saved', release='1', locale='en-US',
                    store_app_id='123', android_package='com.example.synthetic', android_track='production')
        for app in ('sample-one', 'sample-two'):self.store.save_app(app, data)
        self.data = dict(provider='google_play', auth_mode='managed_oauth', credential_ref=uid(),
                         client_id=CONFIG['client_id'], scopes=[SCOPE], account_id='ACCOUNT_NOT_READ',
                         store_app_id='com.example.synthetic', package_name='com.example.synthetic', track='production')
        self.record = self.store.save_record('sample-one', dict(kind='connection', title='Synthetic Play connection', source='Synthetic consent', data=self.data))
        self.vault = MemoryVault(); self.name = target(namespace(self.store.path), 'sample-one', 'google_play', self.data['credential_ref'])
        secret = dict(CONFIG, refresh_token=GRANT['refresh_token'], scopes=[SCOPE],
                      binding=dict(app_id='sample-one', package_name=self.data['package_name'], track=self.data['track'], client_id=CONFIG['client_id']))
        self.vault.put(self.name, secret)
        patch('mission_control.provider_auth.Vault', return_value=self.vault).start(); self.addCleanup(patch.stopall)
        self.token = patch.object(play_auth, 'token_request', return_value=dict(GRANT, token_type='Bearer', scope=SCOPE)).start()
        self.network = patch.object(play_auth, 'read_json', return_value={}).start()
        provider_auth.CACHE.clear(); self.addCleanup(provider_auth.CACHE.clear)
        self.service = Service(self.store)

    def queue(self, **data):
        return self.service.queue('sample-one', dict(action='sync', request_key=uid(), data=dict(connection_id=self.record['id'], **data)))

    def result(self, identity):
        return next(r for r in jobs(self.store, 'sample-one') if r['id'] == identity)


class PlayWorkerTests(PlayFixture):
    def test_default_manual_read_binds_manifest_and_returns_safe_receipt(self):
        job = self.queue()
        self.assertEqual(job['data']['manifest_version'], self.store.app('sample-one')['version'])
        self.assertEqual(job['data']['options'], {'operation': 'play_releases'})
        self.assertTrue(run_once(self.store)); result = self.result(job['id'])
        self.assertEqual(result['status'], 'SUCCEEDED'); self.assertEqual(result['result']['app_id'], 'sample-one')
        self.assertEqual(result['result']['package_name'], self.data['package_name'])
        self.assertFalse(result['result']['external_writes']); self.assertTrue(result['result']['source_hash'])
        for secret in (GRANT['access_token'], GRANT['refresh_token'], CONFIG['client_secret']):self.assertNotIn(secret, json.dumps(result))
        self.assertLessEqual(self.network.call_args.kwargs['timeout'], 10)

    def test_subscription_read_paginates_with_same_target_and_no_price_claim(self):
        self.network.side_effect = [{'subscriptions': [product('first')], 'nextPageToken': 'next'}, {'subscriptions': [product('second')]}]
        job = self.queue(options={'operation': 'play_subscriptions'}); run_once(self.store)
        result = self.result(job['id'])
        self.assertEqual(result['status'], 'SUCCEEDED'); self.assertEqual(result['result']['pages'], 2)
        self.assertEqual(result['result']['subscriptions'][0]['localized_price'], 'NOT_ASSESSED')
        self.assertEqual(self.network.call_count, 2)
        self.assertTrue(all(self.data['package_name'] in c.args[0] for c in self.network.call_args_list))

    def test_operation_and_foreign_app_are_denied_before_any_network(self):
        for options in ({'operation':'publish'}, {'operation':'reviews'}, {'operation':'play_releases','edit_id':'forbidden'}):
            with self.assertRaises(Invalid):self.queue(options=options)
        with self.assertRaises(Invalid):self.service.queue('sample-two', dict(action='sync', data={'connection_id':self.record['id']}))
        with self.assertRaises(Invalid):report_options('app_store', {'operation':'play_releases'})
        self.token.assert_not_called(); self.network.assert_not_called()

    def test_changed_app_and_connection_block_queued_reads_before_credential_use(self):
        job = self.queue(); app = self.store.app('sample-one')
        self.store.save_app('sample-one', dict(app['data'], android_track='internal'), app['version'])
        run_once(self.store); self.assertEqual(self.result(job['id'])['status'], 'BLOCKED')
        self.token.assert_not_called(); self.network.assert_not_called()

    def test_direct_queue_without_manifest_guard_is_not_an_authority_bypass(self):
        job = enqueue(self.store, 'sample-one', 'sync', dict(connection_id=self.record['id'], connection_version=self.record['version']), uid())
        run_once(self.store); self.assertEqual(self.result(job['id'])['status'], 'BLOCKED')
        self.token.assert_not_called(); self.network.assert_not_called()

    def test_cancel_during_network_prevents_result_adoption(self):
        job = self.queue()
        def cancelled(*args, **kwargs):
            self.service.cancel('sample-one', job['id']); return {}
        self.network.side_effect = cancelled; run_once(self.store)
        result = self.result(job['id']); self.assertEqual(result['status'], 'CANCELLED')
        self.assertIsNone(result['result'])

    def test_source_change_during_read_prevents_result_adoption(self):
        job = self.queue()
        def changed(*args, **kwargs):
            old = self.store.app('sample-one'); self.store.save_app('sample-one', dict(old['data'], release='2'), old['version']); return {}
        self.network.side_effect = changed; run_once(self.store)
        result = self.result(job['id']); self.assertEqual(result['status'], 'BLOCKED')
        self.assertNotIn('releases', result['result'])

    def test_native_scope_is_checked_before_cached_bearer_reuse(self):
        secret = self.vault.get(self.name); secret['binding']['package_name'] = 'com.other.foreign'
        self.vault.put(self.name, secret); provider_auth.CACHE[self.name] = ('synthetic-cached-bearer', time.time()+GRANT['expires_in'])
        job = self.queue(); run_once(self.store)
        self.assertEqual(self.result(job['id'])['status'], 'BLOCKED')
        self.token.assert_not_called(); self.network.assert_not_called()

    def test_token_refresh_rotation_persists_before_cache_and_survives_cache_expiry(self):
        binding = dict(self.data, _vault_namespace=namespace(self.store.path))
        self.assertEqual(provider_auth.credential(binding, 'sample-one'), GRANT['access_token'])
        self.assertEqual(provider_auth.credential(binding, 'sample-one'), GRANT['access_token'])
        self.assertEqual(self.token.call_count, 1)
        provider_auth.CACHE[self.name] = ('old', 0)
        self.token.return_value = dict(GRANT, refresh_token='synthetic-rotated-refresh', token_type='Bearer', scope=SCOPE)
        provider_auth.credential(binding, 'sample-one')
        self.assertEqual(self.vault.get(self.name)['refresh_token'], 'synthetic-rotated-refresh')
        provider_auth.CACHE[self.name] = ('old', 0); self.vault.fail_put = True
        self.token.return_value['refresh_token'] = 'synthetic-next-rotation'
        with self.assertRaises(Invalid):provider_auth.credential(binding, 'sample-one')
        self.assertEqual(provider_auth.CACHE[self.name], ('old', 0))

    def test_provider_error_and_foreign_catalog_never_become_empty_success(self):
        for payload, operation in [({'error':{'message':'synthetic-sensitive-value'}}, 'play_releases'),
                                   ({'subscriptions':[product(package='com.other.foreign')]}, 'play_subscriptions')]:
            self.network.return_value = payload
            job = self.queue(options={'operation':operation}); run_once(self.store)
            result = self.result(job['id']); self.assertEqual(result['status'], 'BLOCKED')
            self.assertNotIn('synthetic-sensitive-value', json.dumps(result))

    def test_read_deadline_stops_before_network(self):
        reader = play_auth.PlayReader({'package_name':self.data['package_name'], 'track':'production'}, GRANT['access_token'])
        reader.deadline = 0
        with self.assertRaises(Invalid):reader.read('https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.example.synthetic/tracks/production/releases')
        self.network.assert_not_called()

    def test_public_binding_cannot_inject_runtime_scope_or_use_plaintext_auth(self):
        validate_binding(self.data, 'sample-one')
        for data in (dict(self.data, _vault_namespace='forbidden'), dict(self.data, auth_mode='env'), dict(self.data, scopes=['other'])):
            with self.assertRaises(Invalid):validate_binding(data, 'sample-one')


if __name__ == '__main__':unittest.main()
