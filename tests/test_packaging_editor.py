"""Source-bound editable projects use actual SQLite and synthetic original media."""
from copy import deepcopy
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest
from mission_control.db import connection,initialize
from mission_control.creative_briefs import Briefs
from mission_control.creative_taste import guidance
from mission_control.managed_media_store import Media
from mission_control.packaging_store import Packaging
from mission_control.packaging_editor import prepare
from mission_control.video_edit_projects import Projects,saved_data
from tests import test_agent_grants as grants
from tests import test_verified_review as identities
from tests.test_creative_production import ready_production
from tests.test_packaging import draft,ref
from tests.test_managed_media_store import RAW,synthetic_inspection
from tests.test_video_edit_projects import project_data


class PackagingEditorTests(unittest.TestCase):
    tearDown=grants.GrantTests.tearDown

    def setUp(self):
        grants.GrantTests.setUp(self);self.app='sample-one'
        app=self.store.app(self.app)
        self.store.save_app(self.app,dict(app['data'],job='Synthetic task',audience='Synthetic audience',activation='A fictional task'),app['version'])
        self.source,_,records,data=ready_production(self.store,self.app)
        self.manifest=self.store.app(self.app)['version']
        brief=Briefs(self.store).save(self.app,{'data':data})
        packaging=Packaging(self.store)
        variant=packaging.save(self.app,dict(id='variant-one',version=0,kind='VARIANT',manifest_version=self.manifest,
            data=dict(draft(),creative=ref('BRIEF',brief),app_proofs=[ref('CLAIM',records['claim']),ref('ASSET',records['asset'])])))
        media=Media(self.store)
        with patch('mission_control.managed_media_store.inspect',side_effect=synthetic_inspection):
            self.media=media.upload(self.app,'original.mp4',RAW,dict(manifest_version=self.manifest,request_key='packaging-original'))
        self.review=dict(expected_version=0,manifest_version=self.manifest,source_sha256=self.media['source_sha256'],status='ALLOWED',basis='OWNED',evidence='Synthetic original-owner attestation')
        reviewed=media.review(self.app,self.media['id'],self.review,identities.OWNER)
        segment=dict(id='opening',text='Demonstrate an original app step')
        self.shots=packaging.save(self.app,dict(id='shots-one',version=0,kind='SHOTS',manifest_version=self.manifest,
            data=dict(variant=ref('VARIANT',variant),script=[segment],shots=[dict(id='shot-one',segment_id='opening',segment_sha256=digest(segment),kind='SCREEN_RECORDING',description='Show the app step',source=None,start_ms=None,end_ms=None,
                assets=[dict(kind='MEDIA',id=self.media['id'],version=reviewed['review_version'],sha256=self.media['source_sha256'])],claims=[],claim_text='')])))
        self.taste_body=dict(id='taste-one',version=0,manifest_version=self.manifest,policy_sha256=guidance()['policy_sha256'],data=dict(lens='product',voice='Plain words',visual='Actual product screens',examples=[],exclusions=[]))
        self.taste=self.owner.request('POST','/api/apps/sample-one/packaging/taste-review',self.taste_body)
        clip=project_data(self.media['id'],self.media['source_sha256'])['clips'][0]
        clip.update(source=dict(kind='MANAGED',id=self.media['id'],sha256=self.media['source_sha256']),out_frame=24,audio='MUTE',shot_id='shot-one')
        self.body=dict(manifest_version=self.manifest,shots=ref('SHOTS',self.shots),taste=dict(id=self.taste['id'],version=1,sha256=self.taste['hash']),title='Original app demonstration',purpose='Show a useful original app step',output='PORTRAIT',clips=[clip])

    def save_project(self):
        result=prepare(self.store,self.app,self.body)
        saved=Projects(self.store).save(self.app,dict(id='editor-one',revision=0,manifest_version=self.manifest,data=result['definition'],request_key='first-handoff'))
        return result,saved

    def test_prepare_save_edit_split_and_restart_preserve_reviewed_origin(self):
        prepared,saved=self.save_project()
        self.assertFalse(prepared['execution_authority']);self.assertEqual(prepared['project_save'],'NOT_RUN')
        self.assertEqual(saved['data']['packaging']['taste'],self.body['taste'])
        self.assertEqual(saved['data']['definition']['clips'][0]['audio'],'MUTE')
        projects=Projects(self.store)
        split=projects.edit(self.app,'editor-one',dict(revision=1,manifest_version=self.manifest,request_key='split-reviewed-shot',command=dict(operation='split',clip_id='clip-one',at_frame=12,new_id='split-two')))
        self.assertEqual(len(split['data']['definition']['clips']),2)
        self.assertEqual(split['data']['packaging'],saved['data']['packaging'])
        initialize(self.store.path)
        self.assertEqual(projects.read(self.app,'editor-one')['hash'],split['hash'])
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_wrong_media_missing_audio_closed_fields_and_foreign_scope_reject(self):
        for change in [dict(self.body,approved=True),dict(self.body,manifest_version=999),dict(self.body,taste=dict(self.body['taste'],sha256='0'*64)),dict(self.body,clips=[])]:
            with self.subTest(change=change),self.assertRaises(Invalid):prepare(self.store,self.app,change)
        for change in [dict(shot_id='wrong'),dict(source=dict(kind='NATIVE',id=self.media['id'],sha256=self.media['source_sha256'])),dict(out_frame=25)]:
            body=deepcopy(self.body);body['clips'][0].update(change)
            with self.subTest(change=change),self.assertRaises(Invalid):prepare(self.store,self.app,body)
        body=deepcopy(self.body);body['clips'][0].pop('audio')
        with self.assertRaises(Invalid):prepare(self.store,self.app,body)
        with self.assertRaises(Invalid):prepare(self.store,'sample-two',self.body)

    def test_changed_owner_taste_invalidates_editor_source_proof(self):
        _,saved=self.save_project()
        self.owner.request('POST','/api/apps/sample-one/packaging/taste-review',dict(self.taste_body,version=1))
        with self.assertRaises(Invalid),connection(self.store.path) as db:
            saved_data(db,self.store,self.app,self.manifest,saved['data']['definition'])
        with self.assertRaises(Invalid):prepare(self.store,self.app,self.body)

    def test_changed_script_requires_new_shots_and_invalidates_saved_editor_proof(self):
        _,saved=self.save_project();value=deepcopy(self.shots['data']['definition'])
        value['script'][0]['text']='A reviewed new app demonstration'
        with self.assertRaises(Invalid):
            Packaging(self.store).save(self.app,dict(id='shots-one',version=1,kind='SHOTS',manifest_version=self.manifest,data=value))
        value['shots'][0]['segment_sha256']=digest(value['script'][0])
        Packaging(self.store).save(self.app,dict(id='shots-one',version=1,kind='SHOTS',manifest_version=self.manifest,data=value))
        with self.assertRaises(Invalid):prepare(self.store,self.app,self.body)
        with self.assertRaises(Invalid),connection(self.store.path) as db:
            saved_data(db,self.store,self.app,self.manifest,saved['data']['definition'])

    def test_revoked_original_rights_reject_existing_project_and_preparation(self):
        _,saved=self.save_project()
        Media(self.store).review(self.app,self.media['id'],dict(self.review,expected_version=1,status='REVOKED'),identities.OWNER)
        with self.assertRaises(Invalid):prepare(self.store,self.app,self.body)
        with self.assertRaises(Invalid),connection(self.store.path) as db:
            saved_data(db,self.store,self.app,self.manifest,saved['data']['definition'])

    def test_saved_project_cannot_drop_origin_or_substitute_unselected_media(self):
        _,saved=self.save_project();value=deepcopy(saved['data']['definition']);value.pop('packaging')
        with self.assertRaises(Invalid):Projects(self.store).save(self.app,dict(id='editor-one',revision=1,manifest_version=self.manifest,data=value,request_key='drop-origin'))
        value=deepcopy(saved['data']['definition']);value['clips'][0]['source']['sha256']='0'*64
        with self.assertRaises(Invalid):Projects(self.store).save(self.app,dict(id='editor-one',revision=1,manifest_version=self.manifest,data=value,request_key='swap-source'))


if __name__=='__main__':unittest.main()
