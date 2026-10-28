"""Shared native backup authority and rollback; not physical-device evidence."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4
from unittest.mock import patch
from mission_control.common import Invalid,canonical,digest
from mission_control.db import connection
from mission_control.ios_host import Runtime
from mission_control.ios_snapshots import document,MAX_SNAPSHOT_BYTES


class NativeSnapshotTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name);self.session=str(uuid4());self.principal=str(uuid4());self.generation=str(uuid4())
        self.available=True
        self.source=Runtime(self.root/'source.sqlite3',self.verify)
        self.target=Runtime(self.root/'target.sqlite3',self.verify)
        setup=dict(app_id='sample',manifest=dict(name='Synthetic app',release='build-1',locale='en-US',currency='USD'),confirm_owner=True)
        self.source.create_workspace(self.session,canonical(setup).encode())
        self.source.service.store.save_record('sample',dict(kind='claim',title='Synthetic finding',source='Synthetic test',data=dict(result='PASS')))

    def verify(self,token):
        if not self.available or token!=self.session:return None
        return dict(principal=self.principal,session_generation=self.generation,expires_at_epoch=time.time()+100)

    def exported(self):return self.source.snapshot_export(self.session,'sample')

    def test_round_trip_new_owner_and_no_replaced_existing_workspace(self):
        original=self.exported()
        result=json.loads(self.target.snapshot_restore(self.session,'sample',original,True))
        self.assertEqual(result['status'],'LOCAL_SNAPSHOT_RESTORED')
        self.assertEqual(result['credentials'],'NOT_IMPORTED')
        self.assertEqual(len(self.target.service.store.records('sample')),1)
        listing=json.loads(self.target.workspaces(self.session))
        self.assertIn('sample',canonical(listing))
        with self.assertRaisesRegex(Invalid,'already exists'):
            self.target.snapshot_restore(self.session,'sample',original,True)
        self.assertEqual(self.target.service.store.app('sample')['version'],1)

    def test_export_requires_current_owner_and_never_exports_grants(self):
        self.source.service.store.save_app('foreign',dict(name='Other',release='build-1',locale='en-US',currency='USD'))
        with self.assertRaises(PermissionError):self.source.snapshot_export(self.session,'foreign')
        raw=self.exported();value=json.loads(raw)
        self.assertNotIn('operator_roles',value['payload'])
        self.assertNotIn('agent_grants',value['payload'])
        self.available=False
        with self.assertRaises(PermissionError):self.exported()

    def test_bad_hash_foreign_app_unconfirmed_and_duplicate_fields_reject(self):
        raw=self.exported();value=json.loads(raw);value['sha256']='0'*64
        for payload,app,confirmed in ((canonical(value).encode(),'sample',True),(raw,'other',True),(raw,'sample',False),(b'{"payload":{},"payload":{}}','sample',True)):
            with self.subTest(app=app,confirmed=confirmed),self.assertRaises(Invalid):
                self.target.snapshot_restore(self.session,app,payload,confirmed)
        with connection(self.target.service.store.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM apps').fetchone()[0],0)

    def test_lock_during_restore_rolls_back_workspace_and_membership(self):
        raw=self.exported()
        from mission_control.review_access import Access
        write=Access.write
        def interrupted(access,*args,**kwargs):
            write(access,*args,**kwargs)
            self.available=False
        with patch.object(Access,'write',interrupted),self.assertRaises(PermissionError):
            self.target.snapshot_restore(self.session,'sample',raw,True)
        with connection(self.target.service.store.path) as db:
            for table in ('apps','records','operator_roles','audit'):
                self.assertEqual(db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0],0)

    def test_imported_fields_cannot_restore_authority(self):
        value=json.loads(self.exported())
        value['payload']['agent_grants']=[dict(token='wmmg_'+'x'*43,owner='foreign')]
        value['payload']['operator_roles']=[dict(principal='foreign',role='OWNER')]
        value['sha256']=digest(value['payload'])
        self.target.snapshot_restore(self.session,'sample',canonical(value).encode(),True)
        with connection(self.target.service.store.path) as db:
            rows=db.execute('SELECT principal FROM operator_roles').fetchall()
            self.assertEqual([r[0] for r in rows],['native:'+self.principal])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM agent_grants').fetchone()[0],0)

    def test_document_bounds_and_finite_json(self):
        for raw in (b'',b' '* (MAX_SNAPSHOT_BYTES+1),b'[]',b'{"x":NaN}',b'\xff'):
            with self.subTest(prefix=raw[:10]),self.assertRaises(Invalid):document(raw)


if __name__=='__main__':unittest.main()
