"""Actual native source import/edit proof with synthetic Drive/network/native credential seams."""
import hashlib
import io
import json
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from mission_control import drive_media_contract as contract, drive_media_transport as transport
from mission_control.drive_media import Importer
from mission_control.common import Invalid, now
from mission_control.db import connection
from mission_control.media_native import capability
from mission_control.managed_media_store import Media
from mission_control.video_edit_projects import Projects
from mission_control.video_edit_jobs import EditRenders, artifact_file
from mission_control.worker import run_once, jobs
import tests.test_drive_accounts as account_fixtures
import tests.test_managed_media_stitch as stitch_fixtures


def raw_metadata(raw, file_id='clip_red', version='1'):
    return dict(id=file_id,name=file_id+'.mp4',mimeType='video/mp4',size=str(len(raw)),version=version,
                md5Checksum=hashlib.md5(raw).hexdigest(),trashed=False,capabilities={'canDownload':True})


class DriveBlobTests(unittest.TestCase):
    def test_metadata_closed_blob_shape_and_exact_bounds(self):
        raw=raw_metadata(b'synthetic')
        self.assertEqual(contract.metadata(raw,'clip_red')['bytes'],9)
        self.assertEqual(contract.blob_size('67108864'),67108864)
        self.assertEqual(contract.blob_version('123'),'123')
        self.assertEqual(contract.checksum('a'*32),'a'*32)
        self.assertIsNone(contract.download_capability(False,{'canDownload':True}))
        self.assertEqual(contract.video_filename('original.mp4','video/mp4'),'original.mp4')
        for update in (dict(id='other'),dict(mimeType='application/vnd.google-apps.document'),
                       dict(trashed=True),dict(capabilities={'canDownload':False}),dict(capabilities={'canDownload':1}),
                       dict(size='67108865'),dict(size=True),dict(size='01'),dict(size='0'),dict(version=1),
                       dict(name='../clip.mp4'),dict(name='clip.webm'),dict(md5Checksum='A'*32),dict(extra='untrusted')):
            with self.subTest(update=update),self.assertRaises(Invalid):contract.metadata({**raw,**update},'clip_red')

    def test_destination_never_accepts_supplied_urls_multiple_ids_or_path_query_injection(self):
        self.assertTrue(transport.destination('clip_red').startswith('https://www.googleapis.com/drive/v3/files/clip_red?fields='))
        self.assertEqual(transport.destination('clip_red',True),'https://www.googleapis.com/drive/v3/files/clip_red?alt=media')
        for file_id in ('https://foreign.invalid/video','a,b','../other','a?key=x','a#fragment',''):
            with self.subTest(file_id=file_id),self.assertRaises(Invalid):transport.destination(file_id)

    def test_metadata_fixed_get_duplicate_free_size_and_json_rejections(self):
        with patch.object(transport,'report_bytes',return_value=json.dumps(raw_metadata(b'synthetic')).encode())as call:
            self.assertEqual(transport.read_metadata('clip_red','synthetic-token')['id'],'clip_red')
        request,timeout=call.call_args.args;self.assertEqual(timeout,15);self.assertEqual(request.get_method(),'GET')
        self.assertEqual(request.get_header('Authorization'),'Bearer synthetic-token')
        for raw in (b'x'*8193,b'{"id":"a","id":"b"}',b'null',b'\xff'):
            with self.subTest(raw=raw[:40]),patch.object(transport,'report_bytes',return_value=raw),self.assertRaises(Invalid):transport.read_metadata('clip_red','synthetic-token')

    def test_download_exact_bytes_no_redirect_fixed_timeout_and_checksum(self):
        raw=b'synthetic-original';selected=contract.metadata(raw_metadata(raw),'clip_red')
        class Response(io.BytesIO):status=200
        with patch.object(transport,'build_opener')as opener:
            opener.return_value.open.return_value=Response(raw)
            calls=[];self.assertEqual(transport.download(selected,'synthetic-token',lambda:calls.append('alive')),raw)
        self.assertGreater(len(calls),2);self.assertIsInstance(opener.call_args.args[0],transport.NoRedirect)
        request=opener.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url,'https://www.googleapis.com/drive/v3/files/clip_red?alt=media')
        self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],15)
        for bad in (raw[:-1],raw+b'x',b'X'*len(raw)):
            with self.subTest(bad=bad),patch.object(transport,'build_opener')as opener:
                opener.return_value.open.return_value=Response(bad)
                with self.assertRaises(Invalid):transport.download(selected,'synthetic-token',lambda:None)

    def test_read_chunks_rejects_deadline_partial_and_excess_and_checks_cancellation(self):
        self.assertEqual(transport.read_chunks(io.BytesIO(b'ab'),2,time.monotonic()+120,lambda:None),b'ab')
        with self.assertRaises(Invalid):transport.read_chunks(io.BytesIO(b'ab'),2,0,lambda:None)
        with self.assertRaises(Invalid):transport.read_chunks(io.BytesIO(b'a'),2,time.monotonic()+120,lambda:None)
        with self.assertRaises(Invalid):transport.read_chunks(io.BytesIO(b'abc'),2,time.monotonic()+120,lambda:None)
        def stop():raise Invalid('Synthetic cancellation')
        with self.assertRaises(Invalid):transport.read_chunks(io.BytesIO(b'ab'),2,time.monotonic()+120,stop)


