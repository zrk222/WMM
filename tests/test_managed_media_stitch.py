"""Actual uploaded picture/audio stitching and current owner reuse boundaries."""
from copy import deepcopy
from pathlib import Path
import json
import subprocess
import tempfile
import unittest
from mission_control.store import Store
from mission_control.db import connection
from mission_control.common import Invalid, now
from mission_control.managed_media_store import Media
from mission_control.media_native import capability
from mission_control.video_edit_projects import Projects
from mission_control.video_edit_jobs import EditRenders, artifact_file
from mission_control.worker import run_once, jobs
from tests.test_video_edit_projects import project_data
from tests.test_video_edit_render import frame


class ManagedStitchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.store=Store(self.root/'state.sqlite',seed=False)
        for app in ('sample-one','sample-two'):
            self.store.save_app(app,dict(name='Synthetic app',locale='en-US',release='test',currency='USD'))
        self.version=self.store.app('sample-one')['version'];self.media=Media(self.store)
        with connection(self.store.path) as db:
            db.execute('INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)',('sample-one','owner','owner','OWNER','ACTIVE',1,now(),'owner'))
        self.clips=[]
        for index,(color,tone) in enumerate((('red',440),('blue',880))):
            path=self.root/f'input{index}.mp4'
            cmd=[capability()['tools']['ffmpeg'],'-v','error','-f','lavfi','-i',f'color={color}:s=160x90:r=30:d=2','-f','lavfi','-i',f'sine=frequency={tone}:sample_rate=48000:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(path)]
            subprocess.run(cmd,check=True,capture_output=True,timeout=30)
            row=self.media.upload('sample-one',path.name,path.read_bytes(),dict(manifest_version=self.version,request_key=f'upload-{index}'))
            self.clips.append(self.review(row,'ALLOWED'))
        self.projects=Projects(self.store);self.renders=EditRenders(self.store)

    def review(self,row,status):
        return self.media.review('sample-one',row['id'],dict(expected_version=row['review_version'],manifest_version=self.version,source_sha256=row['source_sha256'],status=status,basis='OWNED',evidence='Synthetic fixture recorded here.'),dict(principal='owner'))

    def definition(self):
        data=project_data(self.clips[0]['id'],self.clips[0]['source_sha256']);data['output']='SQUARE'
        first=data['clips'][0];first.update(source=dict(kind='MANAGED',id=self.clips[0]['id'],sha256=self.clips[0]['source_sha256']),out_frame=24,audio='RETAIN')
        second=deepcopy(first);second.update(id='clip-two',source=dict(kind='MANAGED',id=self.clips[1]['id'],sha256=self.clips[1]['source_sha256']),in_frame=24,out_frame=48)
        data['clips']=[first,second];return data

    def save(self,data=None):
        return self.projects.save('sample-one',dict(id='stitch-project',revision=0,manifest_version=self.version,data=data or self.definition(),request_key='save-project'))

    def queue(self,project):
        return self.renders.queue('sample-one',dict(data=dict(project_id=project['id'],revision=project['revision'],project_hash=project['hash']),request_key='render-stitch'))

    def test_actual_ordered_picture_and_audio_survive_normalized_trim(self):
        project=self.save();queued=self.queue(project);self.assertTrue(run_once(self.store))
        job=next(r for r in jobs(self.store,'sample-one') if r['id']==queued['id'])
        self.assertEqual(job['status'],'SUCCEEDED',job['result'])
        path,data=artifact_file(self.store,'sample-one',job['result']['render_id'])
        self.assertTrue(data['artifact']['metadata']['audio'])
        self.assertAlmostEqual(data['artifact']['metadata']['duration_seconds'],2,delta=.06)
        for at,channel in ((.4,0),(1.4,2)):
            pixels=frame(path,at);offset=(24*48+24)*3;means=list(pixels[offset:offset+3])
            self.assertGreater(means[channel],230)
            self.assertLess(means[2-channel],10)
        import array,math
        for at,target,other in ((.3,440,880),(1.3,880,440)):
            result=subprocess.run([capability()['tools']['ffmpeg'],'-v','error','-ss',str(at),'-i',str(path),'-t','0.2','-ac','1','-ar','48000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=30)
            samples=array.array('f');samples.frombytes(result.stdout)
            def energy(hz):
                return abs(sum(x*complex(math.cos(2*math.pi*hz*i/48000),math.sin(2*math.pi*hz*i/48000))for i,x in enumerate(samples)))
            self.assertGreater(energy(target),10*energy(other))
        self.review(self.clips[0],'REVOKED')
        with self.assertRaises(Invalid):artifact_file(self.store,'sample-one',job['result']['render_id'])

    def test_revoked_foreign_and_out_of_range_sources_cannot_save_or_queue(self):
        data=self.definition();data['clips'][0]['out_frame']=49
        with self.assertRaises(Invalid):self.save(data)
        project=self.save();self.review(self.clips[0],'REVOKED')
        with self.assertRaises(Invalid):self.queue(project)
        with self.assertRaises(Invalid):self.projects.save('sample-two',dict(id='other',revision=0,manifest_version=1,data=self.definition(),request_key='foreign'))

    def test_source_audio_muting_and_speed_are_explicit(self):
        from mission_control.video_edit_rendering import render, edit_metadata
        from mission_control.video_edit_contract import source_key
        data=self.definition();data['clips']=data['clips'][:1]
        data['clips'][0].update(in_frame=0,out_frame=48,speed_percent=200,audio='MUTE')
        row=self.clips[0];source=self.media.resolve('sample-one',row['id'],row['source_sha256'])
        folder=self.root/'muted';folder.mkdir()
        path,artifact=render(folder,data,{source_key(data['clips'][0]['source']):source},lambda:None)
        self.assertFalse(edit_metadata(path)['audio'])
        self.assertAlmostEqual(artifact['metadata']['duration_seconds'],1,delta=.05)
        data['clips'][0]['audio']='RETAIN';folder=self.root/'retained';folder.mkdir()
        path,artifact=render(folder,data,{source_key(data['clips'][0]['source']):source},lambda:None)
        self.assertTrue(edit_metadata(path)['audio'])
        self.assertAlmostEqual(artifact['metadata']['duration_seconds'],1,delta=.05)

    def test_revocation_during_encoding_prevents_committed_derivative(self):
        from unittest.mock import patch
        from mission_control.video_edit_rendering import render as actual_render
        project=self.save();queued=self.queue(project)
        def revoke(folder,value,sources,alive):
            self.review(self.clips[0],'REVOKED')
            return actual_render(folder,value,sources,alive)
        with patch('mission_control.video_edit_jobs.render',side_effect=revoke):
            self.assertTrue(run_once(self.store))
        job=next(r for r in jobs(self.store,'sample-one')if r['id']==queued['id'])
        self.assertEqual(job['status'],'BLOCKED')
        self.assertEqual(self.renders.list('sample-one')['items'],[])

    def test_derivative_snapshot_captures_exact_original_and_rejects_unverified_capture(self):
        from mission_control.managed_media_store import derivative_snapshot
        row=self.clips[0]
        with connection(self.store.path) as db:
            view,raw=derivative_snapshot(db,self.store,'sample-one',row['id'],row['source_sha256'],capture=True)
            import hashlib
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['source_sha256'])
            self.assertEqual(view['review_version'],1)
            with self.assertRaises(Invalid):
                derivative_snapshot(db,self.store,'sample-one',row['id'],row['source_sha256'],capture=True,verify_bytes=False)

    def test_audio_filters_and_segment_argv_keep_only_selected_sound(self):
        from mission_control.video_edit_rendering import audio_filters,segment_argv
        row=self.definition()['clips'][0];row['speed_percent']=25
        filters=audio_filters(row)
        self.assertEqual(filters.count('atempo=0.5'),2)
        row['speed_percent']=400
        self.assertEqual(audio_filters(row).count('atempo=2'),2)
        row['audio']='MUTE'
        path=self.media.resolve('sample-one',self.clips[0]['id'],self.clips[0]['source_sha256'])
        args=segment_argv(capability(),row,'SQUARE',path,0,True)
        self.assertIn('anullsrc=r=48000:cl=stereo',args)
        self.assertIn('1:a:0',args)
        self.assertNotIn('0:a:0',args)

    def test_render_guard_observes_revocation_after_first_poll(self):
        from unittest.mock import patch
        project=self.save();queued=self.queue(project)
        with patch('mission_control.video_edit_jobs.heartbeat'),patch('mission_control.video_edit_jobs.time.monotonic',side_effect=[100,102]):
            guard=self.renders.render_guard(queued,None);guard()
            self.review(self.clips[0],'REVOKED')
            with self.assertRaises(Invalid):guard()
