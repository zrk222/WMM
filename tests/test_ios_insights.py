"""Real native SQLite and scoped Keychain callback with synthetic PostHog HTTP."""
import copy
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_insights import NativeInsights
from tests import test_ios_host as fixture
from tests.test_measurement_connectors import setup_body, payloads


class NativeInsightsTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def start(self):
        self.runtime.create_workspace(self.session, self.creation())
        self.values = {}; self.fail_delete = False
        self.gateway = NativeInsights(self.runtime.service, self.runtime.identities, self.vault)

    def vault(self, raw):
        body = json.loads(raw); action, target = body['action'], body['target']
        if action == 'put':self.values[target] = copy.deepcopy(body['value']); value = None
        elif action == 'get':value = copy.deepcopy(self.values.get(target))
        else:
            if self.fail_delete:return json.dumps({'ok':False, 'value':None}).encode()
            self.values.pop(target, None); value = None
        return json.dumps({'ok':True, 'value':value}).encode()

    def call(self, action, body=None, app='new-app'):
        return json.loads(self.gateway.call(self.session, app, action, json.dumps(body or {}).encode()))

    def setup(self, **changes):
        body = dict(setup_body('posthog'), confirm_storage=True, **changes)
        with patch('mission_control.insights_transport.request', side_effect=copy.deepcopy(payloads()['posthog'])):
            return self.call('setup', body)

    def test_setup_refresh_tick_and_disconnect_real_sqlite(self):
        self.start(); result = self.setup(automatic=True)
        sid = result['source_id']; key = setup_body()['api_key']
        self.assertTrue(next(iter(self.values)).startswith('AppGrowthInsights/'))
        view = self.call('view'); self.assertEqual(view['sources'][0]['status'], 'CONNECTED')
        self.assertNotIn(key, json.dumps(view) + json.dumps(result))
        self.assertEqual(self.call('tick')['status'], 'IDLE')

        with connection(self.path) as db:db.execute('UPDATE insight_sources SET next_due=0 WHERE id=?', (sid,))
        with patch('mission_control.insights_transport.request', side_effect=copy.deepcopy(payloads()['posthog'])):
            self.assertEqual(self.call('tick')['status'], 'CONNECTED')
        with patch('mission_control.insights_transport.request', side_effect=copy.deepcopy(payloads()['posthog'])):
            self.assertEqual(self.call('refresh', {'id':sid,'confirm_read':True})['status'], 'CONNECTED')
        for file in self.path.parent.glob(self.path.name+'*'):self.assertNotIn(key.encode(), file.read_bytes())
        self.assertEqual(self.call('disconnect', {'id':sid,'version':1,'confirm_disconnect':True})['status'], 'DISCONNECTED')
        self.assertEqual(self.values, {})
        self.assertEqual(self.call('tick')['status'], 'IDLE')

    def test_saved_provider_counts_reach_private_native_report_without_project_or_key(self):
        self.start()
        before=json.loads(self.runtime.report(self.session,'new-app'))
        self.setup()
        after=json.loads(self.runtime.report(self.session,'new-app'))
        self.assertNotEqual(before['sourceHash'],after['sourceHash'])
        provider=[row for row in after['rows'] if row['metric'].startswith('Provider posthog:')]
        self.assertGreater(len(provider),1)
        self.assertTrue(all('not transaction evidence or causal attribution' in row['evidence'] for row in provider))
        public=json.dumps(after)
        self.assertNotIn(setup_body()['api_key'],public)
        self.assertNotIn('project_id',public)
        self.assertNotIn('credential_ref',public)
        self.assertNotIn(self.principal,public)

    def test_invalid_scope_consent_and_no_desktop_vault_fallback(self):
        self.start()
        for changes in ({'confirm_storage':False}, {'confirm_read':False}, {'dedicated_project':False},
                        {'project_id':'../foreign'}, {'region':'evil'}, {'api_key':'phc_'+'x'*24}, {'provider':'revenuecat'}):
            with self.subTest(changes=changes), self.assertRaises(Invalid):
                self.call('setup', {**setup_body(), 'confirm_storage':True, **changes})
        with self.assertRaises(PermissionError):self.call('view', app='other')
        self.gateway = NativeInsights(self.runtime.service, self.runtime.identities, None)
        with patch('mission_control.insights.Vault', side_effect=AssertionError('desktop fallback')):
            with self.assertRaises(Invalid):self.call('setup', dict(setup_body(),confirm_storage=True))

    def test_failed_rotation_preserves_old_and_cleanup_failure_is_recorded(self):
        from mission_control.insights_transport import ProviderFailure
        self.start(); sid = self.setup()['source_id']; old = dict(self.values)
        replacement = dict(setup_body(), api_key='phx_'+'Z'*24, version=1, confirm_storage=True)
        with patch('mission_control.insights_transport.request', side_effect=ProviderFailure('NETWORK_ERROR','synthetic failure')):
            with self.assertRaises(Invalid):self.call('setup', replacement)
        self.assertEqual(self.values, old); self.assertEqual(self.call('view')['sources'][0]['version'],1)
        self.fail_delete = True
        with patch('mission_control.insights_transport.request', side_effect=ProviderFailure('NETWORK_ERROR','synthetic failure')):
            with self.assertRaises(Invalid):self.call('setup', replacement)
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM insight_cleanup').fetchone()[0],1)
        self.fail_delete = False
        self.assertEqual(self.call('disconnect', {'id':sid,'version':1,'confirm_disconnect':True})['status'],'DISCONNECTED')
        self.assertEqual(self.values,{})

    def test_wrong_project_and_stale_owner_cannot_commit_provider_observation(self):
        self.start()
        with patch('mission_control.insights_transport.request', return_value={'id':999}):
            with self.assertRaises(Invalid):self.call('setup', dict(setup_body(),confirm_storage=True))
        self.assertEqual(self.call('view')['sources'],[]); self.assertEqual(self.values,{})
        sid = self.setup()['source_id']
        def replace_during_read(url, token, body=None):
            if body is None:return {'id':123}
            self.generation = str(uuid4())
            return {'results':[['signup_completed',1]]}
        with patch('mission_control.insights_transport.request', side_effect=replace_during_read):
            with self.assertRaises(PermissionError):self.call('refresh', {'id':sid,'confirm_read':True})
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM insight_reports').fetchone()[0],1)

    def test_changed_connection_and_expired_lease_discard_read(self):
        self.start(); sid = self.setup()['source_id']
        for mutation in ('version', 'lease'):
            def mutate_during_read(url, token, body=None):
                if body is None:return {'id':123}
                with connection(self.path) as db:
                    if mutation == 'version':db.execute('UPDATE insight_sources SET version=version+1 WHERE id=?', (sid,))
                    else:db.execute('UPDATE insight_sources SET lease=0 WHERE id=?', (sid,))
                return {'results':[['signup_completed',1]]}
            with patch('mission_control.insights_transport.request', side_effect=mutate_during_read):
                self.assertEqual(self.call('refresh', {'id':sid,'confirm_read':True})['status'], 'OBSOLETE_RESULT_DISCARDED')
            with connection(self.path) as db:
                db.execute('UPDATE insight_sources SET lease=0 WHERE id=?', (sid,))
                self.assertEqual(db.execute('SELECT count(*) FROM insight_reports').fetchone()[0],1)

    def test_role_revocation_during_read_blocks_result_commit(self):
        from concurrent.futures import ThreadPoolExecutor
        self.start(); sid = self.setup()['source_id']
        def revoke():
            with connection(self.path) as db:
                db.execute("UPDATE operator_roles SET status='REVOKED' WHERE app_id='new-app'")
        def provider(url, token, body=None):
            if body is None:return {'id':123}
            with ThreadPoolExecutor(max_workers=1) as pool:pool.submit(revoke).result()
            return {'results':[['signup_completed',1]]}
        with patch('mission_control.insights_transport.request', side_effect=provider):
            with self.assertRaises(PermissionError):self.call('refresh', {'id':sid,'confirm_read':True})
        with connection(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM insight_reports').fetchone()[0],1)

    def test_keychain_write_failure_keeps_retryable_cleanup_reference(self):
        self.start(); original = self.gateway.vault_callback
        def fail_after_put(raw):
            body = json.loads(raw)
            result = original(raw)
            return json.dumps({'ok':False,'value':None}).encode() if body['action']=='put' else result
        self.gateway.vault_callback = fail_after_put
        with self.assertRaises(Invalid):self.call('setup', dict(setup_body(),confirm_storage=True))
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM insight_cleanup').fetchone()[0],1)
        self.gateway.vault_callback = original
        self.setup()
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM insight_cleanup').fetchone()[0],0)
        self.assertEqual(len(self.values),1)


if __name__ == '__main__':unittest.main()
