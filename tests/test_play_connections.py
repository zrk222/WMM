"""Synthetic consent, native-storage boundary and race tests; no live Google account used."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from mission_control import play_auth
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.play_connections import PlayConnections
from mission_control.play_contract import SCOPE
from mission_control.store import Store

CONFIG = dict(client_id='123-synthetic.apps.googleusercontent.com', client_secret='synthetic-client-value')


def grant_fixture():
    """Return a synthetic response object with the explicitly declared access duration."""
    return dict(access_token='synthetic-access-value', refresh_token='synthetic-refresh-value', scopes=[SCOPE], expires_in=3600)


GRANT = grant_fixture()


class MemoryVault:
    """Test-only protected-store boundary; this is never a production fallback."""
    def __init__(self):self.data = {}; self.fail_delete = False; self.fail_put = False
    def put(self, name, value):
        if self.fail_put:raise Invalid('Synthetic native storage failure')
        self.data[name] = copy.deepcopy(value)
    def get(self, name):return copy.deepcopy(self.data.get(name))
    def delete(self, name):
        if self.fail_delete:raise Invalid('Synthetic native storage locked')
        self.data.pop(name, None)


class OAuthProtocolTests(unittest.TestCase):
    def test_installed_config_rejects_wrong_client_and_external_endpoints(self):
        self.assertEqual(play_auth.installed_config(json.dumps({'installed': CONFIG})), CONFIG)
        for data in ({'web': CONFIG}, {'installed': dict(CONFIG, token_uri='https://evil.example/token')},
                     {'installed': dict(CONFIG, client_id='not-google')}, {'installed': []}):
            with self.assertRaises(Invalid):play_auth.installed_config(json.dumps(data))
        with self.assertRaises(Invalid):play_auth.installed_config('{"installed":{},"installed":{}}')

    def test_authorization_binds_actual_port_pkce_and_scope_without_secret(self):
        state, hashed, verifier = play_auth.fresh_state()
        uri = play_auth.authorization(CONFIG, 8766, state, verifier)
        query = parse_qs(urlsplit(uri).query)
        self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:8766'])
        self.assertEqual(query['scope'], [SCOPE]); self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['code_challenge'], [play_auth.challenge(verifier)])
        self.assertEqual(hashed, hashlib.sha256(state.encode()).hexdigest())
        self.assertNotIn(CONFIG['client_secret'], uri); self.assertNotIn(verifier, uri)
        for port in (True, 0, 65536):
            with self.assertRaises(Invalid):play_auth.authorization(CONFIG, port, state, verifier)

    def test_challenge_matches_rfc7636(self):
        self.assertEqual(play_auth.challenge('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'),
                         'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')

    def test_exchange_requires_reported_scope_refresh_and_expiry(self):
        payload = dict(GRANT, token_type='Bearer', scope=SCOPE)
        with patch.object(play_auth, 'token_request', return_value=payload) as call:
            value = play_auth.exchange(CONFIG, 'synthetic-code', 'v'*64, 8766)
        self.assertEqual(value, GRANT)
        self.assertEqual(call.call_args.args[0]['redirect_uri'], 'http://127.0.0.1:8766')
        for bad in ({**payload, 'scope': None}, {**payload, 'scope': SCOPE+' other'},
                    {**payload, 'expires_in': True}, {**payload, 'refresh_token': None}):
            with patch.object(play_auth, 'token_request', return_value=bad), self.assertRaises(Invalid):
                play_auth.exchange(CONFIG, 'synthetic-code', 'v'*64, 8766)

    def test_refresh_retains_verified_scope_and_rotates_grant(self):
        secret = dict(CONFIG, refresh_token=GRANT['refresh_token'], scopes=[SCOPE])
        response = dict(access_token='synthetic-new-access', refresh_token='synthetic-rotated-refresh', token_type='Bearer', expires_in=3600)
        with patch.object(play_auth, 'token_request', return_value=response):
            self.assertEqual(play_auth.refresh(secret)['refresh_token'], 'synthetic-rotated-refresh')
        with patch.object(play_auth, 'token_request') as call, self.assertRaises(Invalid):
            play_auth.refresh(dict(secret, scopes=['other']))
        call.assert_not_called()
        with patch.object(play_auth, 'token_request', return_value=dict(response, scope=42)), self.assertRaises(Invalid):
            play_auth.refresh(secret)

    def test_token_request_fixed_host_and_redacted_errors(self):
        with patch.object(play_auth, 'report_bytes', return_value=json.dumps(dict(GRANT, token_type='Bearer', scope=SCOPE)).encode()) as call:
            result = play_auth.token_request({'code': 'synthetic-code'})
        self.assertEqual(result['scope'], SCOPE)
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, 'https://oauth2.googleapis.com/token'); self.assertEqual(request.method, 'POST')
        for raw in (b'{"error":"synthetic-sensitive-value"}', b'not-json', b'x'*8193):
            with patch.object(play_auth, 'report_bytes', return_value=raw), self.assertRaises(Invalid) as error:
                play_auth.token_request({})
            self.assertNotIn('synthetic-sensitive-value', str(error.exception))

    def test_reader_rejects_foreign_host_package_track_and_query_before_credentials(self):
        selected = dict(package_name='com.example.synthetic', track='production')
        reader = play_auth.PlayReader(selected, GRANT['access_token'])
        base = 'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.example.synthetic'
        bad = ['https://evil.example/', base+'/tracks/internal/releases', base+'/subscriptions?pageSize=100&pageSize=100',
               base+'/subscriptions?pageSize=100&pageToken=https://evil.example', base+'/subscriptions?pageSize=100#token',
               base.replace('com.example.synthetic', 'com.example.foreign')+'/tracks/production/releases']
        for url in bad:
            with patch.object(play_auth, 'read_json') as call, self.assertRaises((Invalid, ValueError)):
                reader.read(url)
            call.assert_not_called()
        with patch.object(play_auth, 'read_json', return_value={}) as call:
            reader.read(base+'/subscriptions?pageSize=100&pageToken=next%2B%2F%3D')
        self.assertEqual(call.call_args.args[1]['Authorization'], 'Bearer '+GRANT['access_token'])


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'owner.sqlite', seed=False)
        for app in ('one', 'two'):
            self.store.save_app(app, dict(name='Synthetic '+app, job='Test', audience='Synthetic', activation='Saved', release='1', locale='en-US'))
        self.vault = MemoryVault(); self.mock_vault = patch('mission_control.play_connections.Vault', return_value=self.vault)
        self.mock_vault.start(); self.addCleanup(self.mock_vault.stop)
        self.exchange = patch.object(play_auth, 'exchange', return_value=copy.deepcopy(GRANT)).start()
        self.addCleanup(patch.stopall)
        self.provider = patch.object(play_auth.PlayReader, 'read', return_value={}).start()
        self.service = PlayConnections(self.store, 8766)

    def body(self, app='one', client_json=None):
        records = [r for r in self.store.records(app) if r['kind']=='connection' and r['data']['provider']=='google_play']
        old = records[0] if records else None
        return dict(client_json=json.dumps({'installed': CONFIG}) if client_json is None else client_json,
                    package_name='com.example.synthetic', track='production', manifest_version=self.store.app(app)['version'],
                    connection_id=old['id'] if old else None, connection_version=old['version'] if old else 0, confirm_read=True)

    def start(self, app='one', **changes):
        result = self.service.start(app, dict(self.body(app), **changes))
        state = parse_qs(urlsplit(result['authorization_url']).query)['state'][0]
        return result, state

    def connected(self):
        result, state = self.start(); self.service.finish(dict(state=state, code='synthetic-code'))
        return self.store.records('one')[0]

    def test_consent_state_and_secrets_are_not_stored_in_sqlite_or_status(self):
        flow, state = self.start()
        with connection(self.store.path) as db:
            row = dict(db.execute('SELECT * FROM play_flows').fetchone())
        self.assertNotIn(state, json.dumps(row)); self.assertEqual(row['state_hash'], hashlib.sha256(state.encode()).hexdigest())
        public = json.dumps(self.service.status('one'))
        for secret in (state, CONFIG['client_secret'], 'verifier', 'secret_ref'):self.assertNotIn(secret, public)
        self.assertEqual(len(self.vault.data), 1); self.assertEqual(flow['package_name'], 'com.example.synthetic')

    def test_verified_connection_survives_service_restart_without_exporting_tokens(self):
        flow, state = self.start(); restarted = PlayConnections(self.store, 8766)
        result = restarted.finish(dict(state=state, code='synthetic-code'))
        self.assertEqual(result['status'], 'CONNECTED'); self.assertEqual(len(self.vault.data), 1)
        record = self.store.records('one')[0]
        self.assertEqual(record['data']['auth_mode'], 'managed_oauth')
        self.assertEqual(record['data']['scopes'], [SCOPE]); self.assertEqual(record['data']['package_name'], 'com.example.synthetic')
        self.assertEqual(self.store.app('one')['data']['android_package'], 'com.example.synthetic')
        self.assertEqual(self.store.app('one')['data']['android_track'], 'production')
        self.assertEqual(self.store.app('one')['version'], 2)
        text = json.dumps([self.store.records('one'), restarted.status('one')])
        for value in (GRANT['access_token'], GRANT['refresh_token'], CONFIG['client_secret']):self.assertNotIn(value, text)

    def test_callback_replay_and_foreign_flow_are_denied(self):
        result, state = self.start(); self.service.finish(dict(state=state, code='synthetic-code'))
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, code='synthetic-code'))
        with self.assertRaises(Invalid):self.service.flow('two', result['flow_id'])
        self.assertEqual(self.exchange.call_count, 1)

    def test_cancel_before_callback_and_during_exchange_preserves_prior_connection(self):
        old = self.connected(); flow, state = self.start()
        self.service.stop('one', flow['flow_id'])
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, code='synthetic-code'))
        flow, state = self.start()
        def cancelled(*args):
            self.service.stop('one', flow['flow_id']); return copy.deepcopy(GRANT)
        self.exchange.side_effect = cancelled
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, code='synthetic-code'))
        self.assertEqual(self.store.records('one')[0], old); self.assertEqual(len(self.vault.data), 1)

    def test_failed_provider_read_preserves_old_binding_and_secret(self):
        old = self.connected(); _, state = self.start(); self.provider.side_effect = Invalid('Synthetic permission denied; reconnect')
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, code='synthetic-code'))
        self.assertEqual(self.store.records('one')[0], old)
        self.assertEqual(len(self.vault.data), 1); self.assertEqual(self.service.status('one')['flows'][0]['status'], 'FAILED')

    def test_cancel_at_final_commit_retires_candidate_and_preserves_old_binding(self):
        old = self.connected(); flow, state = self.start(); original = self.service.commit
        def cancel(row, reference, report):
            self.service.stop('one', flow['flow_id']); return original(row, reference, report)
        with patch.object(self.service, 'commit', side_effect=cancel), self.assertRaises(Invalid):
            self.service.finish(dict(state=state, code='synthetic-code'))
        self.assertEqual(self.store.records('one')[0], old); self.assertEqual(len(self.vault.data), 1)

    def test_cleanup_error_after_commit_reports_connected_with_durable_retirements(self):
        old = self.connected(); _, state = self.start()
        with patch.object(self.service, 'retire', side_effect=OSError('Synthetic cleanup failure')):
            result = self.service.finish(dict(state=state, code='synthetic-code'))
        self.assertEqual(result['status'], 'CONNECTED'); self.assertEqual(result['cleanup'], 'LOCAL_CLEANUP_PENDING')
        self.assertEqual(self.store.records('one')[0]['version'], old['version'] + 1)
        self.assertEqual(self.service.status('one')['flows'][0]['status'], 'CONNECTED')
        self.assertEqual(self.service.status('one')['cleanup_pending'], 2)
        self.assertEqual(self.service.cleanup('one')['status'], 'CLEAN'); self.assertEqual(len(self.vault.data), 1)

    def test_manifest_and_listener_changes_reject_before_exchange(self):
        flow, state = self.start(); changed = self.store.app('one')
        self.store.save_app('one', dict(changed['data'], job='Changed'), changed['version'])
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, code='synthetic-code'))
        self.exchange.assert_not_called()
        _, state = self.start()
        with self.assertRaises(Invalid):PlayConnections(self.store, 8767).finish(dict(state=state, code='synthetic-code'))
        self.exchange.assert_not_called()

    def test_expiry_is_not_automatically_replayed_and_unconfirmed_exchange_is_visible(self):
        flow, state = self.start(); self.service.claim(state)
        with connection(self.store.path) as db:db.execute('UPDATE play_flows SET expires=0 WHERE id=?', (flow['flow_id'],))
        self.service.expire('one')
        self.assertEqual(self.service.status('one')['flows'][0]['status'], 'UNCONFIRMED')
        self.assertEqual(len(self.vault.data), 0); self.exchange.assert_not_called()

    def test_native_failure_and_wrong_source_never_replace_connection(self):
        old = self.connected(); self.vault.fail_put = True
        with self.assertRaises(Invalid):self.start()
        self.assertEqual(self.store.records('one')[0], old)
        self.vault.fail_put = False
        for changes in ({'confirm_read': False}, {'connection_version': True}, {'connection_id': 'foreign'}, {'publish': True}):
            with self.subTest(changes=changes), self.assertRaises(Invalid):self.start(**changes)

    def test_reconnect_reuses_only_app_owned_protected_client(self):
        self.connected(); flow, state = self.start(client_json='')
        self.assertEqual(self.service.finish(dict(state=state, code='synthetic-code'))['status'], 'CONNECTED')
        with self.assertRaises(Invalid):self.start('two', client_json='')
        self.assertEqual(len(self.vault.data), 1)

    def test_cleanup_failure_stays_visible_until_native_storage_recovers(self):
        flow, _ = self.start(); self.vault.fail_delete = True
        self.service.stop('one', flow['flow_id'])
        self.assertEqual(self.service.status('one')['cleanup_pending'], 1)
        self.assertEqual(self.service.cleanup('one')['status'], 'LOCAL_CLEANUP_PENDING')
        self.vault.fail_delete = False
        self.assertEqual(self.service.cleanup('one')['status'], 'CLEAN'); self.assertEqual(len(self.vault.data), 0)

    def test_crashed_secret_staging_has_durable_delayed_retirement(self):
        from mission_control.common import uid
        reference = uid(); self.service.stage_secret('one', reference, dict(synthetic='candidate'))
        self.assertEqual(self.service.cleanup('one')['attempted'], 0)
        with connection(self.store.path) as db:db.execute('UPDATE play_retirements SET eligible=0')
        self.assertEqual(self.service.cleanup('one')['attempted'], 1); self.assertEqual(len(self.vault.data), 0)

    def test_cleanup_batch_never_claims_clean_while_retirements_remain(self):
        from mission_control.common import uid
        for _ in range(21):self.service.stage_secret('one', uid(), dict(synthetic='candidate'))
        with connection(self.store.path) as db:db.execute('UPDATE play_retirements SET eligible=0')
        first = self.service.cleanup('one')
        self.assertEqual(first, dict(status='LOCAL_CLEANUP_PENDING', attempted=20, remaining=1))
        self.assertEqual(self.service.cleanup('one'), dict(status='CLEAN', attempted=1, remaining=0))

    def test_candidate_scope_and_protected_target_tampering_fail_closed(self):
        flow, state = self.start()
        with connection(self.store.path) as db:
            row = db.execute('SELECT config FROM play_flows WHERE id=?', (flow['flow_id'],)).fetchone()
            value = json.loads(row[0]); value['package_name'] = 'com.other.foreign'
            db.execute('UPDATE play_flows SET config=? WHERE id=?', (json.dumps(value), flow['flow_id']))
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, code='synthetic-code'))
        self.exchange.assert_not_called(); self.assertEqual(self.store.records('one'), [])

    def test_denied_consent_never_calls_token_endpoint(self):
        flow, state = self.start()
        with self.assertRaises(Invalid):self.service.finish(dict(state=state, error='access_denied'))
        self.exchange.assert_not_called(); self.assertEqual(self.store.records('one'), [])


if __name__ == '__main__':unittest.main()
