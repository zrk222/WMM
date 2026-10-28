"""Shared media persistence/rights through synthetic native inspection, no device proof."""
import json
import unittest
from unittest.mock import patch
from tests import test_ios_host as host
from tests import test_managed_media_store as media_fixture
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_media_adapter import NativeMediaAdapter


class NativeMediaTests(unittest.TestCase):
    setUp = host.NativeRuntimeTests.setUp
    verify = host.NativeRuntimeTests.verify
    creation = host.NativeRuntimeTests.creation

    def adapter(self, inspector=media_fixture.synthetic_inspection):
        return NativeMediaAdapter(self.runtime.service,self.runtime.identities,inspector)

    def owned(self):
        self.runtime.create_workspace(self.session,self.creation())
        return self.adapter()

    def upload(self,adapter,key='native-upload'):
        return json.loads(adapter.upload(self.session,'new-app','clip.mp4',media_fixture.RAW,
            json.dumps(dict(manifest_version=1,request_key=key)).encode()))

    def decision(self,view,status='ALLOWED'):
        return json.dumps(dict(expected_version=view['review_version'],manifest_version=1,
            source_sha256=view['source_sha256'],status=status,basis='OWNED',evidence='Synthetic owner-created clip')).encode()

    def test_original_roundtrip_idempotence_rights_and_revocation(self):
        adapter=self.owned();item=self.upload(adapter)
        self.assertEqual(item['rights_status'],'UNKNOWN')
        self.assertFalse(item['reuse_available'])
        self.assertEqual(self.upload(adapter)['id'],item['id'])
        with self.assertRaises(Invalid):adapter.resolve(self.session,'new-app',item['id'],item['source_sha256'])
        reviewed=json.loads(adapter.review(self.session,'new-app',item['id'],self.decision(item)))
        self.assertTrue(reviewed['reuse_available'])
        resolved=adapter.resolve(self.session,'new-app',item['id'],item['source_sha256'])
        self.assertEqual(resolved.read_bytes(),media_fixture.RAW)
        adapter.review(self.session,'new-app',item['id'],self.decision(reviewed,'REVOKED'))
        with self.assertRaises(Invalid):adapter.resolve(self.session,'new-app',item['id'],item['source_sha256'])

    def test_foreign_session_and_payload_inspection_cannot_authorize_upload(self):
        adapter=self.owned()
        with self.assertRaises(PermissionError):adapter.list(self.session,'other')
        with self.assertRaises(Invalid):adapter.upload(self.session,'new-app','clip.mp4',media_fixture.RAW,
            b'{"manifest_version":1,"request_key":"forge","inspection":{"decoded":true}}')
        self.available=False
        with self.assertRaises(PermissionError):self.upload(adapter)

    def test_native_inspector_never_falls_back_to_desktop_process_validation(self):
        self.owned()
        class NativeInspector:
            def __bool__(self):return False
            def __call__(self,*args,**kwargs):return media_fixture.synthetic_inspection(*args,**kwargs)
        with patch('mission_control.managed_media_store.inspect',side_effect=AssertionError('No desktop inspector')):
            self.assertEqual(self.upload(self.adapter(NativeInspector()))['rights_status'],'UNKNOWN')

    def test_bad_native_proof_or_lock_during_decode_leaves_no_media(self):
        self.owned()
        def mismatch(raw,suffix,alive):
            value=media_fixture.synthetic_inspection(raw,suffix,alive);value['sha256']='0'*64;return value
        with self.assertRaises(Invalid):self.upload(self.adapter(mismatch))
        def lock(raw,suffix,alive):
            value=media_fixture.synthetic_inspection(raw,suffix,alive);self.available=False;return value
        with self.assertRaises(PermissionError):self.upload(self.adapter(lock))
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM managed_media').fetchone()[0],0)

    def test_lock_after_rights_insert_rolls_back_attestation(self):
        from mission_control.managed_media_store import Media
        adapter=self.owned();item=self.upload(adapter)
        original=Media._insert_review
        def write_then_lock(*args):
            original(*args);self.available=False
        with patch.object(Media,'_insert_review',staticmethod(write_then_lock)):
            with self.assertRaises(PermissionError):adapter.review(self.session,'new-app',item['id'],self.decision(item))
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM managed_media_reviews').fetchone()[0],0)
