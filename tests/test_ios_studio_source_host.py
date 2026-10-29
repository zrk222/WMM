"""Fixed native source gateway rejects caller paths and checks bound render media."""
import json
import unittest

from mission_control.common import Invalid
from tests import test_ios_studio as studio_fixture


class StudioSourceHostTests(unittest.TestCase):
    setUp = studio_fixture.NativeStudioTests.setUp
    verify = studio_fixture.NativeStudioTests.verify
    creation = studio_fixture.NativeStudioTests.creation
    adapter = studio_fixture.NativeStudioTests.adapter
    upload = studio_fixture.NativeStudioTests.upload
    decision = studio_fixture.NativeStudioTests.decision
    invoke = studio_fixture.NativeStudioTests.invoke

    def test_host_source_requires_current_render_and_exact_payload(self):
        adapter = self.adapter()
        item = self.upload(adapter)
        adapter.review(self.session, 'new-app', item['id'], self.decision(item))
        scene = dict(title='App demonstration', shape='PORTRAIT', scenes=[dict(
            text='Try the app', seconds=1, media=dict(id=item['id'],
            sha256=item['source_sha256'], in_frame=0, audio='MUTE'))])
        project = self.invoke('save', dict(project_id='host-source', base_revision=0,
            manifest_version=1, request_key='host-source-save', scene=scene))
        start = self.invoke('start', dict(project_id=project['project_id'], revision=1,
            source_hash=project['source_hash'], request_key='host-source-start'))
        body = dict(job_id=start['job']['job_id'], packet_hash=start['packet']['packet_hash'],
                    media_id=item['id'], sha256=item['source_sha256'])
        read = lambda value: self.runtime.native_studio_source(
            self.session, 'new-app', json.dumps(value).encode())
        location = json.loads(read(body))
        self.assertEqual(set(location), {'path'})
        from pathlib import Path
        self.assertTrue(Path(location['path']).is_file())
        for bad in (dict(body, path=location['path']), dict(body, sha256='0'*64), [], None):
            with self.assertRaises(Invalid): read(bad)
        self.available = False
        with self.assertRaises(PermissionError): read(body)
