"""Real durable Drive consent state and synthetic protected-store races; no provider calls."""
import hashlib
import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from mission_control import drive_flow_contract as contract
from mission_control.common import Invalid, canonical, now, uid
from mission_control.db import connection
from mission_control.drive_flows import Flows
from mission_control.store import Store
from tests.test_measurement_connectors import FakeVault
from tests.test_drive_auth import CONFIG


class DriveFlowTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'synthetic.sqlite3');self.flows=Flows(self.store,8768)
        FakeVault.values={};FakeVault.fail_delete=0
        fake=patch('mission_control.drive_secrets.Vault',FakeVault);fake.start();self.addCleanup(fake.stop)

    def body(self,app='sample-one'):
        with connection(self.store.path)as db:old=db.execute('SELECT id,version FROM drive_connections WHERE app_id=?',(app,)).fetchone()
        return dict(client_json=json.dumps(dict(installed=CONFIG)),manifest_version=self.store.app(app)['version'],
                    connection_id=old['id']if old else None,connection_version=old['version']if old else 0,confirm_scope=True)

    def start(self,app='sample-one'):
        result=self.flows.start(app,self.body(app))
        state=parse_qs(urlsplit(result['authorization_url']).query)['state'][0]
        return result,state

    def prior_connection(self):
        values=dict(binding='b'*64,access_token='synthetic-prior-token')
        ref=self.flows.secrets.stage('sample-one',values);identity=uid()
        with connection(self.store.path)as db:
            db.execute('BEGIN IMMEDIATE');self.flows.secrets.activate(db,'sample-one',ref,'b'*64,['access_token'])
            db.execute('INSERT INTO drive_connections VALUES(?,?,?,?,?,?,?,?,?)',
                       ('sample-one',identity,3,'{}',ref,'CONNECTED',time.time()+3600,now(),now()))
        return identity,ref

    def test_pending_start_persist_and_redacted_status_survive_restart(self):
        started=time.time();result,state=self.start();row=self.flows.flow('sample-one',result['flow_id'])
        self.assertGreaterEqual(row['expires'],started+600);self.assertLess(row['expires'],time.time()+601)
        self.assertEqual(row['status'],'PENDING');self.assertEqual(row['state_hash'],hashlib.sha256(state.encode()).hexdigest())
        status=Flows(Store(self.store.path),8768).status('sample-one')
        self.assertEqual(status['flows'][0]['id'],result['flow_id'])
        self.assertEqual(status['scope_of_result'],'CONSENT_PROGRESS_ONLY');self.assertEqual(status['connected_account'],'NOT_ASSESSED')
        self.assertIn('modification permission',status['permission_summary']);self.assertIn('provider reads only',status['permission_summary'])
        self.assertEqual(status['cleanup_pending'],0)
        raw=canonical(status)+canonical(self.store.export('sample-one'))
        for value in (state,row['state_hash'],row['secret_ref'],CONFIG['client_secret'],CONFIG['client_id']):self.assertNotIn(value,raw)
        with connection(self.store.path)as db:
            sql=''.join(str(tuple(r))for r in db.execute('SELECT * FROM drive_flows'))
        self.assertNotIn(CONFIG['client_secret'],sql);self.assertNotIn(state,sql)

    def test_claim_once_pending_binding_and_original_client_are_preserved(self):
        result,state=self.start();row=self.flows.claim(state);self.assertEqual(row['status'],'EXCHANGING')
        secret=self.flows.pending(row)
        self.assertEqual(secret['client_id'],CONFIG['client_id']);self.assertEqual(secret['client_secret'],CONFIG['client_secret'])
        self.assertEqual(secret['binding'],contract.binding(row));self.assertGreaterEqual(len(secret['verifier']),43)
        self.assertEqual(self.flows.alive(row)['id'],result['flow_id'])
        with self.assertRaises(Invalid):self.flows.claim(state)
        with self.assertRaises(Invalid):self.flows.claim('drive_'+'x'*43)

    def test_simultaneous_claims_have_exactly_one_winner(self):
        result,state=self.start();barrier=threading.Barrier(2)
        def claim():
            barrier.wait()
            try:return self.flows.claim(state)['status']
            except Invalid:return 'DENIED'
        with ThreadPoolExecutor(max_workers=2)as pool:outcomes=list(pool.map(lambda _:claim(),range(2)))
        self.assertCountEqual(outcomes,['EXCHANGING','DENIED'])
        self.assertEqual(self.flows.flow('sample-one',result['flow_id'])['status'],'EXCHANGING')

    def test_wrong_port_foreign_app_and_changed_manifest_deny_without_secret_return(self):
        result,state=self.start()
        with self.assertRaises(Invalid):Flows(self.store,8769).claim(state)
        with self.assertRaises(Invalid):self.flows.flow('sample-two',result['flow_id'])
        app=self.store.app('sample-one');self.store.save_app('sample-one',app['data'],app['version'])
        with self.assertRaises(Invalid):self.flows.claim(state)
        self.assertEqual(self.flows.flow('sample-one',result['flow_id'])['status'],'PENDING')
        self.flows.stop('sample-one',result['flow_id']);self.assertFalse(FakeVault.values)

    def test_live_guard_rechecks_manifest_connection_port_and_context_before_loading(self):
        result,state=self.start();row=self.flows.claim(state)
        with self.assertRaises(Invalid):Flows(self.store,8769).pending(row)
        with connection(self.store.path)as db:
            altered=dict(row['data'],client_id='456-other.apps.googleusercontent.com')
            db.execute('UPDATE drive_flows SET data=? WHERE id=?',(canonical(altered),row['id']))
        with self.assertRaises(Invalid):self.flows.pending(row)
        with connection(self.store.path)as db:db.execute('UPDATE drive_flows SET data=? WHERE id=?',(canonical(row['data']),row['id']))
        app=self.store.app('sample-one');self.store.save_app('sample-one',app['data'],app['version'])
        with self.assertRaises(Invalid):self.flows.pending(row)

    def test_cancel_wins_after_claim_and_preserves_prior_connection_credentials(self):
        identity,ref=self.prior_connection();result,state=self.start();row=self.flows.claim(state)
        stopped=self.flows.stop('sample-one',result['flow_id']);self.assertEqual(stopped['status'],'CANCELLED')
        with self.assertRaises(Invalid):self.flows.alive(row)
        with self.assertRaises(Invalid):self.flows.pending(row)
        with self.assertRaises(Invalid):self.flows.claim(state)
        self.assertEqual(self.flows.secrets.load('sample-one',ref,'b'*64)['access_token'],'synthetic-prior-token')
        with connection(self.store.path)as db:
            old=dict(db.execute('SELECT * FROM drive_connections WHERE app_id=?',('sample-one',)).fetchone())
        self.assertEqual((old['id'],old['version'],old['status']),(identity,3,'CONNECTED'))
        self.assertEqual(self.flows.stop('sample-one',result['flow_id'])['status'],'CANCELLED')

    def test_changed_prior_connection_revision_invalidates_claim_and_live_guard(self):
        self.prior_connection();result,state=self.start()
        with connection(self.store.path)as db:db.execute('UPDATE drive_connections SET version=version+1')
        with self.assertRaises(Invalid):self.flows.claim(state)
        self.flows.stop('sample-one',result['flow_id'])
        result,state=self.start();row=self.flows.claim(state)
        with connection(self.store.path)as db:db.execute('UPDATE drive_connections SET version=version+1')
        with self.assertRaises(Invalid):self.flows.alive(row)

    def test_stale_setup_and_boolean_revisions_reject_before_any_vault_write(self):
        body=self.body()
        for update in ({'confirm_scope':False},{'manifest_version':True},{'connection_version':True},
                       {'manifest_version':0},{'connection_id':uid()},{'connection_version':1},
                       {'extra':'not-authorized'},{'client_json':'{}'}):
            with self.subTest(update=update),self.assertRaises(Invalid):self.flows.start('sample-one',{**body,**update})
        self.assertFalse(FakeVault.values)

    def test_expiry_on_restart_cancels_pending_and_marks_exchange_unconfirmed(self):
        pending,_=self.start();exchanging,state=self.start();row=self.flows.claim(state)
        with connection(self.store.path)as db:db.execute('UPDATE drive_flows SET expires=0')
        with self.assertRaises(Invalid):self.flows.alive(row)
        reopened=Flows(Store(self.store.path),8768);status=reopened.status('sample-one')
        states={r['id']:r['status']for r in status['flows']}
        self.assertEqual(states[pending['flow_id']],'EXPIRED');self.assertEqual(states[exchanging['flow_id']],'UNCONFIRMED')
        self.assertFalse(FakeVault.values)

    def test_claim_and_live_guard_reject_at_original_expiry_without_mutating_flow_context(self):
        result,state=self.start();row=self.flows.flow('sample-one',result['flow_id'])
        with patch('mission_control.drive_flows.time.time',return_value=row['expires']),self.assertRaisesRegex(Invalid,'expired'):
            self.flows.claim(state)
        row=self.flows.claim(state)
        with patch('mission_control.drive_flows.time.time',return_value=row['expires']+1),self.assertRaisesRegex(Invalid,'expired'):
            self.flows.alive(row)

    def test_cancel_with_native_delete_failure_leaves_terminal_flow_and_cleanup_reference(self):
        result,state=self.start();FakeVault.fail_delete=1
        self.assertEqual(self.flows.stop('sample-one',result['flow_id'])['status'],'CANCELLED')
        self.assertEqual(self.flows.status('sample-one')['cleanup_pending'],1)
        with self.assertRaises(Invalid):self.flows.claim(state)
        self.assertEqual(self.flows.secrets.cleanup('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)

    def test_active_limit8_and_status_bound_preserve_prior_flows_and_retire_new_stage(self):
        prepared=[self.start()[0]for _ in range(8)];before=copy_values()
        with self.assertRaisesRegex(Invalid,'active Drive'):self.start()
        self.assertEqual(FakeVault.values,before);self.assertEqual(len(self.flows.status('sample-one')['flows']),8)
        self.flows.stop('sample-one',prepared[0]['flow_id']);self.start()
        with connection(self.store.path)as db:self.assertEqual(db.execute('SELECT COUNT(*)FROM drive_flows').fetchone()[0],9)
        self.assertEqual(len(self.flows.status('sample-one')['flows']),8)

    def test_staging_race_manifest_change_rolls_back_candidate_and_does_not_leave_orphan(self):
        original=self.flows.persist
        def changed(row,ref):
            app=self.store.app('sample-one');self.store.save_app('sample-one',app['data'],app['version'])
            return original(row,ref)
        with patch.object(self.flows,'persist',side_effect=changed),self.assertRaises(Invalid):self.start()
        self.assertFalse(FakeVault.values)
        with connection(self.store.path)as db:
            self.assertEqual(db.execute('SELECT COUNT(*)FROM drive_flows').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*)FROM drive_retirements').fetchone()[0],0)

    def test_protected_binding_tamper_is_denied_even_when_public_context_looks_current(self):
        _,state=self.start();row=self.flows.claim(state)
        for key,value in list(FakeVault.values.items()):
            if key.endswith('/binding'):FakeVault.values[key]={'value':'b'*64}
        with self.assertRaises(Invalid):self.flows.pending(row)

    def test_total_limit1000_retains_history_and_cleans_rejected_new_stage(self):
        result,state=self.start();self.flows.stop('sample-one',result['flow_id'])
        row=self.flows.flow('sample-one',result['flow_id'])
        with connection(self.store.path)as db:
            for index in range(999):
                db.execute('INSERT INTO drive_flows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (uid(),'sample-one',1,None,0,hashlib.sha256(str(index).encode()).hexdigest(),uid(),'{}','CANCELLED',0,now(),now(),None))
        with self.assertRaisesRegex(Invalid,'1000'):self.start()
        with connection(self.store.path)as db:self.assertEqual(db.execute('SELECT COUNT(*)FROM drive_flows').fetchone()[0],1000)
        self.assertFalse(FakeVault.values)

    def test_contract_rejects_missing_rows_and_malformed_private_metadata(self):
        with self.assertRaises(Invalid):contract.decoded(None)
        result,_=self.start()
        with connection(self.store.path)as db:db.execute('UPDATE drive_flows SET data=? WHERE id=?',('{broken',result['flow_id']))
        with self.assertRaises(Invalid):self.flows.flow('sample-one',result['flow_id'])
        with self.assertRaises(Invalid):self.flows.stop('sample-one',result['flow_id'],'CONNECTED')


def copy_values():
    return {key:dict(value)for key,value in FakeVault.values.items()}
