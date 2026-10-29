"""Native Studio persistence and authority; this is not AVFoundation evidence."""
import json
import unittest
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.ios_studio import NativeStudio
from tests import test_ios_media_adapter as fixture


class NativeStudioTests(unittest.TestCase):
    verify = fixture.NativeMediaTests.verify
    creation = fixture.NativeMediaTests.creation
    adapter = fixture.NativeMediaTests.adapter
    upload = fixture.NativeMediaTests.upload
    decision = fixture.NativeMediaTests.decision

    def setUp(self):
        fixture.NativeMediaTests.setUp(self)
        self.runtime.create_workspace(self.session, self.creation())

    def invoke(self, action, body, inspection=None):
        studio = NativeStudio(self.runtime.service, self.runtime.identities)
        return json.loads(studio.call(self.session, 'new-app', action, json.dumps(body).encode(), inspection=inspection))

    def saved(self):
        return self.invoke('save', dict(project_id='scene-one', base_revision=0, manifest_version=1,
            request_key='save-one', scene=dict(title='Title', shape='PORTRAIT',
                scenes=[dict(text='First', seconds=1), dict(text='Second', seconds=1)])))

    def started(self):
        project = self.saved()
        request = dict(project_id=project['project_id'], revision=project['revision'], source_hash=project['source_hash'])
        return project, self.invoke('start', dict(request, request_key='render-one'))

    def proof(self, job_id):
        return dict(artifact_id=job_id, sha256='a'*64, bytes=1024, frames=48, width=720, height=1280, audio=False)

    def test_revision_render_and_idempotency(self):
        project, started = self.started()
        self.assertEqual(started['job']['status'], 'PREPARED')
        self.assertEqual(started['packet']['frame_count'], 48)
        self.assertFalse(started['packet']['execution_authority'])
        request = dict(job_id=started['job']['job_id'], packet_hash=started['packet']['packet_hash'])
        self.assertEqual(self.invoke('validate', request), started['packet'])
        with self.assertRaises(Invalid): self.invoke('finish', request)
        bad = self.proof(request['job_id']); bad['frames'] = 47
        with self.assertRaises(Invalid): self.invoke('finish', request, bad)
        with self.assertRaises(Invalid): self.invoke('finish', request, self.proof(str(uuid4())))
        proof = self.proof(request['job_id'])
        result = self.invoke('finish', request, proof)
        self.assertEqual(result['status'], 'SUCCEEDED')
        self.assertEqual(self.invoke('finish', request, proof), result)
        with self.assertRaises(Invalid): self.invoke('finish', request, dict(proof, sha256='b'*64))
        self.assertEqual(self.invoke('artifact', {'job_id': request['job_id']}), result)
        self.invoke('save', dict(project_id=project['project_id'], base_revision=1, manifest_version=1,
            request_key='revision-two', scene=dict(project['scene'], title='Revised')))
        self.assertEqual(self.invoke('artifact', {'job_id': request['job_id']})['revision'], 1)
        self.assertEqual(len(self.invoke('read', {'project_id':project['project_id']})['jobs']), 1)

    def test_edit_cancel_and_revocation_deny_commit(self):
        project, started = self.started()
        request = dict(job_id=started['job']['job_id'], packet_hash=started['packet']['packet_hash'])
        with self.assertRaises(Invalid): self.invoke('artifact', {'job_id': request['job_id']})
        self.invoke('save', dict(project_id=project['project_id'], base_revision=1, manifest_version=1,
            request_key='save-two', scene=dict(project['scene'], title='Changed')))
        with self.assertRaises(Invalid): self.invoke('finish', request, self.proof(request['job_id']))
        self.assertEqual(self.invoke('cancel', {'job_id':request['job_id']})['status'], 'CANCELLED')
        with self.assertRaises(Invalid): self.invoke('finish', request, self.proof(request['job_id']))
        self.available = False
        with self.assertRaises(PermissionError): self.invoke('projects', {})

    def test_closed_scene_and_request_keys(self):
        project = self.saved()
        self.assertEqual(project['revision'], 1)
        with self.assertRaises(Invalid):
            self.invoke('save', dict(project_id='scene-one', base_revision=0, manifest_version=1,
                request_key='save-one', scene=dict(project['scene'], code='arbitrary')))
        with self.assertRaises(Invalid):
            self.invoke('save', dict(project_id='scene-one', base_revision=0, manifest_version=1,
                request_key='different', scene=project['scene']))

    def test_media_source_is_bound_and_revocation_blocks_completion(self):
        media = self.adapter(); item = self.upload(media)
        media.review(self.session, 'new-app', item['id'], self.decision(item))
        source = dict(id=item['id'], sha256=item['source_sha256'], in_frame=0, audio='MUTE')
        scene = dict(title='Media scene', shape='PORTRAIT', scenes=[dict(text='Caption', seconds=1, media=source)])
        for invalid in (dict(source, in_frame=True), dict(source, in_frame=1420), dict(source, audio='RETAIN', endpoint='foreign')):
            with self.assertRaises(Invalid):
                self.invoke('save', dict(project_id='invalid-scene', base_revision=0, manifest_version=1,
                    request_key=str(uuid4()), scene=dict(scene, scenes=[dict(text='Caption', seconds=1, media=invalid)])))
        project = self.invoke('save', dict(project_id='media-scene', base_revision=0, manifest_version=1,
            request_key='save-media', scene=scene))
        missing_audio = dict(scene, scenes=[dict(text='Caption', seconds=1, media=dict(source, audio='RETAIN'))])
        silent = self.invoke('save', dict(project_id='silent-source', base_revision=0, manifest_version=1,
            request_key='save-silent', scene=missing_audio))
        with self.assertRaises(Invalid): self.invoke('plan', dict(project_id='silent-source', revision=1, source_hash=silent['source_hash']))
        start = self.invoke('start', dict(project_id=project['project_id'], revision=1,
            source_hash=project['source_hash'], request_key='render-media'))
        job, packet = start['job'], start['packet']
        studio = NativeStudio(self.runtime.service, self.runtime.identities)
        path = studio.source(self.session, 'new-app', job['job_id'], packet['packet_hash'], item['id'], item['source_sha256'])
        self.assertTrue(path.is_file())
        with self.assertRaises(Invalid):
            studio.source(self.session, 'new-app', job['job_id'], packet['packet_hash'], item['id'], '0'*64)
        reviewed = json.loads(media.list(self.session, 'new-app'))['items'][0]
        media.review(self.session, 'new-app', item['id'], self.decision(reviewed, 'REVOKED'))
        with self.assertRaises(Invalid): self.invoke('validate', dict(job_id=job['job_id'], packet_hash=packet['packet_hash']))
        with self.assertRaises(Invalid): self.invoke('finish', dict(job_id=job['job_id'], packet_hash=packet['packet_hash']), self.proof(job['job_id']))
