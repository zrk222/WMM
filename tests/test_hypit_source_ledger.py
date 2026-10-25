"""Durable source/edit intent behavior; no live edit or authority assertion."""
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.store import Store
from mission_control import hypit_source_ledger as target


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(Path(self.tmp.name)/'state.sqlite',seed=False)
        for app in ('sample-one','sample-two'):
            self.store.save_app(app,dict(name='Synthetic',release='build-1',locale='en-US',currency='USD'))
        self.ledger=target.SourceLedger(self.store)
        self.bundle=dict(upstream_revision=1,root='film.svml',files={
            'build.svrun':'SYNTHETIC_RUN','film.svml':'SYNTHETIC_PRIVATE_AUTHOR','style.svs':'size=38'})
        self.head=self.ledger.initialize('sample-one','project-one',self.bundle)

    def body(self,key='edit-one',head=None):
        head=head or self.head
        return dict(request_key=key,base_version=head['version'],base_hash=head['hash'],
                    view_hash='a'*64,proposal_hash='b'*64,actor='admitted-synthetic-owner')

    def changed(self,revision=2):
        value=copy.deepcopy(self.bundle);value['upstream_revision']=revision
        value['files']['style.svs']='size=46';return value

    def test_source_versions_survive_restart_and_history_receipts_omit_text(self):
        second=target.SourceLedger(Store(self.store.path,seed=False))
        result=second.read('sample-one','project-one')
        self.assertEqual(result['head'],self.head);self.assertEqual(len(result['versions']),1)
        self.assertNotIn('SYNTHETIC_PRIVATE_AUTHOR',json.dumps(result))
        self.assertNotIn('files',result['head'])
        self.assertEqual(self.ledger.initialize('sample-one','project-one',self.bundle),self.head)
        with self.assertRaises(Invalid):self.ledger.initialize('sample-one','project-one',self.changed())
        with self.assertRaises(Invalid):second.read('sample-two','project-one')

    def test_prepare_is_durable_once_only_and_retry_never_allows_dispatch(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        self.assertTrue(first['dispatch_allowed']);self.assertEqual(first['status'],'PREPARED')
        replay=target.SourceLedger(Store(self.store.path,seed=False)).prepare('sample-one','project-one',self.body())
        self.assertEqual(first['id'],replay['id']);self.assertFalse(replay['dispatch_allowed'])
        with self.assertRaises(Invalid):self.ledger.prepare('sample-one','project-one',dict(self.body(),proposal_hash='c'*64))
        with self.assertRaisesRegex(Invalid,'Unresolved'):self.ledger.prepare('sample-one','project-one',self.body('another'))

    def test_uncertain_attempt_survives_restart_and_blocks_resend(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        value=self.ledger.uncertain('sample-one','project-one',first['id'])
        self.assertEqual(value['status'],'UNCERTAIN');self.assertFalse(value['dispatch_allowed'])
        second=target.SourceLedger(Store(self.store.path,seed=False))
        self.assertEqual(second.read('sample-one','project-one')['attempts'][0]['status'],'UNCERTAIN')
        with self.assertRaises(Invalid):second.prepare('sample-one','project-one',self.body('new-key'))

    def test_applied_result_atomically_advances_head_and_preserves_versions(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        result=self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
        self.assertEqual(result['result_version'],2)
        view=self.ledger.read('sample-one','project-one')
        self.assertEqual(view['head']['upstream_revision'],2);self.assertEqual(len(view['versions']),2)
        self.assertNotEqual(view['versions'][0]['content_hash'],view['versions'][1]['content_hash'])
        replay=self.ledger.prepare('sample-one','project-one',self.body())
        self.assertEqual(replay['status'],'APPLIED');self.assertFalse(replay['dispatch_allowed'])
        with self.assertRaises(Invalid):self.ledger.uncertain('sample-one','project-one',first['id'])

    def test_rejected_result_requires_identical_source_content_and_allows_new_intent(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        with self.assertRaisesRegex(Invalid,'restore'):self.ledger.finish('sample-one','project-one',first['id'],'REJECTED',self.changed())
        rejected=copy.deepcopy(self.bundle);rejected['upstream_revision']=3
        self.ledger.finish('sample-one','project-one',first['id'],'REJECTED',rejected)
        view=self.ledger.read('sample-one','project-one')
        self.assertEqual(view['head']['content_hash'],self.head['content_hash'])
        self.assertTrue(self.ledger.prepare('sample-one','project-one',self.body('next',view['head']))['dispatch_allowed'])

    def test_invalid_closure_revision_order_stale_head_and_foreign_attempt_reject(self):
        for change in (dict(base_version=2),dict(base_hash='c'*64),dict(base_version=True)):
            with self.assertRaises(Invalid):self.ledger.prepare('sample-one','project-one',dict(self.body(),**change))
        first=self.ledger.prepare('sample-one','project-one',self.body())
        for bundle in (self.changed(1),dict(self.changed(),files={'build.svrun':'new','other.svml':'other'},root='other.svml')):
            with self.assertRaises(Invalid):self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',bundle)
        with self.assertRaises(Invalid):self.ledger.finish('sample-two','project-one',first['id'],'APPLIED',self.changed())
        self.assertEqual(self.ledger.read('sample-one','project-one')['head'],self.head)

    def test_concurrent_distinct_intents_allow_one_unresolved_attempt(self):
        def prepare(key):
            try:return self.ledger.prepare('sample-one','project-one',self.body(key))
            except Invalid:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(prepare,['first','second']))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(len(self.ledger.read('sample-one','project-one')['attempts']),1)

    def test_database_failure_rolls_back_source_head_and_attempt_result_together(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        original=target.append
        def fail(*args,**kw):original(*args,**kw);raise RuntimeError('Synthetic persistence failure')
        with patch.object(target,'append',side_effect=fail):
            with self.assertRaises(RuntimeError):self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
        result=self.ledger.read('sample-one','project-one')
        self.assertEqual(result['head'],self.head);self.assertEqual(result['attempts'][0]['status'],'PREPARED')
        self.assertEqual(len(result['versions']),1)

    def test_source_history_tamper_rejects_and_input_paths_are_closed(self):
        for name in ('../outside.svml','C:/private.svs','/tmp/private.svml','bad\\path.svs','./film.svml'):
            value=copy.deepcopy(self.bundle);value['files'][name]='foreign'
            with self.assertRaises(Invalid):target.source_bundle(value)
        with connection(self.store.path) as db:
            row=db.execute('SELECT data FROM studio_source_versions WHERE app_id=?',('sample-one',)).fetchone()
            tampered=json.loads(row['data']);tampered['files']['film.svml']='changed valid source JSON'
            db.execute('UPDATE studio_source_versions SET data=? WHERE app_id=?',(json.dumps(tampered),'sample-one'))
        with self.assertRaisesRegex(Invalid,'history changed'):self.ledger.read('sample-one','project-one')

    def test_limits_and_non_json_observations_reject(self):
        for name,value in (('MAX_FILES',1),('MAX_SOURCE_BYTES',1)):
            with patch.object(target,name,value),self.assertRaises(Invalid):target.source_bundle(self.bundle)
        with patch.object(target,'MAX_ATTEMPTS',0),self.assertRaises(Invalid):self.ledger.prepare('sample-one','project-one',self.body())
        first=self.ledger.prepare('sample-one','project-one',self.body())
        with patch.object(target,'MAX_VERSIONS',1),self.assertRaises(Invalid):self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
        for value in ([],dict(self.bundle,root=[]),dict(self.bundle,files={'build.svrun':('tuple',)})):
            with self.assertRaises(Invalid):target.source_bundle(value)

    def test_version_capacity_is_checked_before_dispatch_and_run_only_root_rejects(self):
        with patch.object(target,'MAX_VERSIONS',1):
            with self.assertRaisesRegex(Invalid,'capacity'):self.ledger.prepare('sample-one','project-one',self.body())
        self.assertEqual(self.ledger.read('sample-one','project-one')['attempts'],[])
        for value in (dict(upstream_revision=1,root='build.svrun',files={'build.svrun':'run only'}),
                      dict(self.bundle,root='build.svrun')):
            with self.assertRaisesRegex(Invalid,'Author root'):target.source_bundle(value)

    def test_actual_utf8_source_byte_limit_accepts_exact_boundary_and_escaping(self):
        for character in ('a','"','\\'):
            value=dict(upstream_revision=1,root='film.svml',files={
                'build.svrun':'run','film.svml':character*(target.MAX_SOURCE_BYTES-3)})
            target.source_bundle(value)
            value['files']['film.svml']+='a'
            with self.assertRaisesRegex(Invalid,'byte bound'):target.source_bundle(value)
        value=copy.deepcopy(self.bundle);value['files']['film.svml']=chr(0xD800)
        with self.assertRaisesRegex(Invalid,'UTF8'):target.source_bundle(value)

    def test_non_head_corruption_blocks_prepare_and_finish(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
        head=self.ledger.read('sample-one','project-one')['head']
        second=self.ledger.prepare('sample-one','project-one',self.body('next',head))
        with connection(self.store.path) as db:
            db.execute('UPDATE studio_source_versions SET data=? WHERE app_id=? AND version=1',('{}','sample-one'))
        with self.assertRaisesRegex(Invalid,'history changed'):
            self.ledger.prepare('sample-one','project-one',self.body('third',head))
        with self.assertRaisesRegex(Invalid,'history changed'):
            self.ledger.finish('sample-one','project-one',second['id'],'REJECTED',self.changed(3))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT version FROM studio_source_heads WHERE app_id=?',('sample-one',)).fetchone()['version'],2)
            self.assertEqual(db.execute('SELECT status FROM studio_edit_attempts WHERE id=?',(second['id'],)).fetchone()['status'],'PREPARED')

    def test_attempt_state_metadata_tampering_cannot_unblock_dispatch(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        with connection(self.store.path) as db:
            original=dict(db.execute('SELECT * FROM studio_edit_attempts WHERE id=?',(first['id'],)).fetchone())
        for field,value in (('status','APPLIED'),('result_version',99),('updated','changed timestamp'),('request_key','changed-key')):
            with connection(self.store.path) as db:
                db.execute('UPDATE studio_edit_attempts SET '+field+'=? WHERE id=?',(value,first['id']))
            with self.assertRaisesRegex(Invalid,'history changed'):
                self.ledger.prepare('sample-one','project-one',self.body('new-dispatch'))
            with self.assertRaisesRegex(Invalid,'history changed'):
                self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
            with connection(self.store.path) as db:
                db.execute('UPDATE studio_edit_attempts SET '+field+'=? WHERE id=?',(original[field],first['id']))
        self.assertEqual(self.ledger.read('sample-one','project-one')['attempts'][0]['status'],'PREPARED')

    def test_completed_result_linkage_tamper_rejects_after_restart(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
        with connection(self.store.path) as db:
            db.execute('UPDATE studio_edit_attempts SET result_version=1 WHERE id=?',(first['id'],))
        second=target.SourceLedger(Store(self.store.path,seed=False))
        with self.assertRaisesRegex(Invalid,'history changed'):second.read('sample-one','project-one')

    def test_surrogate_source_filenames_and_author_roots_raise_invalid(self):
        for name in ('bad'+chr(0xD800)+'.svml','bad'+chr(0xDFFF)+'.svs'):
            value=copy.deepcopy(self.bundle);value['files'][name]='valid text'
            with self.assertRaisesRegex(Invalid,'UTF8'):target.source_bundle(value)
            value['root']=name
            with self.assertRaisesRegex(Invalid,'UTF8'):target.source_bundle(value)

    def test_source_snapshot_does_not_retain_mutable_caller_files(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        bundle=self.changed();expected=target.source_bundle(copy.deepcopy(bundle))
        real_append=target.append
        def mutate_then_append(*args):
            bundle['files']['style.svs']='unvalidated caller replacement'
            return real_append(*args)
        with patch.object(target,'append',side_effect=mutate_then_append):
            self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',bundle)
        view=self.ledger.read('sample-one','project-one')
        self.assertEqual(view['head']['content_hash'],expected['content_hash'])
        with connection(self.store.path) as db:
            row=db.execute('SELECT data FROM studio_source_versions WHERE version=2').fetchone()
        self.assertEqual(json.loads(row['data']),expected)

    def test_source_timestamp_tamper_rejects_read_prepare_and_finish(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        with connection(self.store.path) as db:
            db.execute('UPDATE studio_source_versions SET created=? WHERE app_id=?',('changed-timestamp','sample-one'))
        with self.assertRaisesRegex(Invalid,'history changed'):
            self.ledger.read('sample-one','project-one')
        with self.assertRaisesRegex(Invalid,'history changed'):
            self.ledger.prepare('sample-one','project-one',self.body('new-edit'))
        with self.assertRaisesRegex(Invalid,'history changed'):
            self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())

    def test_rolled_back_head_pointer_cannot_admit_an_edit_against_old_sources(self):
        first=self.ledger.prepare('sample-one','project-one',self.body())
        self.ledger.finish('sample-one','project-one',first['id'],'APPLIED',self.changed())
        with connection(self.store.path) as db:
            db.execute('UPDATE studio_source_heads SET version=1 WHERE app_id=?',('sample-one',))
        with self.assertRaisesRegex(Invalid,'latest retained'):
            self.ledger.prepare('sample-one','project-one',self.body('stale-replay'))
        with self.assertRaisesRegex(Invalid,'latest retained'):self.ledger.read('sample-one','project-one')


if __name__=='__main__':unittest.main()
