"""Actual local owner HTTP with synthetic identity and explicit decoder fixture."""
import hashlib
from email.message import Message
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.managed_media_http import body, route
from mission_control.operator_client import OperatorClient
from mission_control.server import Server
from mission_control.store import Store
from tests import test_verified_review as identities

APP='media-fixture'
RAW=b'explicit synthetic decoder fixture; not playable video'


def decoded(raw,suffix,alive=lambda:None,tools=None):
    alive()
    return dict(sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                metadata=dict(codec='h264',width=320,height=180,duration_seconds=2,frame_rate=24,audio=True),
                decoded=dict(video_frames=48,audio_frames=94))


class MediaHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'state.sqlite',seed=False)
        self.store.save_app(APP,dict(name='Synthetic source app',release='one',locale='en-US'))
        self.identity=patch('mission_control.operator_identity.github_read',side_effect=identities.synthetic_identity)
        self.identity.start();self.addCleanup(self.identity.stop)
        decoder=patch('mission_control.managed_media_store.inspect',side_effect=decoded)
        self.decoder=decoder.start();self.addCleanup(decoder.stop)
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port);self.base='/api/apps/'+APP+'/media'
        self.client=OperatorClient(self.origin);self.client.bootstrap()
        self.client.request('POST','/api/identity/login',dict(token=identities.OWNER_TOKEN))
        self.client.request('POST','/api/apps/'+APP+'/access/bootstrap',dict(confirm_owner=True))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10);self.temp.cleanup()

    def send(self,method,path,raw=None,headers=None,client=None):
        client=client or self.client
        values={'Origin':self.origin,'X-CSRF-Token':client.csrf or ''};values.update(headers or {})
        request=Request(self.origin+path,data=raw,headers=values,method=method)
        try:
            with client.opener.open(request,timeout=15) as response:return response.status,response.read(),response.headers
        except HTTPError as error:
            with error:return error.code,error.read(),error.headers

    def upload(self,key='upload-one'):
        import json
        code,raw,_=self.send('POST',self.base+'/uploads',RAW,{'Content-Type':'application/octet-stream',
            'X-Filename':'clip.mp4','X-WMM-Manifest-Version':'1','X-WMM-Request-Key':key})
        self.assertEqual(code,201,raw);return json.loads(raw)

    def test_upload_original_range_and_reuse_review_are_separate(self):
        row=self.upload();self.assertEqual(row['source_sha256'],hashlib.sha256(RAW).hexdigest())
        self.assertFalse(row['reuse_available']);self.assertEqual(row['id'],self.upload()['id'])
        code,raw,headers=self.send('GET',self.base+'/'+row['id']+'/preview',headers={'Range':'bytes=2-7'})
        self.assertEqual((code,raw),(206,RAW[2:8]));self.assertEqual(headers['Content-Range'],f'bytes 2-7/{len(RAW)}')
        review=dict(expected_version=0,manifest_version=1,source_sha256=row['source_sha256'],status='ALLOWED',basis='OWNED',evidence='Synthetic owner attestation')
        allowed=self.client.request('POST',self.base+'/'+row['id']+'/reviews',review)
        self.assertTrue(allowed['reuse_available'])
        revoked=self.client.request('POST',self.base+'/'+row['id']+'/reviews',dict(review,expected_version=1,status='REVOKED'))
        self.assertFalse(revoked['reuse_available'])
        self.assertEqual(self.send('GET',self.base+'/'+row['id']+'/download')[1],RAW)

    def test_unsigned_wrong_scope_and_noncanonical_paths_cannot_read_sources(self):
        row=self.upload();anonymous=OperatorClient(self.origin);anonymous.bootstrap()
        self.assertEqual(self.send('GET',self.base,client=anonymous)[0],403)
        for path in [self.base+'/',self.base+'?x=1',self.base.replace('/media','//media'),'/api/apps/other-app/media/'+row['id']]:
            with self.subTest(path=path):self.assertNotEqual(self.send('GET',path)[0],200)

    def test_missing_csrf_and_unapproved_content_type_do_not_decode(self):
        self.decoder.reset_mock()
        for headers in [{'X-CSRF-Token':'wrong'},{'Content-Type':'video/mp4'}]:
            code,_,_=self.send('POST',self.base+'/uploads',RAW,dict({'Content-Type':'application/octet-stream','X-Filename':'clip.mp4',
                'X-WMM-Manifest-Version':'1','X-WMM-Request-Key':'bad'},**headers))
            self.assertIn(code,(400,403))
        self.decoder.assert_not_called()

    def test_owner_revoked_during_decode_cannot_commit(self):
        def revoke(raw,suffix,**kwargs):
            # Separate thread models another local owner operation outside this
            # request's contextvars, rather than borrowing its protected scope.
            def write():
                with connection(self.store.path) as db:
                    db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",(APP,))
            worker=threading.Thread(target=write);worker.start();worker.join()
            return decoded(raw,suffix)
        self.decoder.side_effect=revoke
        code,_,_=self.send('POST',self.base+'/uploads',RAW,{'Content-Type':'application/octet-stream','X-Filename':'clip.mp4',
            'X-WMM-Manifest-Version':'1','X-WMM-Request-Key':'revoked'})
        self.assertEqual(code,403)
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM managed_media').fetchone()[0],0)


class MediaEnvelopeTests(unittest.TestCase):
    def test_ambiguous_framing_and_noncanonical_paths_reject_before_read(self):
        for name,value in [('Transfer-Encoding',''),('Content-Type','application/octet-stream'),('Content-Length','3')]:
            headers=Message();headers['Content-Type']='application/octet-stream';headers['Content-Length']='3';headers[name]=value
            with self.subTest(name=name):
                with self.assertRaises(Invalid):body(SimpleNamespace(headers=headers),'application/octet-stream',64)
        handler=SimpleNamespace(path='/api/apps/media-fixture/media?x=1')
        with self.assertRaises(Invalid):route(handler,['api','apps',APP,'media'])


if __name__=='__main__':unittest.main()
