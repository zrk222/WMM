"""Real isolated storage validates checklists; synthetic media is not render proof."""
import json
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,digest,now
from mission_control.db import connection
from mission_control.packaging_handoff import preview
from mission_control.managed_media_store import Media
from tests import test_packaging as fixtures
from tests.test_packaging import ref,draft
from tests.test_managed_media_store import RAW,synthetic_inspection


class HandoffChecklistTests(unittest.TestCase):
    setUp=fixtures.PackagingTests.setUp
    tearDown=fixtures.PackagingTests.tearDown
    save=fixtures.PackagingTests.save
    shotlist=fixtures.PackagingTests.shotlist

    def plan(self):
        variant=self.save();definition=self.shotlist(variant)
        saved=self.save(definition,'shots-one',kind='SHOTS')
        return variant,saved,definition

    def body(self,saved):
        return dict(manifest_version=self.store.app(self.app)['version'],shots=ref('SHOTS',saved))

    def test_missing_media_and_claims_are_visible_without_writes(self):
        _,saved,_=self.plan()
        with connection(self.store.path) as db:before=db.execute('SELECT count(*) FROM audit').fetchone()[0]
        first=preview(self.store,self.app,self.body(saved));second=preview(self.store,self.app,self.body(saved))
        self.assertEqual(first,second);self.assertEqual(first['source_status'],'CURRENT')
        row=first['rows'][0]
        self.assertIn('TIMED_ORIGINAL_MEDIA_REQUIRED',row['gaps'])
        self.assertIn('CLAIM_PROOF_REQUIRED',row['gaps'])
        self.assertEqual(row['script']['sha256'],digest(dict(id='opening',text='A fictional original script')))
        self.assertFalse(first['execution_authority']);self.assertFalse(row['research']['reuse_authority'])
        self.assertEqual(first['status'],'EDITING_DECISIONS_REQUIRED')
        self.assertEqual(first['checklist_sha256'],digest({k:v for k,v in first.items() if k!='checklist_sha256'}))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM audit').fetchone()[0],before)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_still_asset_is_not_timed_media_and_changed_bytes_are_stale(self):
        variant=self.save();definition=self.shotlist(variant)
        definition['shots'][0]['assets']=[ref('ASSET',self.records['asset'])]
        saved=self.save(definition,'shots-one',kind='SHOTS');body=self.body(saved)
        value=preview(self.store,self.app,body)
        self.assertEqual(len(value['rows'][0]['still_assets']),1)
        self.assertEqual(value['rows'][0]['media'],[])
        self.assertIn('TIMED_ORIGINAL_MEDIA_REQUIRED',value['rows'][0]['gaps'])
        path=self.store.path.parent/'files'/self.app/self.records['asset']['data']['file_id']
        path.write_bytes(b'Changed synthetic asset')
        value=preview(self.store,self.app,body)
        self.assertEqual(value['source_status'],'STALE');self.assertTrue(value['source_problems'])

    def test_exact_revision_hash_app_and_closed_input_reject(self):
        _,saved,definition=self.plan();body=self.body(saved)
        for changed in [dict(body,extra=True),dict(body,manifest_version=True),dict(body,shots=dict(body['shots'],sha256='0'*64)),dict(body,shots=dict(body['shots'],kind='VARIANT'))]:
            with self.subTest(changed=changed),self.assertRaises(Invalid):preview(self.store,self.app,changed)
        with self.assertRaises(Invalid):preview(self.store,'sample-two',body)
        definition['shots'][0]['description']='Reviewed next shot'
        self.save(definition,'shots-one',version=1,kind='SHOTS')
        with self.assertRaises(Invalid):preview(self.store,self.app,body)

    def test_changed_app_or_variant_cannot_silently_rebind(self):
        _,saved,_=self.plan();body=self.body(saved)
        app=self.store.app(self.app);self.store.save_app(self.app,dict(app['data'],audience='Another audience'),app['version'])
        with self.assertRaises(Invalid):preview(self.store,self.app,body)
        body['manifest_version']=self.store.app(self.app)['version']
        self.assertEqual(preview(self.store,self.app,body)['source_status'],'STALE')

    def test_changed_variant_rejects_old_shot_parent(self):
        _,saved,_=self.plan();self.save(dict(draft(),title='Revised creative'),version=1)
        with self.assertRaises(Invalid):preview(self.store,self.app,self.body(saved))

    def test_research_timing_is_not_a_source_trim(self):
        variant=self.save();definition=self.shotlist(variant)
        source=dict(self.source['current'],id=self.source['id'])
        definition['shots'][0].update(source=ref('SOURCE',source),start_ms=1001,end_ms=2500)
        saved=self.save(definition,'shots-one',kind='SHOTS')
        row=preview(self.store,self.app,self.body(saved))['rows'][0]
        self.assertEqual((row['research']['start_ms'],row['research']['end_ms']),(1001,2500))
        self.assertFalse(row['research']['reuse_authority'])
        self.assertIn('ORIGINAL_SOURCE_FRAME_RANGE',row['decisions_required'])

    def test_reviewed_media_and_revocation_are_rechecked(self):
        with connection(self.store.path) as db:
            db.execute('INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)',(self.app,'owner-1','owner','OWNER','ACTIVE',1,now(),'owner-1'))
        media=Media(self.store);manifest=self.store.app(self.app)['version']
        with patch('mission_control.managed_media_store.inspect',side_effect=synthetic_inspection):
            item=media.upload(self.app,'original.mp4',RAW,dict(manifest_version=manifest,request_key='synthetic-original'))
        review=dict(expected_version=0,manifest_version=manifest,source_sha256=item['source_sha256'],status='ALLOWED',basis='OWNED',evidence='Synthetic owner attestation')
        reviewed=media.review(self.app,item['id'],review,dict(principal='owner-1'))
        variant=self.save();definition=self.shotlist(variant)
        definition['shots'][0]['assets']=[dict(kind='MEDIA',id=item['id'],version=reviewed['review_version'],sha256=item['source_sha256'])]
        saved=self.save(definition,'shots-one',kind='SHOTS');body=self.body(saved)
        value=preview(self.store,self.app,body);row=value['rows'][0]
        self.assertEqual(row['media'][0]['status'],'CURRENT_REUSABLE_ORIGINAL')
        self.assertNotIn('TIMED_ORIGINAL_MEDIA_REQUIRED',row['gaps'])
        self.assertFalse(value['execution_authority']);self.assertNotIn('storage_name',json.dumps(value))
        media.review(self.app,item['id'],dict(review,expected_version=reviewed['review_version'],status='REVOKED'),dict(principal='owner-1'))
        value=preview(self.store,self.app,body)
        self.assertEqual(value['source_status'],'STALE')
        self.assertIn('CURRENT_MEDIA_AND_RIGHTS_REQUIRED',value['rows'][0]['gaps'])


if __name__=='__main__':unittest.main()
