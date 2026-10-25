"""Synthetic protected-store boundaries; real native acceptance is recorded separately."""
import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from mission_control import drive_secrets as secrets
from mission_control.common import Invalid, canonical, now, uid
from mission_control.db import connection
from mission_control.store import Store
from tests.test_measurement_connectors import FakeVault

BINDING = 'a'*64


class DriveSecretTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'synthetic.sqlite3');self.secrets=secrets.Secrets(self.store)
        FakeVault.values={};FakeVault.fail_delete=0
        fake=patch('mission_control.drive_secrets.Vault',FakeVault);fake.start();self.addCleanup(fake.stop)

    def values(self):
        return dict(binding=BINDING,access_token='A'*2048,refresh_token='R'*2048)

    def attach(self,ref,status='CONNECTED'):
        with connection(self.store.path)as db:
            db.execute('BEGIN IMMEDIATE')
            self.secrets.activate(db,'sample-one',ref,BINDING,['access_token','refresh_token'])
            db.execute('INSERT INTO drive_connections VALUES(?,?,?,?,?,?,?,?,?)',
                       ('sample-one',uid(),1,'{}',ref,status,time.time()+3600,now(),now()))

    def test_fields_stage_and_load_long_values_without_sql_or_export_payloads(self):
        values=self.values();ref=self.secrets.stage('sample-one',values)
        self.assertEqual(self.secrets.load('sample-one',ref,BINDING),values)
        self.assertEqual(secrets.Secrets(Store(self.store.path)).load('sample-one',ref,BINDING),values)
        values['access_token']='changed';self.assertEqual(self.secrets.load('sample-one',ref,BINDING)['access_token'],'A'*2048)
        with connection(self.store.path)as db:
            sql=''.join(str(tuple(row))for row in db.execute('SELECT * FROM drive_retirements'))
        exported=canonical(self.store.export('sample-one'))
        for private in ('A'*2048,'R'*2048,BINDING):self.assertNotIn(private,sql+exported)
        self.assertNotIn(ref,exported)

    def test_name_reference_binding_and_field_validation_before_native_access(self):
        ref=uid();self.assertIn('/sample-one/',secrets.name(self.store,'sample-one',ref,'binding'))
        self.assertEqual(secrets.reference(ref),ref);self.assertEqual(secrets.binding(BINDING),BINDING)
        for value in ('../foreign',None,ref.upper(),[],123):
            with self.subTest(value=value),self.assertRaises(Invalid):secrets.reference(value)
        for value in ('a'*63,'A'*64,[],None):
            with self.subTest(value=value),self.assertRaises(Invalid):secrets.binding(value)
        with self.assertRaises(Invalid):secrets.name(self.store,'sample-one',ref,'password')
        for value in ({},None,{'binding':BINDING},{'binding':BINDING,'password':'secret'},
                      {'binding':BINDING,'access_token':'x'*2049},{'binding':BINDING,'access_token':'x\ny'}):
            with self.subTest(value=value),self.assertRaises(Invalid):self.secrets.stage('sample-one',value)
        self.assertFalse(FakeVault.values)

    def test_wrong_app_database_and_expected_binding_cannot_load(self):
        ref=self.secrets.stage('sample-one',self.values())
        with self.assertRaises(Invalid):self.secrets.load('sample-two',ref,BINDING)
        with self.assertRaises(Invalid):self.secrets.load('sample-one',ref,'b'*64)
        other=Store(Path(self.folder.name)/'other.sqlite3')
        with self.assertRaises(Invalid):secrets.Secrets(other).load('sample-one',ref,BINDING)
        self.assertEqual(self.secrets.load('sample-one',ref,BINDING),self.values())

    def test_partial_write_failure_removes_or_queues_bundle_for_recovery(self):
        original=FakeVault.put
        def fail(vault,address,value):
            if address.endswith('/refresh_token'):raise Invalid('Synthetic write failure')
            return original(vault,address,value)
        with patch.object(FakeVault,'put',fail),self.assertRaises(Invalid):self.secrets.stage('sample-one',self.values())
        self.assertFalse(FakeVault.values)
        FakeVault.fail_delete=1
        with patch.object(FakeVault,'put',fail),self.assertRaises(Invalid):self.secrets.stage('sample-one',self.values())
        self.assertTrue(FakeVault.values)
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)

    def test_activation_needs_transaction_live_stage_required_fields_and_binding(self):
        ref=self.secrets.stage('sample-one',self.values())
        with connection(self.store.path)as db:
            with self.assertRaises(Invalid):self.secrets.activate(db,'sample-one',ref,BINDING,['access_token'])
            db.execute('BEGIN IMMEDIATE')
            for required in ([],None,['password'],['client_secret']):
                with self.subTest(required=required),self.assertRaises(Invalid):self.secrets.activate(db,'sample-one',ref,BINDING,required)
            with self.assertRaises(Invalid):self.secrets.activate(db,'sample-one',ref,'b'*64,['access_token'])
            db.execute('UPDATE drive_retirements SET eligible=0')
            with self.assertRaisesRegex(Invalid,'expired'):self.secrets.activate(db,'sample-one',ref,BINDING,['access_token'])
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],0)

    def test_active_connection_retirement_is_denied_until_detachment(self):
        ref=self.secrets.stage('sample-one',self.values());self.attach(ref)
        with connection(self.store.path)as db:
            self.assertTrue(secrets.active(db,'sample-one',ref))
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaisesRegex(Invalid,'already attached'):self.secrets.activate(db,'sample-one',ref,BINDING,['access_token'])
        self.assertEqual(self.secrets.retire('sample-one',ref),'LOCAL_CLEANUP_REQUIRED')
        self.assertEqual(self.secrets.load('sample-one',ref,BINDING),self.values())
        with self.assertRaisesRegex(Invalid,'active Drive'):self.secrets.cleanup('sample-one')
        with connection(self.store.path)as db:db.execute("UPDATE drive_connections SET status='DISCONNECTED',secret_ref=NULL")
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)

    def test_pending_flow_protects_credentials_until_terminal_status(self):
        ref=self.secrets.stage('sample-one',dict(binding=BINDING,verifier='v'*64))
        with connection(self.store.path)as db:
            db.execute('BEGIN IMMEDIATE');self.secrets.activate(db,'sample-one',ref,BINDING,['verifier'])
            db.execute('INSERT INTO drive_flows VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (uid(),'sample-one',1,None,0,'s'*64,ref,'{}','PENDING',time.time()+600,now(),now(),None))
        self.assertEqual(self.secrets.retire('sample-one',ref),'LOCAL_CLEANUP_REQUIRED')
        with connection(self.store.path)as db:db.execute("UPDATE drive_flows SET status='CANCELLED'")
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)

    def test_expired_stages_and_failed_delete_recover_after_reopen(self):
        ref=self.secrets.stage('sample-one',self.values())
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],1)
        FakeVault.fail_delete=1
        self.assertEqual(self.secrets.retire('sample-one',ref),'LOCAL_CLEANUP_REQUIRED')
        reopened=secrets.Secrets(Store(self.store.path));self.assertEqual(reopened.cleanup('sample-two')['remaining'],0)
        self.assertEqual(reopened.cleanup('sample-one')['remaining'],0);self.assertFalse(FakeVault.values)
        self.assertEqual(reopened.retire('sample-one',None),'NO_PRIOR_SECRET')

    def test_clean_one_removes_only_an_eligible_queued_bundle(self):
        ref=self.secrets.stage('sample-one',self.values())
        self.secrets.clean_one('sample-one',ref)
        self.assertEqual(self.secrets.load('sample-one',ref,BINDING),self.values())
        with connection(self.store.path)as db:db.execute('UPDATE drive_retirements SET eligible=0')
        self.secrets.clean_one('sample-one',ref)
        self.assertFalse(FakeVault.values)
        self.secrets.clean_one('sample-one',ref)

    def test_cleanup_limit20_does_not_touch_other_app_and_missing_stage_cannot_activate(self):
        refs=[self.secrets.stage('sample-one',dict(binding=BINDING,verifier='v'*64))for _ in range(21)]
        other=self.secrets.stage('sample-two',dict(binding=BINDING,verifier='z'*64))
        with connection(self.store.path)as db:db.execute('UPDATE drive_retirements SET eligible=0')
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],1)
        self.assertEqual(self.secrets.load('sample-two',other,BINDING)['verifier'],'z'*64)
        self.assertEqual(self.secrets.cleanup('sample-one')['remaining'],0)
        with connection(self.store.path)as db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(Invalid):self.secrets.activate(db,'sample-one',refs[0],BINDING,['verifier'])
        with connection(self.store.path)as db:
            for delay in (True,-1,1,301):
                with self.subTest(delay=delay),self.assertRaises(Invalid):secrets.queue(db,'sample-one',uid(),delay)

    def test_tampered_native_shape_or_bound_value_is_rejected(self):
        ref=self.secrets.stage('sample-one',self.values());address=secrets.name(self.store,'sample-one',ref,'access_token')
        for value in ({'value':'x','extra':1},[],{'value':'bad\nvalue'}):
            FakeVault.values[address]=copy.deepcopy(value)
            with self.subTest(value=value),self.assertRaises(Invalid):self.secrets.load('sample-one',ref,BINDING)

    def test_schema_is_idempotent_and_foreign_app_reference_is_rejected(self):
        Store(self.store.path);Store(self.store.path)
        with connection(self.store.path)as db:
            self.assertEqual(db.execute("SELECT COUNT(*)FROM sqlite_master WHERE type='table' AND name IN ('drive_flows','drive_connections','drive_retirements')").fetchone()[0],3)
        with self.assertRaises(KeyError):self.secrets.stage('nonexistent-app',self.values())
