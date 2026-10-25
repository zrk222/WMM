"""Concurrent actual SQLite reservations and durable capacity without native work."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control import hypit_studio_registry as target


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'registry.sqlite',seed=False)
        for name in ('sample-one','sample-two','sample-three'):
            self.store.save_app(name,dict(name=name,release='one',locale='en-US',currency='USD'))
        self.registry=target.Registry(self.store)

    def intent(self,app='sample-one'):
        value=self.store.app(app)
        return dict(manifest_version=value['version'],app_hash=digest(value['data']),source_job_id='source-job',
            source_hash='a'*64,summary_hash='b'*64,installation_id='c'*64)

    def reserve(self,key='startup-one',app='sample-one'):
        return self.registry.reserve(app,key,self.intent(app))

    def proof(self):return dict(kind='OWNED_CLEANUP',child='STOPPED',worker='STOPPED',evidence_hash='d'*64)

    def change(self,row,state,proof=None):
        return self.registry.transition(row['app_id'],row['id'],row['version'],state,proof)

    def test_concurrent_same_key_launches_only_once_and_replay_survives_restart(self):
        def reserve(_):return target.Registry(Store(self.store.path,seed=False)).reserve('sample-one','same',self.intent())
        with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(reserve,range(5)))
        self.assertEqual(sum(row['launch_allowed'] for row in results),1)
        self.assertEqual(len({row['id'] for row in results}),1)
        retry=self.registry.reserve('sample-one','same',self.intent())
        self.assertFalse(retry['launch_allowed']);self.assertTrue(retry['capacity_reserved'])
        self.assertEqual(retry['live_ownership'],'NOT_ESTABLISHED_BY_REGISTRY')

    def test_changed_retry_rejects_before_any_capacity_or_manifest_change(self):
        first=self.reserve();value=self.intent();value['summary_hash']='e'*64
        with self.assertRaisesRegex(Invalid,'retry'):self.registry.reserve('sample-one','startup-one',value)
        app=self.store.app('sample-one');self.store.save_app('sample-one',dict(app['data'],release='two'),app['version'])
        retry=self.registry.reserve('sample-one','startup-one',self.intent_from(first))
        self.assertFalse(retry['launch_allowed']);self.assertEqual(retry['id'],first['id'])
        with self.assertRaisesRegex(Invalid,'manifest'):self.registry.reserve('sample-one','new',first['intent'])

    def intent_from(self,row):return row['intent']

    def test_app_capacity_counts_unknown_and_cleanup_required_after_restart(self):
        first=self.change(self.reserve('one'),'UNKNOWN')
        second=self.change(self.reserve('two'),'CLEANUP_REQUIRED')
        reopened=target.Registry(Store(self.store.path,seed=False))
        with self.assertRaisesRegex(Invalid,'capacity'):reopened.reserve('sample-one','three',self.intent())
        self.change(first,'CLOSED',self.proof())
        self.assertTrue(reopened.reserve('sample-one','three',self.intent())['launch_allowed'])
        self.assertTrue(self.registry.read('sample-one',second['id'])['inspection_required'])

    def test_global_capacity_is_atomic_across_apps(self):
        for app in ('sample-one','sample-two'):
            for key in ('one','two'):self.reserve(key,app)
        with self.assertRaisesRegex(Invalid,'capacity'):self.reserve('one','sample-three')
        self.assertEqual(len(self.registry.list('sample-three')),0)

    def test_racing_new_keys_never_exceed_app_ceiling(self):
        def reserve(index):
            try:return self.reserve('key-'+str(index))['launch_allowed']
            except Invalid:return False
        with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(reserve,range(6)))
        self.assertEqual(sum(results),2);self.assertEqual(len(self.registry.list('sample-one')),2)

    def test_transitions_are_versioned_and_closed_is_terminal(self):
        row=self.reserve();row=self.change(row,'ACTIVE');row=self.change(row,'CLOSING');row=self.change(row,'CLEANUP_REQUIRED')
        with self.assertRaises(Invalid):self.registry.transition('sample-one',row['id'],True,'CLOSED',self.proof())
        with self.assertRaises(Invalid):self.registry.transition('sample-one',row['id'],row['version']-1,'UNKNOWN')
        row=self.change(row,'CLOSED',self.proof());self.assertFalse(row['capacity_reserved'])
        self.assertEqual([x['version'] for x in row['history']],list(range(1,6)))
        with self.assertRaises(Invalid):self.change(row,'ACTIVE')
        retry=self.registry.reserve('sample-one','startup-one',self.intent())
        self.assertFalse(retry['launch_allowed']);self.assertEqual(retry['state'],'CLOSED')

    def test_missing_or_unconfirmed_cleanup_proof_cannot_release_capacity(self):
        row=self.reserve()
        for proof in (None,{},dict(self.proof(),child='RUNNING'),dict(self.proof(),worker='UNKNOWN'),dict(self.proof(),kind='HUMAN_ASSERTION')):
            with self.assertRaises(Invalid):self.change(row,'CLOSED',proof)
        self.assertEqual(self.registry.read('sample-one',row['id'])['version'],1)

    def test_manifest_types_unknown_fields_private_paths_and_hashes_reject(self):
        intent=self.intent()
        for change in ({'manifest_version':True},{'source_hash':'bad'},{'source_job_id':'../private'},{'path':'PRIVATE_SECRET'}):
            with self.assertRaises(Invalid):self.registry.reserve('sample-one','bad',dict(intent,**change))
        self.assertEqual(self.registry.list('sample-one'),[])

    def test_cross_app_isolation_and_public_projection_omit_internal_retry_key(self):
        row=self.reserve('PRIVATE_RETRY_KEY')
        with self.assertRaises(Invalid):self.registry.read('sample-two',row['id'])
        with self.assertRaises(Invalid):self.registry.transition('sample-two',row['id'],1,'UNKNOWN')
        self.assertNotIn('PRIVATE_RETRY_KEY',json.dumps(row));self.assertNotIn('pid',row);self.assertNotIn('url',row)

    def test_database_failure_rolls_back_reservation_and_transition(self):
        original=target.persist
        def fail(db,row):original(db,row);raise OSError('SYNTHETIC_STORAGE_FAILURE')
        with patch.object(target,'persist',side_effect=fail):
            with self.assertRaises(OSError):self.reserve()
        self.assertEqual(self.registry.list('sample-one'),[])
        row=self.reserve()
        with patch.object(target,'persist',side_effect=fail):
            with self.assertRaises(OSError):self.change(row,'UNKNOWN')
        self.assertEqual(self.registry.read('sample-one',row['id'])['state'],'PREPARED')

    def test_row_tampering_prevents_capacity_and_reads(self):
        row=self.reserve()
        with connection(self.store.path) as db:db.execute("UPDATE studio_sessions SET request_key='changed'")
        with self.assertRaisesRegex(Invalid,'integrity'):self.registry.read('sample-one',row['id'])
        with self.assertRaises(Invalid):self.reserve('another','sample-two')

    def test_checksum_valid_broken_chain_and_illegal_transition_still_reject(self):
        row=self.change(self.reserve(),'ACTIVE')
        with connection(self.store.path) as db:
            stored=dict(db.execute('SELECT * FROM studio_sessions').fetchone());stored['data']=json.loads(stored['data'])
            item=stored['data']['history'][-1];item['previous_hash']='f'*64
            item['hash']=digest({k:v for k,v in item.items() if k!='hash'})
            target.persist(db,stored)
        with self.assertRaisesRegex(Invalid,'chain'):self.registry.read('sample-one',row['id'])

    def test_retained_history_and_transition_bounds_do_not_delete_records(self):
        row=self.reserve()
        with patch.object(target,'MAX_APP_HISTORY',1):
            with self.assertRaisesRegex(Invalid,'history'):self.reserve('another')
        with patch.object(target,'MAX_TRANSITIONS',1):
            with self.assertRaises(Invalid):self.change(row,'UNKNOWN')
        self.assertEqual(len(self.registry.list('sample-one')),1)

    def test_history_always_reserves_terminal_cleanup_slot(self):
        row=self.change(self.reserve(),'CLEANUP_REQUIRED')
        with patch.object(target,'MAX_TRANSITIONS',3):
            with self.assertRaisesRegex(Invalid,'reserved'):self.change(row,'CLEANUP_REQUIRED')
            row=self.change(row,'CLOSED',self.proof())
            self.assertEqual(row['version'],3);self.assertFalse(row['capacity_reserved'])


if __name__=='__main__':unittest.main()
