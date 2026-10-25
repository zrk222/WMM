"""Actual encoded edits, decoded output differences, current source proofs and recovery."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.media_native import capability
from mission_control.creative_rendering import artifact_file as source_file
from mission_control.service import Service
from mission_control.video_edit_jobs import EditRenders, artifact_file
from mission_control.video_edit_rendering import validate, render, clip_filters
from mission_control.video_edit_projects import Projects
from mission_control.worker import jobs, run_once
from mission_control.workflow_telemetry import monitor
from tests.test_video_edit_projects import ProjectFixture, APP


def frame(path, at=0):
    """Decode actual RGB pixels; container hashes alone cannot prove visual changes."""
    result = subprocess.run([capability()['tools']['ffmpeg'], '-v', 'error', '-ss', str(at), '-i', str(path),
                             '-vf', 'scale=48:48', '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', 'pipe:1'],
                            capture_output=True, timeout=30)
    assert result.returncode == 0 and len(result.stdout) == 48*48*3
    return result.stdout


class EditRenderFixture(ProjectFixture):
    def setup_edit(self):
        self.setup_project()
        self.data['clips'][0].update(in_frame=0, out_frame=48)
        self.project = self.projects.save(APP, self.create_body())
        self.renders = EditRenders(self.store)

    def queue(self, key='edit-render', project=None):
        project = project or self.project
        return self.renders.queue(APP, dict(data=dict(project_id=project['id'], revision=project['revision'],
                                                      project_hash=project['hash']), request_key=key))

    def run_video(self, key, value):
        current = self.projects.read(APP, 'test-project')
        self.project = self.projects.save(APP, dict(id=current['id'], revision=current['revision'],
            manifest_version=self.store.app(APP)['version'], data=value, request_key='save-'+key))
        queued = self.queue(key)
        self.assertTrue(run_once(self.store))
        job = next(row for row in jobs(self.store, APP) if row['id'] == queued['id'])
        self.assertEqual(job['status'], 'SUCCEEDED', job['result'])
        return artifact_file(self.store, APP, job['result']['render_id'])


class EditRenderTests(EditRenderFixture, unittest.TestCase):
    def setUp(self):self.setup_edit()
    def tearDown(self):self.tmp.cleanup()

    def test_edit_output_actual_pixels_for_crop_orientation_fit_background_and_color(self):
        baseline, data = self.run_video('baseline', deepcopy(self.data));pixels = frame(baseline)
        variants = []
        for key, value in (('rotation', 90), ('flip_y', True), ('flip_x', True)):
            edited = deepcopy(self.data);edited['clips'][0]['transform'][key] = value;variants.append((key, edited))
        edited=deepcopy(self.data);edited['clips'][0]['transform']['crop'].update(width=5000,height=5000);variants.append(('crop',edited))
        edited=deepcopy(self.data);edited['output']='SQUARE';edited['clips'][0]['transform']['fit']='COVER';variants.append(('square-cover',edited))
        edited=deepcopy(self.data);edited['output']='LANDSCAPE';edited['clips'][0]['transform']['background']='#FF0000';variants.append(('landscape-bg',edited))
        for key, value in (('brightness', 25), ('contrast', 150), ('saturation', 0)):
            edited=deepcopy(self.data);edited['clips'][0]['effects'][key]=value;variants.append((key,edited))
        for key, edited in variants:
            with self.subTest(control=key):
                output, data = self.run_video(key, edited)
                self.assertNotEqual(frame(output), pixels)
                self.assertEqual(validate(output, edited), data['artifact'])
                self.assertEqual(data['publication'], 'NOT_RUN')
        self.assertEqual(data['cost'], dict(model_api_charge_minor=0, machine_cost='NOT_MEASURED'))

    def test_edit_output_trim_order_speed_and_actual_live_steps(self):
        value=deepcopy(self.data)
        first=value['clips'][0];first.update(in_frame=24,out_frame=72,speed_percent=200)
        second=deepcopy(first);second.update(id='clip-two',in_frame=240,out_frame=288,speed_percent=100)
        value['clips']=[first,second]
        reached=[]
        def active(*args,**kwargs):
            observed=monitor(self.store,APP)['runs'][0]
            reached.append(observed['latest']['code'])
            return render(*args,**kwargs)
        with patch('mission_control.video_edit_jobs.render',side_effect=active):
            output,data=self.run_video('timeline',value)
        self.assertEqual(reached,['EDIT_ENCODING'])
        self.assertAlmostEqual(data['artifact']['metadata']['duration_seconds'],3,places=2)
        events=monitor(self.store,APP)['runs'][0]['events']
        self.assertEqual([r['code'] for r in events],['STARTED','EDIT_PROOF','EDIT_SOURCES','EDIT_ENCODING','EDIT_COMMIT','SUCCEEDED'])
        first_pixels=frame(output,0.5);second_pixels=frame(output,1.5)
        self.assertNotEqual(first_pixels,second_pixels)
        source=source_file(self.store,APP,self.native['id'])[0]
        expected_first=frame(source,2.0);expected_second=frame(source,10.5)
        self.assertLess(sum(abs(a-b) for a,b in zip(first_pixels,expected_first))/len(first_pixels),3)
        self.assertLess(sum(abs(a-b) for a,b in zip(second_pixels,expected_second))/len(second_pixels),3)
        value['clips'].reverse()
        reordered,_=self.run_video('reordered',value)
        self.assertNotEqual(frame(reordered,0.5),first_pixels)

    def test_edit_jobs_idempotency_cancellation_and_current_history(self):
        queued=self.queue();self.assertEqual(self.queue()['id'],queued['id'])
        Service(self.store).cancel(APP,queued['id'])
        with patch('mission_control.video_edit_jobs.render') as encode:
            self.assertFalse(run_once(self.store));encode.assert_not_called()
        self.assertEqual(self.renders.list(APP)['items'],[])
        self.assertEqual(next(j for j in jobs(self.store,APP) if j['id']==queued['id'])['status'],'CANCELLED')

    def test_edit_proof_project_changed_after_encoding_prevents_saved_artifact(self):
        queued=self.queue()
        def change(*args,**kwargs):
            result=render(*args,**kwargs)
            self.projects.edit(APP,'test-project',dict(revision=1,manifest_version=self.store.app(APP)['version'],
                command=dict(operation='trim',clip_id='clip-one',in_frame=0,out_frame=24),request_key='intervening-edit'))
            return result
        with patch('mission_control.video_edit_jobs.render',side_effect=change):self.assertTrue(run_once(self.store))
        self.assertEqual(next(j for j in jobs(self.store,APP) if j['id']==queued['id'])['status'],'BLOCKED')
        self.assertEqual(self.renders.list(APP)['items'],[])
        self.assertEqual(list((self.store.path.parent/'edited-videos').rglob('*.mp4')),[])

    def test_edit_proof_rights_withdrawal_after_encoding_and_cancel_remove_temporary_media(self):
        queued=self.queue()
        def withdraw(*args,**kwargs):
            result=render(*args,**kwargs)
            with connection(self.store.path) as db:
                identity=self.brief['data']['definition']['asset_ids'][0]
                row=db.execute('SELECT data FROM records WHERE app_id=? AND id=?',(APP,identity)).fetchone()
                value=json.loads(row['data']);value['rights_cleared']=False
                db.execute('UPDATE records SET data=?,version=version+1 WHERE app_id=? AND id=?',(json.dumps(value),APP,identity))
            return result
        with patch('mission_control.video_edit_jobs.render',side_effect=withdraw):self.assertTrue(run_once(self.store))
        self.assertEqual(self.renders.list(APP)['items'],[])
        self.assertEqual(list((self.store.path.parent/'edited-videos').rglob('*.mp4')),[])

    def test_edit_proof_queue_hash_tamper_foreign_and_frozen_inputs_are_rejected(self):
        for data in (dict(project_id='test-project',revision=1,project_hash='0'*64),
                     dict(project_id='test-project',revision=1,project_hash=self.project['hash'],path='../private')):
            with self.assertRaises(Invalid):self.renders.queue(APP,dict(data=data,request_key='invalid'))
        with self.assertRaises(Invalid):self.renders.queue('sample-two',dict(data=dict(project_id='test-project',revision=1,project_hash=self.project['hash']),request_key='foreign'))
        queued=self.queue()
        with connection(self.store.path) as db:
            value=deepcopy(queued['data']);value['project']['definition']['clips'][0]['effects']['brightness']=50
            db.execute('UPDATE jobs SET data=? WHERE id=?',(json.dumps(value),queued['id']))
        with patch('mission_control.video_edit_jobs.render') as encode:
            self.assertTrue(run_once(self.store));encode.assert_not_called()
        self.assertEqual(self.renders.list(APP)['items'],[])

    def test_edit_jobs_retained_artifact_current_head_bytes_and_foreign_access(self):
        output,data=self.run_video('first',deepcopy(self.data))
        row=self.renders.list(APP)['items'][0]
        self.assertEqual(row['status'],'CURRENT')
        with self.assertRaises(Invalid):artifact_file(self.store,'sample-two',row['id'])
        with self.assertRaises(Invalid):artifact_file(self.store,APP,'../private')
        self.projects.edit(APP,'test-project',dict(revision=self.project['revision'],manifest_version=self.store.app(APP)['version'],
            command=dict(operation='trim',clip_id='clip-one',in_frame=0,out_frame=24),request_key='later-edit'))
        self.assertEqual(self.renders.list(APP)['items'][0]['status'],'STALE_OR_UNAVAILABLE')
        self.assertEqual(artifact_file(self.store,APP,row['id'])[0],output)
        output.write_bytes(b'changed')
        with self.assertRaises(Invalid):artifact_file(self.store,APP,row['id'])

    def test_edit_jobs_running_cancellation_removes_all_uncommitted_media(self):
        queued=self.queue()
        def cancel(*args,**kwargs):
            result=render(*args,**kwargs)
            Service(self.store).cancel(APP,queued['id'])
            return result
        with patch('mission_control.video_edit_jobs.render',side_effect=cancel):self.assertTrue(run_once(self.store))
        self.assertEqual(next(j for j in jobs(self.store,APP) if j['id']==queued['id'])['status'],'CANCELLED')
        self.assertEqual(self.renders.list(APP)['items'],[])
        self.assertEqual(list((self.store.path.parent/'edited-videos').rglob('*.mp4')),[])

    def test_edit_proof_tampered_saved_project_data_cannot_reuse_its_old_hash(self):
        with connection(self.store.path) as db:
            row=db.execute('SELECT data FROM video_project_revisions WHERE app_id=? AND id=?',(APP,'test-project')).fetchone()
            value=json.loads(row['data']);value['definition']['clips'][0]['effects']['brightness']=50
            db.execute('UPDATE video_project_revisions SET data=? WHERE app_id=? AND id=?',(json.dumps(value),APP,'test-project'))
        with self.assertRaises(Invalid):self.queue()

    def test_edit_proof_changed_runtime_blocks_job_before_encoder(self):
        queued=self.queue()
        with patch('mission_control.video_edit_jobs.runtime_identity',return_value=dict(status='READY',sha256={'ffmpeg':'0'*64})), patch('mission_control.video_edit_jobs.render') as encode:
            self.assertTrue(run_once(self.store));encode.assert_not_called()
        self.assertEqual(self.renders.list(APP)['items'],[])

    def test_copy_sources_preserves_actual_hash_and_clip_filters_rejects_untyped_code(self):
        queued=self.queue()
        with tempfile.TemporaryDirectory() as directory:
            copied=self.renders.copy_sources(Path(directory),APP,queued['data'])
            self.assertEqual(len(copied),1)
            self.assertEqual(hashlib.sha256(next(iter(copied.values())).read_bytes()).hexdigest(),self.data['clips'][0]['source']['sha256'])
        current=deepcopy(self.data['clips'][0]);current['transform']['background']='movie=http://unsafe'
        with self.assertRaises(Invalid):clip_filters(current,'PORTRAIT')
        with self.assertRaises(Invalid):clip_filters(self.data['clips'][0],'arbitrary-filter')
