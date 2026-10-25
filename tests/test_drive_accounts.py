"""Durable account candidate/adoption with synthetic Google responses and native store."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit
from mission_control import drive_accounts as accounts
from mission_control import drive_account_contract as contract
from mission_control import drive_auth
from mission_control.drive_connection_state import Connections
from mission_control.common import Invalid, canonical
from mission_control.db import connection
from mission_control.store import Store
from tests.test_drive_auth import CONFIG, PAYLOAD
from tests.test_measurement_connectors import FakeVault

USER = dict(user=dict(permissionId='synthetic-account-one',displayName='Synthetic Owner',emailAddress='owner@example.test',me=True,kind='drive#user'))


class DriveAccountTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'synthetic.sqlite3');self.accounts=accounts.Accounts(self.store,8768)
        self.connections=Connections(self.store,8768);FakeVault.values={};FakeVault.fail_delete=0
        fake=patch('mission_control.drive_secrets.Vault',FakeVault);fake.start();self.addCleanup(fake.stop)

    def start(self):
        prior=self.connections.row('sample-one')
        body=dict(client_json=json.dumps(dict(installed=CONFIG)),manifest_version=self.store.app('sample-one')['version'],
                  connection_id=prior['id']if prior else None,connection_version=prior['version']if prior else 0,confirm_scope=True)
        result=self.accounts.flows.start('sample-one',body)
        state=parse_qs(urlsplit(result['authorization_url']).query)['state'][0]
        return result,urlencode(dict(state=state,code='synthetic-code',scope=drive_auth.SCOPE,picked_file_ids='clip_red,clip_blue'))

    def candidate(self,user=None):
        flow,query=self.start()
        with patch.object(drive_auth,'exchange',return_value=drive_auth.grant(PAYLOAD))as exchange, \
             patch.object(accounts,'read_account',return_value=contract.identity(user or USER))as read:
            review=self.accounts.finish(query)
        exchange.assert_called_once();read.assert_called_once()
        self.assertEqual(review['id'],flow['flow_id'])
        return review

    def adopt(self,user=None):
        review=self.candidate(user)
        return self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))

    def test_identity_requires_requesting_user_and_safe_stable_permission_identity(self):
        expected=dict(permission_id='synthetic-account-one',display_name='Synthetic Owner',email='owner@example.test')
        self.assertEqual(contract.identity(USER),expected)
        self.assertEqual(contract.identity({'user':dict(permissionId='id_one',me=True,kind='drive#user')}),{'permission_id':'id_one'})
        for value in (None,[],{},dict(USER,extra=1),{'user':[]},
                      {'user':{**USER['user'],'permissionId':'../foreign'}},
                      {'user':{**USER['user'],'me':False}}, {'user':{**USER['user'],'kind':'other'}},
                      {'user':{**USER['user'],'displayName':'bad\nname'}}):
            with self.subTest(value=value),self.assertRaises(Invalid):contract.identity(value)

    def test_account_read_uses_fixed_projected_get_and_bounded_redacted_transport(self):
        with patch.object(accounts,'report_bytes',return_value=json.dumps(USER).encode())as call:
            result=accounts.read_account('synthetic-token')
        self.assertEqual(result['permission_id'],'synthetic-account-one');call.assert_called_once()
        request,timeout=call.call_args.args
        self.assertEqual(request.full_url,accounts.ACCOUNT_ENDPOINT);self.assertEqual(request.get_method(),'GET')
        self.assertEqual(request.get_header('Authorization'),'Bearer synthetic-token');self.assertEqual(timeout,15)
        for raw in (b'x'*8193,b'{"user":{},"user":{}}',b'null',b'\xff',b'['*1500):
            with self.subTest(raw=raw[:30]),patch.object(accounts,'report_bytes',return_value=raw),self.assertRaises(Invalid):accounts.read_account('synthetic-token')
        with patch.object(accounts,'report_bytes',side_effect=Invalid('private-provider-detail')),self.assertRaises(Invalid)as failure:accounts.read_account('synthetic-token')
        self.assertNotIn('private-provider-detail',str(failure.exception))

    def test_candidate_requires_explicit_account_confirmation_and_redacts_protected_values(self):
        review=self.candidate()
        self.assertEqual(review['account']['permission_id'],'synthetic-account-one')
        self.assertEqual(review['selected_files'],['clip_red','clip_blue']);self.assertEqual(review['reuse_permission'],'NOT_GRANTED')
        self.assertEqual(self.connections.status('sample-one')['status'],'SETUP_REQUIRED')
        row=self.accounts.flows.flow('sample-one',review['id']);self.assertEqual(row['status'],'AWAITING_ACCOUNT')
        self.assertEqual(accounts.Accounts(Store(self.store.path),8768).review('sample-one',review['id']),review)
        secret=self.accounts.secrets.load('sample-one',row['secret_ref'],accounts.binding(row))
        self.assertNotIn('verifier',secret)
        with connection(self.store.path)as db:sql=''.join(str(tuple(r))for r in db.execute('SELECT * FROM drive_flows'))
        for private in (CONFIG['client_secret'],PAYLOAD['access_token'],PAYLOAD['refresh_token']):
            self.assertNotIn(private,sql+canonical(review)+canonical(self.store.export('sample-one')))

    def test_confirm_commits_bound_connection_and_retires_candidate_without_code_replay(self):
        review=self.candidate();status=self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))
        self.assertEqual(status['status'],'CONNECTED');self.assertEqual(status['version'],1)
        row=self.connections.row('sample-one');secret=self.accounts.secrets.load('sample-one',row['secret_ref'],contract.connection_binding(row))
        self.assertEqual(secret['access_token'],PAYLOAD['access_token']);self.assertEqual(len(FakeVault.values),5)
        self.assertEqual(self.accounts.flows.flow('sample-one',review['id'])['status'],'CONFIRMED')
        with self.assertRaises(Invalid):self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))
        self.assertEqual(self.connections.status('sample-one')['status'],'CONNECTED')

    def test_wrong_packet_missing_confirmation_foreign_app_and_expiry_deny_adoption(self):
        review=self.candidate()
        for body in ({'packet_hash':'a'*64,'confirm_account':True},{'packet_hash':review['packet_hash'],'confirm_account':False},
                     {'packet_hash':review['packet_hash'],'confirm_account':True,'override':True}):
            with self.subTest(body=body),self.assertRaises(Invalid):self.accounts.confirm('sample-one',review['id'],body)
        with self.assertRaises(Invalid):self.accounts.review('sample-two',review['id'])
        with patch('mission_control.drive_account_contract.time.time',return_value=review['access_expires']+1),self.assertRaises(Invalid):self.accounts.review('sample-one',review['id'])
        self.assertEqual(self.connections.status('sample-one')['status'],'SETUP_REQUIRED')

    def test_replacement_requires_explicit_new_account_packet_and_preserves_old_until_commit(self):
        first=self.adopt();before=self.connections.row('sample-one');old_ref=before['secret_ref']
        alternate=dict(user={**USER['user'],'permissionId':'synthetic-account-two','emailAddress':'two@example.test'})
        review=self.candidate(alternate)
        self.assertEqual(self.connections.status('sample-one')['account']['permission_id'],'synthetic-account-one')
        second=self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))
        self.assertEqual(second['id'],first['id']);self.assertEqual(second['version'],2)
        self.assertEqual(second['account']['permission_id'],'synthetic-account-two')
        with self.assertRaises(Invalid):self.accounts.secrets.load('sample-one',old_ref,contract.connection_binding(before))
        self.assertEqual(len(FakeVault.values),5)

    def test_exchange_or_account_read_failure_preserves_prior_connection_and_never_replays_code(self):
        first=self.adopt()
        for failed_step in ('exchange','read_account'):
            flow,query=self.start()
            with patch.object(drive_auth,'exchange',return_value=drive_auth.grant(PAYLOAD))as exchange, \
                 patch.object(accounts,'read_account',return_value=contract.identity(USER))as read:
                (exchange if failed_step=='exchange'else read).side_effect=Invalid('synthetic-private-error')
                with self.assertRaises(Invalid)as failure:self.accounts.finish(query)
                self.assertNotIn('synthetic-private-error',str(failure.exception));exchange.assert_called_once()
                with self.assertRaises(Invalid):self.accounts.finish(query)
                exchange.assert_called_once()
            self.assertEqual(self.accounts.flows.flow('sample-one',flow['flow_id'])['status'],'UNCONFIRMED')
            self.assertEqual(self.connections.status('sample-one')['id'],first['id']);self.assertEqual(len(FakeVault.values),5)

    def test_cancellation_during_account_read_prevents_attachment_and_preserves_connection(self):
        first=self.adopt();flow,query=self.start()
        def cancel(_):
            self.accounts.flows.stop('sample-one',flow['flow_id'])
            return contract.identity(USER)
        with patch.object(drive_auth,'exchange',return_value=drive_auth.grant(PAYLOAD)),patch.object(accounts,'read_account',side_effect=cancel),self.assertRaises(Invalid):self.accounts.finish(query)
        self.assertEqual(self.accounts.flows.flow('sample-one',flow['flow_id'])['status'],'CANCELLED')
        self.assertEqual(self.connections.status('sample-one')['id'],first['id']);self.assertEqual(len(FakeVault.values),5)

    def test_stale_manifest_and_disconnect_during_confirmation_cannot_adopt(self):
        first=self.adopt();review=self.candidate();original=self.accounts.adopt
        def disconnect(row,candidate,ref,expected):
            self.connections.disconnect('sample-one',dict(connection_id=first['id'],version=first['version'],confirm_disconnect=True))
            return original(row,candidate,ref,expected)
        with patch.object(self.accounts,'adopt',side_effect=disconnect),self.assertRaises(Invalid):
            self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))
        self.assertEqual(self.connections.status('sample-one')['status'],'DISCONNECTED');self.assertFalse(FakeVault.values)
        review=self.candidate();app=self.store.app('sample-one');self.store.save_app('sample-one',app['data'],app['version'])
        with self.assertRaises(Invalid):self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))

    def test_disconnect_requires_exact_revision_cancels_pending_and_removes_local_fields(self):
        status=self.adopt();flow,query=self.start()
        for body in (dict(connection_id=status['id'],version=True,confirm_disconnect=True),
                     dict(connection_id=status['id'],version=0,confirm_disconnect=True),
                     dict(connection_id=status['id'],version=1,confirm_disconnect=False)):
            with self.subTest(body=body),self.assertRaises(Invalid):self.connections.disconnect('sample-one',body)
        result=self.connections.disconnect('sample-one',dict(connection_id=status['id'],version=1,confirm_disconnect=True))
        self.assertEqual(result['status'],'DISCONNECTED');self.assertEqual(result['provider_revocation'],'NOT_PERFORMED')
        self.assertEqual(result['imported_media'],'PRESERVED');self.assertFalse(FakeVault.values)
        self.assertEqual(self.accounts.flows.flow('sample-one',flow['flow_id'])['status'],'CANCELLED')
        with self.assertRaises(Invalid):self.accounts.finish(query)

    def test_status_distinguishes_expiry_missing_secret_and_changed_manifest(self):
        self.assertEqual(self.connections.status('sample-one')['status'],'SETUP_REQUIRED')
        self.adopt();row=self.connections.row('sample-one')
        with patch('mission_control.drive_connection_state.time.time',return_value=row['expires']+1):
            self.assertEqual(self.connections.status('sample-one')['status'],'ACCESS_EXPIRED')
        app=self.store.app('sample-one');self.store.save_app('sample-one',app['data'],app['version'])
        self.assertEqual(self.connections.status('sample-one')['status'],'APP_REVIEW_REQUIRED')
        with connection(self.store.path)as db:db.execute('UPDATE apps SET version=version-1 WHERE id=?',('sample-one',))
        FakeVault.values={};self.assertEqual(self.connections.status('sample-one')['status'],'RECONNECT_REQUIRED')

    def test_declined_consent_does_not_exchange_code_or_replace_account(self):
        first=self.adopt();flow,query=self.start();fields=parse_qs(query)
        query=urlencode(dict(state=fields['state'][0],error='access_denied'))
        with patch.object(drive_auth,'exchange')as exchange:
            self.assertEqual(self.accounts.finish(query)['status'],'CANCELLED')
        exchange.assert_not_called();self.assertEqual(self.connections.status('sample-one')['id'],first['id'])

    def test_canceled_current_claim_cannot_save_candidate_even_with_existing_protected_reference(self):
        flow,query=self.start();state=parse_qs(query)['state'][0];row=self.accounts.flows.claim(state)
        with connection(self.store.path)as db:self.accounts.current_claim(db,row)
        self.accounts.flows.stop('sample-one',row['id'])
        with connection(self.store.path)as db,self.assertRaises(Invalid):self.accounts.current_claim(db,row)
        with self.assertRaises(Invalid):self.accounts.save_candidate(row,row,row['secret_ref'])
        self.assertFalse(FakeVault.values)

    def test_new_connection_binding_changes_for_account_selection_and_revision(self):
        review=self.candidate();row=self.accounts.flows.flow('sample-one',review['id'])
        result=self.accounts.new_connection(row)
        self.assertEqual(result['version'],1);self.assertEqual(result['data']['selected_files'],['clip_red','clip_blue'])
        digest=contract.connection_binding(result)
        self.assertNotEqual(digest,contract.connection_binding(dict(result,version=2)))
        self.assertNotEqual(digest,contract.connection_binding(dict(result,data={**result['data'],'selected_files':['clip_blue']})))

    def test_disconnect_with_persistently_locked_native_store_disables_access_and_preserves_cleanup(self):
        status=self.adopt()
        with patch.object(FakeVault,'delete',side_effect=Invalid('Synthetic locked native store')):
            result=self.connections.disconnect('sample-one',dict(connection_id=status['id'],version=status['version'],confirm_disconnect=True))
        self.assertEqual(result['status'],'DISCONNECTED');self.assertEqual(result['cleanup']['remaining'],1)
        self.assertEqual(self.connections.status('sample-one')['status'],'DISCONNECTED')
        self.assertEqual(self.connections.cleanup_result('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)

    def test_account_status_rejects_connection_changed_during_protected_read(self):
        self.adopt();original=self.connections.readiness
        def replaced(row):
            result=original(row)
            with connection(self.store.path)as db:db.execute('UPDATE drive_connections SET version=version+1')
            return result
        with patch.object(self.connections,'readiness',side_effect=replaced),self.assertRaisesRegex(Invalid,'changed during'):self.connections.status('sample-one')

    def test_candidate_access_expiry_is_shorter_than_live_consent_and_blocks_confirmation(self):
        flow,query=self.start()
        grant=drive_auth.grant(dict(PAYLOAD,expires_in=1))
        with patch.object(drive_auth,'exchange',return_value=grant),patch.object(accounts,'read_account',return_value=contract.identity(USER)):
            review=self.accounts.finish(query)
        self.assertLess(review['access_expires'],review['expires'])
        clock=type('Clock',(),{'time':staticmethod(lambda:review['access_expires']+1)})
        with patch.object(contract,'time',clock),self.assertRaisesRegex(Invalid,'access expired'):
            self.accounts.confirm('sample-one',review['id'],dict(packet_hash=review['packet_hash'],confirm_account=True))
        self.assertEqual(self.connections.status('sample-one')['status'],'SETUP_REQUIRED')
