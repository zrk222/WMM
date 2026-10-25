"""Real app/source/registry preparation with controlled installation identity."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest,canonical
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.hypit_jobs import HypitRenders
from mission_control.hypit_studio_registry import Registry
from mission_control import hypit_studio_factory as target
from tests.test_creative_rendering import prepared_render,APP


class FactoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name);self.store=Store(self.root/'state.sqlite')
        self.brief,request=prepared_render(self.store)
        with patch('mission_control.hypit_jobs.identity',return_value={}):
            self.job=HypitRenders(self.store).queue(APP,dict(data=request,request_key='source-one'))
        self.font=self.root/'synthetic-font.ttf';self.font.write_bytes(b'SYNTHETIC_FONT_BYTES')
        self.installation=dict(id='a'*64,version='0.3.1',tree_sha256='b'*64,node_sha256='c'*64,files=10,bytes=100)
        for name,value in [('discover',self.installation),('capability',dict(font=str(self.font))),('revalidate',self.installation)]:
            p=patch.object(target,name,return_value=value);p.start();self.addCleanup(p.stop)
        self.factory=target.Factory(self.store);self.registry=Registry(self.store)
        self.body=dict(source_job_id=self.job['id'],manifest_version=self.store.app(APP)['version'])

    def reserve(self):
        self.plan=self.factory.plan(APP,self.body)
        return self.registry.reserve(APP,'studio-one',self.plan['intent'])

    def create(self,row):return self.factory.create(APP,row['id'],row['version'],lambda:None)

    def test_summary_is_deterministic_binds_every_file_and_omits_paths(self):
        first=self.factory.plan(APP,self.body);second=self.factory.plan(APP,self.body)
        self.assertEqual(first,second);self.assertEqual(first['summary_hash'],digest(first['summary']))
        self.assertEqual(set(first['summary']['staged_hashes']),{'film.svml','style.svs','build.svrun','runtime.json','package.json','font.ttf'})
        self.assertEqual(first['summary']['staged_hashes']['font.ttf'],hashlib.sha256(self.font.read_bytes()).hexdigest())
        for secret in (str(self.root),'SYNTHETIC_FONT_BYTES','<svml','entrypoint'):
            self.assertNotIn(secret,json.dumps(first))
        self.assertFalse((self.root/'studio').exists())

    def test_creates_exact_isolated_project_and_new_unstarted_object(self):
        row=self.reserve()
        with patch.object(target.StudioProcess,'start',side_effect=AssertionError('No launch from factory')):
            session=self.create(row)
        self.assertEqual(session.state,'NEW');self.assertIsNone(session.process);self.assertIsNone(session.origin)
        self.assertEqual(session.folder,self.root/'studio'/digest(APP)/row['id'])
        self.assertEqual(session.sources,self.plan['summary']['staged_hashes'])
        self.assertEqual((session.folder/'font.ttf').read_bytes(),self.font.read_bytes())
        self.assertFalse((session.folder/'.hypit').exists())
        self.assertEqual(set(p.name for p in session.folder.iterdir()),set(session.sources))
        with self.assertRaises(FileExistsError):self.create(row)

    def test_foreign_job_wrong_action_manifest_and_hidden_input_reject(self):
        with self.assertRaises(Invalid):self.factory.plan('sample-two',self.body)
        for change in ({'manifest_version':True},{'manifest_version':99},{'path':'PRIVATE'}):
            with self.assertRaises(Invalid):self.factory.plan(APP,dict(self.body,**change))
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET action='pipeline' WHERE id=?",(self.job['id'],))
        with self.assertRaises(Invalid):self.factory.plan(APP,self.body)

    def test_changed_frozen_scene_and_rights_reject(self):
        with connection(self.store.path) as db:
            data=json.loads(db.execute('SELECT data FROM jobs WHERE id=?',(self.job['id'],)).fetchone()[0])
            data['scene']['scenes'][0]['text']='Changed after approval'
            db.execute('UPDATE jobs SET data=? WHERE id=?',(canonical(data),self.job['id']))
        with self.assertRaises(Invalid):self.factory.plan(APP,self.body)
        self.assertFalse((self.root/'studio').exists())

    def test_revoked_asset_rights_rejects_current_source(self):
        row=self.reserve()
        asset=next(r for r in self.store.records(APP) if r['kind']=='asset')
        Service(self.store).evidence(APP,dict(id=asset['id'],version=asset['version'],kind='asset',
            title=asset['title'],source=asset['source'],data=dict(asset['data'],rights_cleared=False)))
        with self.assertRaises(Invalid):self.create(row)
        self.assertFalse((self.root/'studio').exists())

    def test_changed_font_or_installation_after_review_rejects_before_folder(self):
        row=self.reserve();self.font.write_bytes(b'NEW_FONT_BYTES')
        with self.assertRaisesRegex(Invalid,'summary'):self.create(row)
        self.assertFalse((self.root/'studio').exists())
        self.font.write_bytes(b'SYNTHETIC_FONT_BYTES')
        with patch.object(target,'discover',return_value=dict(self.installation,id='d'*64)):
            with self.assertRaisesRegex(Invalid,'summary'):self.create(row)

    def test_missing_or_changed_reservation_never_creates_project(self):
        row=self.reserve()
        with self.assertRaises(Invalid):self.factory.create(APP,row['id'],True,lambda:None)
        self.registry.transition(APP,row['id'],1,'UNKNOWN')
        with self.assertRaises(Invalid):self.create(row)
        self.assertFalse((self.root/'studio').exists())

    def test_final_reservation_recheck_rejects_intervening_transition(self):
        row=self.reserve();calls=[]
        def revalidate(value):
            calls.append(1)
            if len(calls)==2:self.registry.transition(APP,row['id'],1,'UNKNOWN')
            return value
        with patch.object(target,'revalidate',side_effect=revalidate):
            with self.assertRaisesRegex(Invalid,'reservation'):self.create(row)
        folder=self.root/'studio'/digest(APP)/row['id']
        self.assertTrue(folder.exists());self.assertEqual(self.registry.read(APP,row['id'])['state'],'UNKNOWN')

    def test_final_staged_bytes_and_unexpected_files_reject_without_cleanup_deletion(self):
        row=self.reserve();calls=[]
        def revalidate(value):
            calls.append(1)
            if len(calls)==2:
                folder=self.root/'studio'/digest(APP)/row['id']
                (folder/'runtime.json').write_text('{}')
            return value
        with patch.object(target,'revalidate',side_effect=revalidate):
            with self.assertRaises(Invalid):self.create(row)
        self.assertTrue((self.root/'studio'/digest(APP)/row['id']).exists())

    def test_font_changed_during_final_installation_check_rejects(self):
        row=self.reserve();calls=[]
        def revalidate(value):
            calls.append(1)
            if len(calls)==2:self.font.write_bytes(b'CHANGED_LATE_FONT')
            return value
        with patch.object(target,'revalidate',side_effect=revalidate):
            with self.assertRaisesRegex(Invalid,'font'):self.create(row)

    def test_bundle_and_font_size_bounds_reject_before_directory(self):
        with patch.object(target,'MAX_PROJECT_BYTES',1):
            with self.assertRaisesRegex(Invalid,'project'):self.factory.plan(APP,self.body)
        with patch.object(target,'MAX_FONT_BYTES',1):
            with self.assertRaisesRegex(Invalid,'font'):self.factory.plan(APP,self.body)
        self.assertFalse((self.root/'studio').exists())

    def test_reparse_attribute_is_rejected_on_private_parent(self):
        row=self.reserve();original=target.plain
        def reject(path,directory=False):
            if Path(path)==self.root/'studio':raise Invalid('Synthetic reparse directory')
            return original(path,directory)
        with patch.object(target,'plain',side_effect=reject):
            with self.assertRaisesRegex(Invalid,'reparse'):self.create(row)
        self.assertFalse((self.root/'studio'/digest(APP)/row['id']).exists())

    def test_callback_denial_during_writes_leaves_inspectable_partial_project(self):
        row=self.reserve();calls=[]
        def alive():
            calls.append(1)
            if len(calls)==7:raise PermissionError('Synthetic revocation')
        with self.assertRaises(PermissionError):self.factory.create(APP,row['id'],1,alive)
        self.assertTrue((self.root/'studio'/digest(APP)/row['id']).exists())
        self.assertEqual(self.registry.read(APP,row['id'])['state'],'PREPARED')


if __name__=='__main__':unittest.main()
