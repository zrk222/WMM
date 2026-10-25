"""Real full-duration owned media, decoded frames/sound and unchanged strict bounds."""
from copy import deepcopy
import array
import hashlib
import json
import math
import subprocess
import unittest
from mission_control.common import Invalid
from mission_control.media_native import capability
from mission_control import video_edit_rendering as renderer
from mission_control.video_edit_contract import definition,timing
from mission_control.video_edit_jobs import artifact_file
from mission_control.worker import run_once,jobs
from mission_control.managed_media_validation import media_metadata,PROBE_TIMEOUT_SECONDS
from tests import test_managed_media_stitch as fixture
from tests.test_managed_media_validation import probed
from tests.test_video_edit_render import frame


class MediaDurationTests(unittest.TestCase):
    setUp=fixture.ManagedStitchTests.setUp
    review=fixture.ManagedStitchTests.review
    definition=fixture.ManagedStitchTests.definition
    save=fixture.ManagedStitchTests.save
    queue=fixture.ManagedStitchTests.queue

    def full_source(self):
        path=self.root/'full-source.mp4';tools=capability()['tools']
        subprocess.run([tools['ffmpeg'],'-v','error','-f','lavfi','-i','color=red:s=160x90:r=24:d=60',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=60','-t','60',
            '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True,timeout=60)
        row=self.media.upload('sample-one',path.name,path.read_bytes(),dict(manifest_version=self.version,request_key='full-source'))
        return self.review(row,'ALLOWED')

    def completed(self,project,key):
        queued=self.renders.queue('sample-one',dict(data=dict(project_id=project['id'],revision=project['revision'],project_hash=project['hash']),request_key=key))
        self.assertTrue(run_once(self.store))
        job=next(row for row in jobs(self.store,'sample-one')if row['id']==queued['id'])
        self.assertEqual(job['status'],'SUCCEEDED',job['result'])
        self.last_render_id=job['result']['render_id']
        path,data=artifact_file(self.store,'sample-one',job['result']['render_id'])
        self.assertEqual(data['artifact']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(data['request']['selection']['project_hash'],project['hash'])
        print('DURATION_ARTIFACT '+json.dumps(dict(project_hash=project['hash'],revision=project['revision'],sha256=data['artifact']['sha256'])))
        return path,data

    def decoded_boundary(self,path,audio):
        result=subprocess.run([capability()['tools']['ffprobe'],'-v','error','-count_frames','-show_entries',
            'stream=codec_type,nb_read_frames,start_time,duration:format=duration','-of','json',str(path)],capture_output=True,check=True,timeout=60)
        value=json.loads(result.stdout);video=next(r for r in value['streams']if r['codec_type']=='video')
        self.assertEqual(int(video['nb_read_frames']),1440)
        self.assertAlmostEqual(float(video['duration']),60,places=3)
        self.assertLessEqual(abs(float(video['start_time'])),.001)
        self.assertLessEqual(float(value['format']['duration']),60)
        self.assertEqual(any(r['codec_type']=='audio'for r in value['streams']),audio)
        for stream in value['streams']:self.assertLessEqual(float(stream['duration']),60)
        print('DURATION_DECODE '+json.dumps(dict(audio=audio,probe=value)))
        return value

    def tone(self,path,at,frequency,other):
        result=subprocess.run([capability()['tools']['ffmpeg'],'-v','error','-ss',str(at),'-i',str(path),
            '-t','0.2','-ac','1','-ar','48000','-f','f32le','pipe:1'],capture_output=True,check=True,timeout=30)
        samples=array.array('f');samples.frombytes(result.stdout)
        def energy(hz):return abs(sum(x*complex(math.cos(2*math.pi*hz*i/48000),math.sin(2*math.pi*hz*i/48000))for i,x in enumerate(samples)))
        self.assertTrue(samples)
        wanted,unwanted=energy(frequency),energy(other)
        self.assertGreater(wanted,10*unwanted)
        print('DURATION_TONE '+json.dumps(dict(at=at,frequency=frequency,energy=wanted,other=other,other_energy=unwanted)))

    def test_queued_full_duration_audio_and_explicit_mute_produce_all1440_decoded_frames(self):
        row=self.full_source();data=self.definition();data['clips']=data['clips'][:1]
        data['clips'][0].update(source=dict(kind='MANAGED',id=row['id'],sha256=row['source_sha256']),in_frame=0,out_frame=1440,audio='RETAIN')
        project=self.save(data);path,artifact=self.completed(project,'full-audio');first_id=self.last_render_id
        self.decoded_boundary(path,True);self.tone(path,.1,440,880);self.tone(path,59.7,440,880)
        self.assertEqual(artifact['artifact']['metadata']['duration_seconds'],60)
        data['clips'][0]['audio']='MUTE'
        muted=self.projects.save('sample-one',dict(id=project['id'],revision=project['revision'],manifest_version=self.version,data=data,request_key='mute-full'))
        path,_=self.completed(muted,'full-muted');self.decoded_boundary(path,False)
        self.review(row,'REVOKED')
        for identity in (first_id,self.last_render_id):
            with self.subTest(identity=identity),self.assertRaises(Invalid):artifact_file(self.store,'sample-one',identity)

    def test_stitched60_seconds_preserves_selected_picture_and_tone_order(self):
        data=self.definition();originals=deepcopy(data['clips']);data['clips']=[]
        for i in range(8):
            item=deepcopy(originals[i%2]);item.update(id='clip-'+str(i),in_frame=0,out_frame=48,speed_percent=25 if i<7 else 50)
            data['clips'].append(item)
        self.assertEqual(timing(definition(data))['total_frames'],1440)
        project=self.save(data);path,_=self.completed(project,'full-stitch');self.decoded_boundary(path,True)
        for at,channel,tone,other in ((.4,0,440,880),(8.4,2,880,440),(56.4,2,880,440)):
            pixels=frame(path,at);offset=(24*48+24)*3;color=list(pixels[offset:offset+3])
            self.assertGreater(color[channel],230)
            self.assertLess(color[2-channel],10)
            self.tone(path,at,tone,other)

    def test_concat_argv_compiles_fixed_priming_correction_only_for_audio(self):
        method=getattr(renderer,'concat_argv',None);self.assertTrue(callable(method))
        args=method(capability(),True)
        self.assertAlmostEqual(float(args[args.index('-output_ts_offset')+1]),-1024/48000,places=10)
        self.assertEqual(args[args.index('-avoid_negative_ts')+1],'disabled')
        self.assertEqual(args[args.index('-protocol_whitelist')+1],'file,pipe')
        self.assertEqual(args[-1],'video.mp4')
        self.assertNotIn('-output_ts_offset',method(capability(),False))
        with self.assertRaises(Invalid):method(capability(),'RETAIN')

    def test_imported_duration_and_timeline_limits_stay_strict(self):
        for duration in ('60.000001','60.021333','61'):
            value=probed();value['format']['duration']=duration
            with self.subTest(duration=duration),self.assertRaises(Invalid):media_metadata(value)
        value=probed();value['format']['duration']='60';value['streams'][1]['duration']='60.021333'
        with self.assertRaises(Invalid):media_metadata(value)
        data=self.definition();item=deepcopy(data['clips'][0]);item.update(in_frame=0,out_frame=48,speed_percent=25)
        data['clips']=[dict(deepcopy(item),id='too-long-'+str(i))for i in range(8)]
        with self.assertRaises(Invalid):definition(data)
        self.assertEqual(renderer.RENDER_SECONDS,180)
        self.assertEqual(PROBE_TIMEOUT_SECONDS,15)
