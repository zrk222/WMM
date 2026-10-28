"""Real shared SQLite through the native callback seam; no native-device claim."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

from mission_control.ios_host import NativeIdentities, Runtime
from mission_control.common import Invalid


class NativeIdentityTests(unittest.TestCase):
    def test_requires_exact_host_metadata_and_bounded_current_session(self):
        session=str(uuid4()); stamp=1000
        valid=dict(principal=str(uuid4()),session_generation=str(uuid4()),expires_at_epoch=stamp+100)
        source=[valid]
        identities=NativeIdentities(lambda token:source[0],lambda:stamp)
        user=identities.fresh(session)
        self.assertEqual(user['provider'],'NATIVE_DEVICE')
        self.assertEqual(identities.local(session,user['principal'],user['session_generation']),user)
        for bad in (None,{},dict(valid,role='OWNER'),dict(valid,expires_at_epoch=True),
                    dict(valid,expires_at_epoch=float('nan')),dict(valid,expires_at_epoch=stamp),
                    dict(valid,expires_at_epoch=stamp+901),dict(valid,principal='not-a-uuid')):
            source[0]=bad
            with self.subTest(bad=bad),self.assertRaises(PermissionError):identities.fresh(session)
        source[0]=dict(valid,session_generation=str(uuid4()))
        with self.assertRaises(PermissionError):identities.local(session,user['principal'],user['session_generation'])
        with self.assertRaises(PermissionError):identities.fresh('caller-supplied-name')

    def test_callback_errors_do_not_disclose_native_details(self):
        def fail(token):raise RuntimeError('PRIVATE_KEYCHAIN_DETAIL')
        with self.assertRaises(PermissionError) as result:NativeIdentities(fail).fresh(str(uuid4()))
        self.assertNotIn('PRIVATE_KEYCHAIN_DETAIL',str(result.exception))


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.path=Path(folder.name)/'native.sqlite3'
        self.session=str(uuid4());self.principal=str(uuid4());self.generation=str(uuid4())
        self.available=True
        self.runtime=Runtime(self.path,self.verify)
        for app in ('own','other'):
            self.runtime.service.store.save_app(app,dict(name='Synthetic app',release='build-1',locale='en-US',currency='USD'))

    def verify(self,token):
        if not self.available or token!=self.session:return None
        return dict(principal=self.principal,session_generation=self.generation,expires_at_epoch=time.time()+300)

    def test_explicit_owner_enrollment_scoped_read_and_process_reopen(self):
        self.assertEqual(json.loads(self.runtime.workspaces(self.session)),{'apps':[]})
        result=json.loads(self.runtime.enroll(self.session,'own'))
        self.assertEqual(result['identity_provider'],'NATIVE_DEVICE')
        self.assertEqual([a['id'] for a in json.loads(self.runtime.workspaces(self.session))['apps']],['own'])
        payload=b'{"app_id":"own","operation":"growth.history","input":{}}'
        self.assertEqual(json.loads(self.runtime.owner_call(self.session,payload))['app_id'],'own')
        with self.assertRaises(PermissionError):self.runtime.owner_call(self.session,payload.replace(b'own',b'other'))
        reopened=Runtime(self.path,self.verify)
        self.assertEqual(json.loads(reopened.owner_call(self.session,payload))['app_id'],'own')
        self.available=False
        with self.assertRaises(PermissionError):reopened.owner_call(self.session,payload)

    def test_missing_or_replaced_native_identity_never_adopts_saved_owner(self):
        self.runtime.enroll(self.session,'own')
        self.principal=str(uuid4())
        self.assertEqual(json.loads(self.runtime.workspaces(self.session)),{'apps':[]})
        with self.assertRaises(Invalid):self.runtime.enroll(self.session,'own')
        self.available=False
        with self.assertRaises(PermissionError):self.runtime.workspaces(self.session)
