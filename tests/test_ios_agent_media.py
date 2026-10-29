"""Real SQLite scoped-agent native media contracts; no device rendering claim."""
from datetime import datetime,timedelta,timezone
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_agent_access import NativeAgentAccess
from mission_control.ios_agent_media import NativeAgentTimeline
from mission_control.ios_studio import NativeStudio
from tests import test_ios_media_adapter as fixture
from tests import test_ios_production as production_fixture


class NativeAgentMediaTests(unittest.TestCase):
    setUp=fixture.NativeMediaTests.setUp
    verify=fixture.NativeMediaTests.verify
    creation=fixture.NativeMediaTests.creation
    adapter=fixture.NativeMediaTests.adapter
    owned=fixture.NativeMediaTests.owned
    upload=fixture.NativeMediaTests.upload
    decision=fixture.NativeMediaTests.decision
    prepare_fixture=production_fixture.NativeProductionTests.prepare_fixture

    def issue(self,operations,review=()):
        access=NativeAgentAccess(self.runtime.service,self.runtime.identities)
        grant=dict(agent_id='media-agent',manifest_version=1,operations=operations,
                   expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),max_calls=30)
        if review:grant['review_operations']=list(review)
        return json.loads(access.manage(self.session,'new-app','issue',json.dumps({'confirm_scope':True,'grant':grant}).encode()))

    def call(self,token,operation,body,app='new-app'):
        payload=json.dumps(dict(app_id=app,operation=operation,input=body)).encode()
        return json.loads(NativeAgentAccess(self.runtime.service,self.runtime.identities).call(self.session,token,payload))

    def scene(self):
        return dict(title='Synthetic',shape='PORTRAIT',scenes=[dict(text='First',seconds=1)])

    def save_scene(self,token):
        return self.call(token,'ios.scene.save',dict(project_id='scene-one',base_revision=0,manifest_version=1,request_key='save-one',scene=self.scene()))

    def start_scene(self,token,project):
        return self.call(token,'ios.scene.start',dict(project_id='scene-one',revision=project['revision'],source_hash=project['source_hash'],request_key='render-one'))

    def studio(self,action,body,inspection=None):
        return json.loads(NativeStudio(self.runtime.service,self.runtime.identities).call(self.session,'new-app',action,json.dumps(body).encode(),inspection=inspection))

    def test_scene_real_grant_prepares_native_packet_and_revocation_blocks_finish(self):
        self.runtime.create_workspace(self.session,self.creation())
        grant=self.issue(['ios.scene.save','ios.scene.start','ios.scene.inspect','ios.scene.cancel'])
        project=self.save_scene(grant['token']);started=self.start_scene(grant['token'],project)
        self.assertEqual(started['job']['status'],'PREPARED');self.assertFalse(started['packet']['execution_authority'])
        job=started['job'];request={'job_id':job['job_id'],'packet_hash':job['packet_hash']}
        self.assertEqual(self.studio('validate',request)['packet_hash'],job['packet_hash'])
        with self.assertRaises(Invalid):self.call(grant['token'],'ios.scene.finish',request)
        other=self.issue(['ios.scene.cancel'])
        with self.assertRaises(PermissionError):self.call(other['token'],'ios.scene.cancel',{'job_id':job['job_id']})
        NativeAgentAccess(self.runtime.service,self.runtime.identities).manage(self.session,'new-app','revoke',
            json.dumps({'id':grant['grant']['id'],'version':1,'confirm_revoke':True}).encode())
        with self.assertRaises(PermissionError):self.studio('validate',request)
        proof=dict(artifact_id=job['job_id'],sha256='a'*64,bytes=100,frames=24,width=720,height=1280,audio=False)
        with self.assertRaises(PermissionError):self.studio('finish',request,proof)

    def test_review_required_cannot_be_bypassed_and_completed_review_allows_validate(self):
        from mission_control.agent_checkpoints import Checkpoints
        from mission_control.review_access import Access
        self.runtime.create_workspace(self.session,self.creation())
        grant=self.issue(['ios.scene.save','ios.scene.start'],['ios.scene.start']);token=grant['token']
        project=self.save_scene(token);body=dict(project_id='scene-one',revision=1,source_hash=project['source_hash'],request_key='render-one')
        with self.assertRaises(PermissionError):self.call(token,'ios.scene.start',body)
        owner=self.runtime.identities.fresh(self.session);checker=dict(principal='github:202',login='checker')
        Access(self.runtime.service.store).save('new-app',owner,checker,dict(login='checker',role='CHECKER',status='ACTIVE',version=None))
        access=NativeAgentAccess(self.runtime.service,self.runtime.identities)
        envelope=dict(app_id='new-app',operation='ios.scene.start',input=body)
        waiting=json.loads(access.review(self.session,token,'prepare',json.dumps({'id':'review-one','envelope':envelope}).encode()))
        row=waiting['checkpoint'];approved=Checkpoints(self.runtime.service.store).approve('new-app','review-one',checker['principal'],row['revision'],row['hash'])
        result=json.loads(access.review(self.session,token,'resume',json.dumps(dict(id='review-one',app_id='new-app',revision=approved['revision'],packet_hash=approved['hash'])).encode()))
        self.assertEqual(result['result']['outcome'],'SUCCEEDED')
        job=result['result']['data']['job'];request=dict(job_id=job['job_id'],packet_hash=job['packet_hash'])
        self.assertEqual(self.studio('validate',request)['packet_hash'],job['packet_hash'])
        Access(self.runtime.service.store).save('new-app',owner,checker,dict(login='checker',role='CHECKER',status='REVOKED',version=1))
        with self.assertRaises(PermissionError):self.studio('validate',request)

    def test_timeline_queue_host_validate_source_finish_and_revocation(self):
        self.prepare_fixture();grant=self.issue(['ios.timeline.queue','ios.timeline.inspect'])
        body=dict(project_id=self.project['id'],revision=self.project['revision'],project_hash=self.project['hash'],request_key='agent-timeline')
        queued=self.call(grant['token'],'ios.timeline.queue',body);job=queued['job'];packet=queued['packet']
        self.assertEqual(job['status'],'PREPARED');self.assertNotIn('path',json.dumps(queued))
        host=NativeAgentTimeline(self.runtime.service,self.runtime.identities)
        request=dict(job_id=job['job_id'],packet_hash=job['packet_hash'])
        with self.assertRaises(Invalid):host.call(self.session,'new-app','artifact',json.dumps({'job_id':job['job_id']}).encode())
        self.assertEqual(json.loads(host.call(self.session,'new-app','validate',json.dumps(request).encode())),packet)
        source=dict(request,kind='MANAGED',source_id=self.item['id'],sha256=self.item['source_sha256'])
        self.assertIn('path',json.loads(host.source(self.session,'new-app',json.dumps(source).encode())))
        proof=dict(artifact_id=job['job_id'],sha256='a'*64,bytes=100,frames=packet['plan']['output_frame_count'],width=packet['plan']['width'],height=packet['plan']['height'],audio=False)
        with self.assertRaises(Invalid):host.call(self.session,'new-app','finish',json.dumps(request).encode(),inspection=dict(proof,frames=0))
        done=json.loads(host.call(self.session,'new-app','finish',json.dumps(request).encode(),inspection=proof))
        self.assertEqual(done['status'],'SUCCEEDED')
        self.assertEqual(json.loads(host.call(self.session,'new-app','finish',json.dumps(request).encode(),inspection=proof)),done)
        with self.assertRaises(Invalid):host.call(self.session,'new-app','finish',json.dumps(dict(request,inspection=proof)).encode())
        with self.assertRaises(Invalid):host.call(self.session,'new-app','finish',json.dumps(request).encode(),inspection=dict(proof,sha256='b'*64))
        observed=self.call(grant['token'],'ios.timeline.inspect',{'job_id':job['job_id']})
        self.assertEqual(observed['result'],proof);self.assertNotIn('path',json.dumps(observed))
        with self.assertRaises(Invalid):self.call(grant['token'],'ios.timeline.finish',dict(request,inspection=proof))
        history=json.loads(host.call(self.session,'new-app','history',b'{}'))
        self.assertEqual([row['job_id'] for row in history['items']],[job['job_id']])
        artifact_body=json.dumps({'job_id':job['job_id']}).encode()
        self.assertEqual(json.loads(host.call(self.session,'new-app','artifact',artifact_body)),done)
        with self.assertRaises(PermissionError):host.call(self.session,'other','artifact',artifact_body)
        NativeAgentAccess(self.runtime.service,self.runtime.identities).manage(self.session,'new-app','revoke',
            json.dumps({'id':grant['grant']['id'],'version':1,'confirm_revoke':True}).encode())
        self.assertEqual(json.loads(host.call(self.session,'new-app','artifact',artifact_body)),done)
        item=json.loads(self.media_adapter.list(self.session,'new-app'))['items'][0]
        self.media_adapter.review(self.session,'new-app',item['id'],self.decision(item,'REVOKED'))
        with self.assertRaises(Invalid):host.call(self.session,'new-app','artifact',artifact_body)
        self.available=False
        with self.assertRaises(PermissionError):host.call(self.session,'new-app','history',b'{}')

    def test_native_session_lock_foreign_app_and_desktop_fallback_denied(self):
        self.runtime.create_workspace(self.session,self.creation())
        grant=self.issue(['ios.scene.save','studio.sessions']);token=grant['token']
        body=dict(project_id='scene-one',base_revision=0,manifest_version=1,request_key='save-one',scene=self.scene())
        with self.assertRaises(PermissionError):self.call(token,'ios.scene.save',body,app='other')
        with self.assertRaises(Invalid):self.call(token,'studio.sessions',{})
        from mission_control.ios_operation_adapter import ScopedAgentAdapter
        raw=json.dumps(dict(app_id='new-app',operation='ios.scene.save',input=body)).encode()
        with self.assertRaises(PermissionError):ScopedAgentAdapter(self.runtime.service).call(token,raw)
        self.available=False
        with self.assertRaises(PermissionError):self.save_scene(token)

    def test_timeline_grant_revocation_and_rights_change_deny_inflight_completion(self):
        self.prepare_fixture();grant=self.issue(['ios.timeline.queue']);token=grant['token']
        body=dict(project_id=self.project['id'],revision=1,project_hash=self.project['hash'],request_key='timeline-1')
        job=self.call(token,'ios.timeline.queue',body)['job'];host=NativeAgentTimeline(self.runtime.service,self.runtime.identities)
        request=dict(job_id=job['job_id'],packet_hash=job['packet_hash'])
        NativeAgentAccess(self.runtime.service,self.runtime.identities).manage(self.session,'new-app','revoke',
            json.dumps({'id':grant['grant']['id'],'version':1,'confirm_revoke':True}).encode())
        with self.assertRaises(PermissionError):host.call(self.session,'new-app','validate',json.dumps(request).encode())
        grant2=self.issue(['ios.timeline.queue']);body['request_key']='timeline-2'
        other=self.call(grant2['token'],'ios.timeline.queue',body)['job']
        reviewed=json.loads(self.media_adapter.list(self.session,'new-app'))['items'][0]
        self.media_adapter.review(self.session,'new-app',reviewed['id'],self.decision(reviewed,'REVOKED'))
        with self.assertRaises(Invalid):host.call(self.session,'new-app','validate',json.dumps(dict(job_id=other['job_id'],packet_hash=other['packet_hash'])).encode())

    def test_owner_job_cannot_be_adopted_and_agent_lock_rolls_back(self):
        self.runtime.create_workspace(self.session,self.creation())
        grant=self.issue(['ios.scene.save','ios.scene.start']);project=self.save_scene(grant['token'])
        body=dict(project_id='scene-one',revision=1,source_hash=project['source_hash'],request_key='owner-render')
        self.studio('start',body)
        with self.assertRaises(PermissionError):self.call(grant['token'],'ios.scene.start',body)
        original=NativeStudio._dispatch
        def lock_after_dispatch(studio,*args):
            result=original(studio,*args)
            if args[3]=='start':self.available=False
            return result
        body['request_key']='agent-lock'
        with patch.object(NativeStudio,'_dispatch',lock_after_dispatch):
            with self.assertRaises(PermissionError):self.call(grant['token'],'ios.scene.start',body)
        self.available=True
        with connection(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM ios_studio_jobs WHERE request_key='agent-lock'").fetchone()[0],0)

    def test_owner_can_read_finished_scene_receipt_after_grant_revocation(self):
        self.runtime.create_workspace(self.session,self.creation())
        grant=self.issue(['ios.scene.save','ios.scene.start','ios.scene.inspect']);project=self.save_scene(grant['token'])
        job=self.start_scene(grant['token'],project)['job'];request=dict(job_id=job['job_id'],packet_hash=job['packet_hash'])
        proof=dict(artifact_id=job['job_id'],sha256='a'*64,bytes=100,frames=24,width=720,height=1280,audio=False)
        self.studio('finish',request,proof)
        self.assertEqual(self.call(grant['token'],'ios.scene.inspect',{'job_id':job['job_id']})['result'],proof)
        NativeAgentAccess(self.runtime.service,self.runtime.identities).manage(self.session,'new-app','revoke',
            json.dumps({'id':grant['grant']['id'],'version':1,'confirm_revoke':True}).encode())
        self.assertEqual(self.studio('artifact',{'job_id':job['job_id']})['result'],proof)

    def check_retained_source_audio(self,has_audio):
        from tests.test_video_edit_projects import project_data
        self.runtime.create_workspace(self.session,self.creation())
        def inspect(raw,suffix,alive):
            result=fixture.media_fixture.synthetic_inspection(raw,suffix,alive)
            result['metadata']['audio']=has_audio
            result['decoded']['audio_frames']=1024 if has_audio else 0
            return result
        adapter=self.adapter(inspect);item=self.upload(adapter)
        adapter.review(self.session,'new-app',item['id'],self.decision(item))
        definition=project_data(item['id'],item['source_sha256'])
        definition['clips'][0]['source']['kind']='MANAGED';definition['clips'][0]['out_frame']=24
        definition['clips'][0]['audio']='RETAIN'
        body=dict(id='audio-edit',revision=0,manifest_version=1,data=definition,request_key='audio-project')
        project=json.loads(self.runtime.owner_call(self.session,json.dumps(dict(app_id='new-app',operation='editor.save',input=body)).encode()))
        grant=self.issue(['ios.timeline.queue'])
        job=self.call(grant['token'],'ios.timeline.queue',dict(project_id=project['id'],revision=1,project_hash=project['hash'],request_key='audio-render'))
        packet=job['packet'];identity=job['job']['job_id'];host=NativeAgentTimeline(self.runtime.service,self.runtime.identities)
        request=dict(job_id=identity,packet_hash=packet['packet_hash'])
        proof=dict(artifact_id=identity,sha256='a'*64,bytes=100,frames=packet['plan']['output_frame_count'],
                   width=packet['plan']['width'],height=packet['plan']['height'],audio=not has_audio)
        with self.assertRaises(Invalid):host.call(self.session,'new-app','finish',json.dumps(request).encode(),inspection=proof)
        proof['audio']=has_audio
        self.assertEqual(json.loads(host.call(self.session,'new-app','finish',json.dumps(request).encode(),inspection=proof))['status'],'SUCCEEDED')

    def test_retain_silent_source_requires_silent_output(self):
        self.check_retained_source_audio(False)

    def test_retain_audio_source_requires_audio_output(self):
        self.check_retained_source_audio(True)


if __name__=='__main__':unittest.main()