class DriveMediaTests(unittest.TestCase):
    start=account_fixtures.DriveAccountTests.start
    candidate=account_fixtures.DriveAccountTests.candidate
    adopt=account_fixtures.DriveAccountTests.adopt
    review=stitch_fixtures.ManagedStitchTests.review
    definition=stitch_fixtures.ManagedStitchTests.definition
    save=stitch_fixtures.ManagedStitchTests.save
    queue=stitch_fixtures.ManagedStitchTests.queue

    def setUp(self):
        account_fixtures.DriveAccountTests.setUp(self)
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'locale':'en-US'},app['version'])
        self.version=self.store.app('sample-one')['version'];self.root=Path(self.folder.name)
        self.status=self.adopt();self.importer=Importer(self.store,8768);self.media=Media(self.store)
        self.projects=Projects(self.store);self.renders=EditRenders(self.store)
        with connection(self.store.path)as db:
            db.execute('INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)',('sample-one','owner','owner','OWNER','ACTIVE',1,now(),'owner'))
        self.originals={}
        for file_id,color,tone in [('clip_red','red',440),('clip_blue','blue',880)]:
            path=self.root/(file_id+'.mp4')
            subprocess.run([capability()['tools']['ffmpeg'],'-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=30:d=2',
                '-f','lavfi','-i',f'sine=frequency={tone}:sample_rate=48000:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)],capture_output=True,check=True,timeout=30)
            self.originals[file_id]=path.read_bytes()

    def body(self,file_id='clip_red',key='drive-original'):
        return dict(connection_id=self.status['id'],connection_version=self.status['version'],file_id=file_id,
                    manifest_version=self.version,request_key=key)

    def imported(self,body=None,download=None,metadata=None,account=None):
        value=body or self.body()
        read=metadata or (lambda file_id,bearer:contract.metadata(raw_metadata(self.originals[file_id],file_id),file_id))
        fetch=download or (lambda selected,bearer,alive:self.originals[selected['id']])
        identity=account or (lambda _:dict(permission_id='synthetic-account-one'))
        with patch('mission_control.drive_media.read_account',side_effect=identity), \
             patch.object(transport,'read_metadata',side_effect=read),patch.object(transport,'download',side_effect=fetch):
            return self.importer.import_file('sample-one',value)

    def test_actual_original_hash_provenance_replay_and_separate_owner_reuse(self):
        imported=self.imported();raw=self.originals['clip_red']
        self.assertEqual(imported['source_sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(imported['provenance']['kind'],'GOOGLE_DRIVE');self.assertEqual(imported['provenance']['file_version'],'1')
        self.assertEqual(imported['provenance']['permission_id'],'synthetic-account-one')
        self.assertEqual(imported['rights_status'],'UNKNOWN');self.assertFalse(imported['reuse_available'])
        item,original=self.media.original('sample-one',imported['id'],'owner')
        self.assertEqual(original,raw);self.assertEqual(item['source_integrity'],'VERIFIED')
        self.assertEqual(self.imported()['id'],imported['id']);self.assertEqual(len(self.media.list('sample-one')['items']),1)
        allowed=self.review(imported,'ALLOWED');self.assertTrue(allowed['reuse_available'])
        self.assertEqual(self.media.read('sample-one',imported['id'])['provenance'],imported['provenance'])
        self.review(allowed,'REVOKED');self.assertFalse(self.media.read('sample-one',imported['id'])['reuse_available'])

    def test_changed_metadata_account_or_disconnected_access_cannot_commit(self):
        calls=[]
        def changed(file_id,bearer):
            calls.append(file_id);return contract.metadata(raw_metadata(self.originals[file_id],file_id,str(len(calls))),file_id)
        with self.assertRaises(Invalid):self.imported(metadata=changed)
        with self.assertRaises(Invalid):self.imported(account=lambda _:dict(permission_id='foreign-account'))
        def disconnect(selected,bearer,alive):
            self.connections.disconnect('sample-one',dict(connection_id=self.status['id'],version=self.status['version'],confirm_disconnect=True))
            return self.originals[selected['id']]
        with self.assertRaises(Invalid):self.imported(download=disconnect)
        self.assertEqual(self.media.list('sample-one')['items'],[])

    def test_unselected_foreign_stale_and_expired_requests_never_download(self):
        for update in (dict(file_id='unselected'),dict(connection_version=2),dict(manifest_version=2),dict(connection_version=True)):
            with self.subTest(update=update),patch.object(transport,'download')as download,self.assertRaises(Invalid):self.importer.import_file('sample-one',{**self.body(),**update})
            download.assert_not_called()
        with patch.object(transport,'download')as download,self.assertRaises(Invalid):self.importer.import_file('sample-two',self.body())
        download.assert_not_called()
        with patch('mission_control.drive_connection_state.time.time',return_value=self.status['expires']+1),patch.object(transport,'download')as download,self.assertRaises(Invalid):self.importer.import_file('sample-one',self.body())
        download.assert_not_called()

    def test_missing_protected_access_token_requires_reconnect_before_any_provider_call(self):
        from tests.test_measurement_connectors import FakeVault
        for key in list(FakeVault.values):
            if key.endswith('/access_token'):del FakeVault.values[key]
        self.assertEqual(self.connections.status('sample-one')['status'],'RECONNECT_REQUIRED')
        self.assertEqual(self.connections.readiness(self.connections.row('sample-one')),'RECONNECT_REQUIRED')
        with patch('mission_control.drive_media.read_account')as account,patch.object(transport,'download')as download,self.assertRaises(Invalid):self.importer.import_file('sample-one',self.body())
        account.assert_not_called();download.assert_not_called()

    def test_same_request_key_changed_provider_version_is_rejected_and_local_upload_cannot_spoof(self):
        imported=self.imported()
        def changed(file_id,bearer):return contract.metadata(raw_metadata(self.originals[file_id],file_id,'2'),file_id)
        with self.assertRaises(Invalid):self.imported(metadata=changed)
        self.assertEqual(len(self.media.list('sample-one')['items']),1)
        with self.assertRaises(Invalid):self.media.upload('sample-one','local.mp4',self.originals['clip_red'],dict(manifest_version=self.version,request_key='spoof',provenance=imported['provenance']))

    def test_disconnect_during_final_source_write_rolls_back_library_and_owned_file(self):
        from mission_control import managed_media_store as managed
        original=managed._write_exclusive
        def changed(path,raw,alive):
            result=original(path,raw,alive)
            self.importer.guard=lambda row:(_ for _ in ()).throw(Invalid('Synthetic access revocation'))
            return result
        with patch.object(managed,'_write_exclusive',side_effect=changed),self.assertRaises(Invalid):self.imported()
        self.assertEqual(self.media.list('sample-one')['items'],[])
        self.assertEqual(list((self.root/'managed-media').rglob('*.mp4')),[])

    def test_changed_account_after_download_and_invalid_video_bytes_leave_no_original(self):
        count=[]
        def account(_):
            count.append(1);return dict(permission_id='synthetic-account-one'if len(count)==1 else'other-account')
        with self.assertRaises(Invalid):self.imported(account=account)
        raw=b'not a valid video'
        def metadata(file_id,bearer):return contract.metadata(raw_metadata(raw,file_id),file_id)
        with self.assertRaises(Invalid):self.imported(metadata=metadata,download=lambda *_:raw)
        self.assertEqual(self.media.list('sample-one')['items'],[])

    def test_two_imported_reviewed_sources_render_in_selected_order_with_sound(self):
        self.clips=[self.review(self.imported(self.body(file_id,file_id)),'ALLOWED')for file_id in ('clip_red','clip_blue')]
        project=self.save();queued=self.queue(project);self.assertTrue(run_once(self.store))
        job=next(row for row in jobs(self.store,'sample-one')if row['id']==queued['id']);self.assertEqual(job['status'],'SUCCEEDED',job['result'])
        path,data=artifact_file(self.store,'sample-one',job['result']['render_id'])
        self.assertTrue(data['artifact']['metadata']['audio']);self.assertAlmostEqual(data['artifact']['metadata']['duration_seconds'],2,delta=.06)
        for at,channel in ((.4,0),(1.4,2)):
            pixels=stitch_fixtures.frame(path,at);offset=(24*48+24)*3;means=list(pixels[offset:offset+3])
            self.assertGreater(means[channel],230);self.assertLess(means[2-channel],10)
        import array,math
        for at,target,other in ((.3,440,880),(1.3,880,440)):
            result=subprocess.run([capability()['tools']['ffmpeg'],'-v','error','-ss',str(at),'-i',str(path),'-t','0.2','-ac','1','-ar','48000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=30)
            samples=array.array('f');samples.frombytes(result.stdout)
            def energy(hz):return abs(sum(x*complex(math.cos(2*math.pi*hz*i/48000),math.sin(2*math.pi*hz*i/48000))for i,x in enumerate(samples)))
            self.assertGreater(energy(target),10*energy(other))
        print('DRIVE_IMPORTED_STITCH '+json.dumps(dict(sources=[row['source_sha256']for row in self.clips],artifact_sha256=data['artifact']['sha256'],picture_and_tone_order='PASS')))
        self.review(self.clips[0],'REVOKED')
        with self.assertRaises(Invalid):artifact_file(self.store,'sample-one',job['result']['render_id'])
