"""Real editor/media state through native preparation; no AVFoundation claim."""
from copy import deepcopy
import json
import unittest
from tests import test_ios_media_adapter as fixture
from tests.test_video_edit_projects import project_data
from mission_control.common import Invalid
from mission_control.ios_production import NativeProduction


class NativeProductionTests(unittest.TestCase):
    setUp=fixture.NativeMediaTests.setUp
    verify=fixture.NativeMediaTests.verify
    creation=fixture.NativeMediaTests.creation
    adapter=fixture.NativeMediaTests.adapter
    owned=fixture.NativeMediaTests.owned
    upload=fixture.NativeMediaTests.upload
    decision=fixture.NativeMediaTests.decision

    def prepare_fixture(self):
        media=self.owned();item=self.upload(media)
        media.review(self.session,'new-app',item['id'],self.decision(item))
        data=project_data(item['id'],item['source_sha256'])
        data['clips'][0]['source']['kind']='MANAGED';data['clips'][0]['out_frame']=24
        body=dict(id='native-edit',revision=0,manifest_version=1,data=data,request_key='save-native-edit')
        project=json.loads(self.runtime.owner_call(self.session,json.dumps(dict(app_id='new-app',operation='editor.save',input=body)).encode()))
        self.production=NativeProduction(self.runtime.service,self.runtime.identities)
        self.project=project;self.item=item;self.media_adapter=media
        self.args=(self.session,'new-app',project['id'],project['revision'],project['hash'])
        return json.loads(self.production.prepare(*self.args))

    def test_saved_source_and_plan_bind_actual_original(self):
        packet=self.prepare_fixture()
        self.assertEqual(packet['status'],'PREPARED_NOT_RENDERED')
        self.assertFalse(packet['execution_authority'])
        self.assertEqual(packet['plan']['output_frame_count'],24)
        path=self.production.source(*self.args,packet['packet_hash'],'MANAGED',self.item['id'],self.item['source_sha256'])
        self.assertEqual(path.read_bytes(),fixture.media_fixture.RAW)
        self.assertNotIn(str(path),json.dumps(packet))
        self.assertEqual(self.production.validate(*self.args,packet['packet_hash']),packet)

    def test_edit_invalidates_prepared_revision_and_packet(self):
        packet=self.prepare_fixture()
        data=deepcopy(self.project['data']['definition']);data['title']='Revised title'
        body=dict(id=self.project['id'],revision=1,manifest_version=1,data=data,request_key='edit-new-title')
        self.runtime.owner_call(self.session,json.dumps(dict(app_id='new-app',operation='editor.save',input=body)).encode())
        with self.assertRaises(Invalid):self.production.validate(*self.args,packet['packet_hash'])

    def test_rights_revocation_session_loss_and_forged_source_deny(self):
        packet=self.prepare_fixture()
        with self.assertRaises(Invalid):self.production.source(*self.args,packet['packet_hash'],'MANAGED','0'*36,self.item['source_sha256'])
        allowed=json.loads(self.media_adapter.list(self.session,'new-app'))['items'][0]
        self.media_adapter.review(self.session,'new-app',allowed['id'],self.decision(allowed,'REVOKED'))
        with self.assertRaises(Invalid):self.production.validate(*self.args,packet['packet_hash'])
        self.available=False
        with self.assertRaises(PermissionError):self.production.prepare(*self.args)

    def test_wrong_packet_hash_foreign_app_and_fractional_revision_deny(self):
        packet=self.prepare_fixture()
        with self.assertRaises(Invalid):self.production.validate(*self.args,'0'*64)
        with self.assertRaises(PermissionError):self.production.prepare(self.session,'other',self.project['id'],1,self.project['hash'])
        with self.assertRaises(Invalid):self.production.prepare(self.session,'new-app',self.project['id'],True,self.project['hash'])

    def test_fixed_runtime_entry_retains_packet_and_rejects_extra_authority(self):
        packet=self.prepare_fixture()
        body=dict(project_id=self.project['id'],revision=1,project_hash=self.project['hash'])
        result=json.loads(self.runtime.native_production(self.session,'new-app','prepare',json.dumps(body).encode()))
        self.assertEqual(result,packet)
        body['packet_hash']=packet['packet_hash']
        self.assertEqual(json.loads(self.runtime.native_production(self.session,'new-app','validate',json.dumps(body).encode())),packet)
        source_body=dict(body,kind='MANAGED',source_id=self.item['id'],sha256=self.item['source_sha256'])
        located=json.loads(self.runtime.native_production(self.session,'new-app','source',json.dumps(source_body).encode()))
        from pathlib import Path
        self.assertEqual(Path(located['path']).read_bytes(),fixture.media_fixture.RAW)
        source_body['id']=source_body.pop('source_id')
        with self.assertRaises(Invalid):self.runtime.native_production(self.session,'new-app','source',json.dumps(source_body).encode())
        body['role']='OWNER'
        with self.assertRaises(Invalid):self.runtime.native_production(self.session,'new-app','validate',json.dumps(body).encode())
        with self.assertRaises(Invalid):self.runtime.native_production(self.session,'new-app','shell',b'{}')
