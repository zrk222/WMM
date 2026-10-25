"""Actual loopback owner Drive requests with synthetic provider and protected vault."""
import json
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from mission_control import drive_auth
from mission_control.drive_account_contract import identity
from mission_control.drive_http import empty, route
from mission_control.db import connection
from mission_control.operator_client import OperatorClient
from mission_control.common import Invalid
from tests import test_managed_media_http as media_http
APP = media_http.APP
from tests.test_drive_auth import CONFIG, PAYLOAD
from tests.test_drive_accounts import USER
from tests.test_measurement_connectors import FakeVault


class DriveHTTPTests(unittest.TestCase):
    send = media_http.MediaHTTPTests.send
    tearDown = media_http.MediaHTTPTests.tearDown
    def setUp(self):
        media_http.MediaHTTPTests.setUp(self); self.base = '/api/apps/' + APP + '/drive'
        FakeVault.values = {}; FakeVault.fail_delete = 0
        vault = patch('mission_control.drive_secrets.Vault', FakeVault)
        vault.start(); self.addCleanup(vault.stop)
        self.exchange = patch.object(drive_auth, 'exchange', return_value=drive_auth.grant(PAYLOAD))
        self.exchange_mock = self.exchange.start(); self.addCleanup(self.exchange.stop)
        account = patch('mission_control.drive_accounts.read_account', return_value=identity(USER))
        self.account = account.start(); self.addCleanup(account.stop)

    def start(self):
        value = dict(client_json=json.dumps(dict(installed=CONFIG)), manifest_version=1,
                     connection_id=None, connection_version=0, confirm_scope=True)
        code, raw, _ = self.send('POST', self.base + '/start', json.dumps(value).encode(), {'Content-Type':'application/json'})
        self.assertEqual(code, 201, raw); result = json.loads(raw)
        state = parse_qs(urlsplit(result['authorization_url']).query)['state'][0]
        query = urlencode(dict(state=state, code='synthetic-code', scope=drive_auth.SCOPE, picked_file_ids='clip_red'))
        return result, query

    def candidate(self):
        flow, query = self.start()
        review = self.client.request('POST', self.base + '/callback', dict(query=query))
        self.assertEqual(review['id'], flow['flow_id']); return review

    def adopt(self):
        review = self.candidate()
        self.assertEqual(self.client.request('GET', self.base + '/flows/' + review['id'])['packet_hash'], review['packet_hash'])
        return self.client.request('POST', self.base + '/flows/' + review['id'] + '/confirm',
                                   dict(packet_hash=review['packet_hash'], confirm_account=True))

    def test_lifecycle_and_durable_job_routes_are_private_and_do_not_download(self):
        self.assertEqual(self.client.request('GET', self.base)['connection']['status'], 'SETUP_REQUIRED')
        current = self.adopt(); self.assertEqual(current['status'], 'CONNECTED')
        value = dict(connection_id=current['id'], connection_version=current['version'], file_id='clip_red', manifest_version=1, request_key='http-import-one')
        with patch('mission_control.drive_media.Importer.import_file', side_effect=AssertionError('HTTP must only queue')):
            code, raw, _ = self.send('POST', self.base + '/imports', json.dumps(value).encode(), {'Content-Type':'application/json'})
        self.assertEqual(code, 201, raw); job = json.loads(raw)
        self.assertEqual(job['status'], 'QUEUED'); self.assertIsNone(job['progress_percent'])
        self.assertEqual(self.client.request('POST', self.base + '/imports', value)['id'], job['id'])
        self.assertEqual(self.client.request('GET', self.base + '/imports/' + job['id'])['selection']['file_id'], 'clip_red')
        self.assertNotIn(job['id'], json.dumps(self.client.request('GET', '/api/apps/' + APP + '/jobs')))
        canceled = self.client.request('POST', self.base + '/imports/' + job['id'] + '/cancel', {})
        self.assertEqual(canceled['status'], 'CANCELLED')
        self.assertEqual(self.client.request('POST', self.base + '/disconnect', dict(connection_id=current['id'], version=current['version'], confirm_disconnect=True))['status'], 'DISCONNECTED')
        self.client.request('POST', self.base + '/cleanup', {})
        self.assertEqual(self.exchange_mock.call_count, 1)
        text = json.dumps(self.client.request('GET', self.base))
        for field in ('access_token', 'refresh_token', 'client_secret', 'secret_ref', 'verifier'):
            self.assertNotIn(field, text)

    def test_cross_app_callback_is_rejected_before_claim_or_exchange(self):
        self.store.save_app('other-app', dict(name='Other synthetic app', release='one', locale='en-US'))
        self.client.request('POST', '/api/apps/other-app/access/bootstrap', dict(confirm_owner=True))
        flow, query = self.start()
        code, _, _ = self.send('POST', '/api/apps/other-app/drive/callback', json.dumps(dict(query=query)).encode(), {'Content-Type':'application/json'})
        self.assertEqual(code, 400); self.exchange_mock.assert_not_called()
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT status FROM drive_flows WHERE id=?', (flow['flow_id'],)).fetchone()[0], 'PENDING')
        self.client.request('POST', self.base + '/callback', dict(query=query)); self.exchange_mock.assert_called_once()

    def test_cancel_and_exact_empty_action_reject_extra_authority(self):
        flow, _ = self.start(); path = self.base + '/flows/' + flow['flow_id'] + '/cancel'
        code, _, _ = self.send('POST', path, b'{"principal":"forged"}', {'Content-Type':'application/json'})
        self.assertEqual(code, 400)
        self.assertEqual(self.client.request('POST', path, {})['status'], 'CANCELLED')
        for value in ({'extra':True}, [], None):
            with self.assertRaises(Invalid):empty(value)
        empty({})

    def test_owner_and_framing_rejections_never_exchange(self):
        anonymous = OperatorClient(self.origin); anonymous.bootstrap()
        self.assertEqual(self.send('GET', self.base, client=anonymous)[0], 403)
        for suffix in ('/', '?extra=1', '//imports', '/unknown'):
            self.assertNotEqual(self.send('GET', self.base + suffix)[0], 200)
        for raw in (b'[]', b'{"query":"x","query":"y"}', b'{' + b'x' * 16384):
            self.assertEqual(self.send('POST', self.base + '/callback', raw, {'Content-Type':'application/json'})[0], 400)
        for headers in ({'Origin':'https://other.example'}, {'X-CSRF-Token':'wrong'}, {'Host':'localhost:' + str(self.server.server_port)}):
            self.assertEqual(self.send('POST', self.base + '/start', b'{}', dict({'Content-Type':'application/json'}, **headers))[0], 403)
        self.exchange_mock.assert_not_called()

    def test_revoked_owner_during_account_read_cannot_attach_candidate(self):
        flow, query = self.start()
        def revoke(token):
            def write():
                with connection(self.store.path) as db:
                    db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", (APP,))
            thread = threading.Thread(target=write); thread.start(); thread.join(); return identity(USER)
        self.account.side_effect = revoke
        code, raw, _ = self.send('POST', self.base + '/callback', json.dumps(dict(query=query)).encode(), {'Content-Type':'application/json'})
        self.assertEqual(code, 403, raw)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM drive_connections').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT status FROM drive_flows WHERE id=?', (flow['flow_id'],)).fetchone()[0], 'EXCHANGING')

    def test_route_and_empty_have_explicit_non_hollow_contracts(self):
        parts = ['api', 'apps', APP, 'drive']
        route(SimpleNamespace(path='/' + '/'.join(parts)), parts)
        for path in ('/api/apps/' + APP + '/drive/', '/api/apps/' + APP + '/drive?query=1'):
            with self.assertRaises(Invalid):route(SimpleNamespace(path=path), parts)
        with self.assertRaises(Invalid):route(SimpleNamespace(path='/'), ['bad'])
        with self.assertRaises(Invalid):empty({'extra':1})

    def test_duplicate_callback_keys_do_not_consume_valid_flow(self):
        flow, query = self.start(); encoded = json.dumps(query)
        raw = ('{"query":' + encoded + ',"query":' + encoded + '}').encode()
        self.assertEqual(self.send('POST', self.base + '/callback', raw, {'Content-Type':'application/json'})[0], 400)
        self.exchange_mock.assert_not_called()
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT status FROM drive_flows WHERE id=?', (flow['flow_id'],)).fetchone()[0], 'PENDING')
        self.client.request('POST', self.base + '/callback', dict(query=query))
