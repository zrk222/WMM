"""Real temporary SQLite and synthetic bytes prove bounded preparation only."""
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest, now
from mission_control.db import connection
from mission_control.store import Store
from mission_control.packaging_store import Packaging, gaps
from mission_control.packaging_bindings import variant_binding, shot_claims, collection_review
from mission_control.funnel_store import app_context
from mission_control.creative_library import Library
from mission_control.creative_briefs import Briefs
from tests.test_creative_production import ready_production
from tests.test_creative_library import reference


def ref(kind, row):
    return dict(kind=kind, id=row['id'], version=row['version'], sha256=row['hash'])


def draft():
    return dict(audience='Synthetic makers', app_outcome='Draft rehearsal hypothesis', title='Original test title',
                thumbnail='Planned original image', opening_frame='Original opening', hook='A fictional question',
                cta='Explore the fictional demo', sources=[], creative=None, app_proofs=[])


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'state.sqlite')
        self.app='production-test';self.source,self.analysis,self.records,self.brief_data=ready_production(self.store, self.app)
        self.packaging=Packaging(self.store)

    def tearDown(self):self.tmp.cleanup()

    def save(self, data=None, identity='variant-one', version=0, kind='VARIANT', app=None):
        app=app or self.app
        return self.packaging.save(app, dict(id=identity, version=version, kind=kind,
            manifest_version=self.store.app(app)['version'], data=draft() if data is None else data))

    def shotlist(self, variant):
        return dict(variant=ref('VARIANT', variant), script=[dict(id='opening', text='A fictional original script')],
            shots=[dict(id='shot-one', segment_id='opening', segment_sha256=digest(dict(id='opening', text='A fictional original script')), kind='A_ROLL', description='Film original opening',
                        source=None, start_ms=None, end_ms=None, assets=[], claims=[], claim_text='Unverified hypothesis')])

    def test_draft_missing_evidence_and_restart_history(self):
        first=self.save();self.assertEqual(first['source_status'], 'CURRENT')
        self.assertEqual(first['missing_evidence'], ['sources', 'creative', 'app_proofs'])
        self.assertFalse(first['execution_authority']);self.assertEqual(first['render'], 'NOT_RUN')
        second=self.save(dict(draft(), title='Reviewed second hypothesis'), version=1)
        restored=Packaging(Store(self.store.path));self.assertEqual(restored.read(self.app, 'variant-one', 'VARIANT', 1)['hash'], first['hash'])
        self.assertEqual(second['version'], 2);self.assertEqual(restored.list(self.app)['total'], 2)
        self.assertEqual(restored.list(self.app, 2)['items'], [])
        with self.assertRaises(Invalid):self.save(version=1)

    def test_source_brief_assets_claims_exact_bindings(self):
        brief=Briefs(self.store).save(self.app, {'data':self.brief_data})
        source=self.source['current'];source=dict(source, id=self.source['id'])
        data=dict(draft(), sources=[ref('SOURCE', source)], creative=ref('BRIEF', brief),
                  app_proofs=[ref('CLAIM', self.records['claim']), ref('ASSET', self.records['asset'])])
        row=self.save(data);self.assertEqual(row['missing_evidence'], [])
        self.assertEqual(row['state'], 'DRAFT');self.assertEqual(row['evidence_status'], 'SUPPLIED_CURRENT')
        changed=copy.deepcopy(data);changed['sources'][0]['sha256']='0'*64
        with self.assertRaises(Invalid):self.save(changed, 'bad-hash')
        with self.assertRaises(Invalid):self.save(data, app='sample-two')
        Library(self.store).save(self.app, dict(id=self.source['id'], version=1, data=reference(title='Changed source')))
        self.assertEqual(self.packaging.read(self.app, row['id'], 'VARIANT')['source_status'], 'STALE')
        with self.assertRaises(Invalid):self.save(data, 'stale-source')

    def test_manifest_changes_and_atomic_stale_denial(self):
        row=self.save();old=self.store.app(self.app);changed=dict(old['data'], audience='Changed synthetic audience')
        self.store.save_app(self.app, changed, old['version'])
        self.assertEqual(self.packaging.read(self.app, row['id'], 'VARIANT')['source_status'], 'STALE')
        with self.assertRaises(Invalid):self.packaging.save(self.app, dict(id='obsolete', version=0, kind='VARIANT', manifest_version=old['version'], data=draft()))
        self.assertEqual(self.packaging.list(self.app)['total'], 1)

    def test_script_shots_original_missing_and_stale_variant(self):
        variant=self.save();data=self.shotlist(variant);row=self.save(data, 'shots-one', kind='SHOTS')
        self.assertEqual(row['missing_evidence'], [dict(shot_id='shot-one', missing='ASSET_AND_RIGHTS'), dict(shot_id='shot-one', missing='CLAIM_PROOF')])
        self.assertIsNone(row['data']['definition']['shots'][0]['source'])
        self.save(dict(draft(), title='New variant'), version=1)
        self.assertEqual(self.packaging.read(self.app, 'shots-one', 'SHOTS')['source_status'], 'STALE')
        with self.assertRaises(Invalid):self.save(data, 'stale-shots', kind='SHOTS')

    def test_real_asset_bytes_and_claim_failure_readback(self):
        variant=self.save();data=self.shotlist(variant);shot=data['shots'][0]
        shot['assets']=[ref('ASSET', self.records['asset'])];shot['claims']=[ref('CLAIM', self.records['claim'])]
        shot['claim_text']=self.records['claim']['data']['claim']
        row=self.save(data, 'supported-shots', kind='SHOTS');self.assertEqual(row['missing_evidence'], [])
        path=self.store.path.parent/'files'/self.app/self.records['asset']['data']['file_id'];path.write_bytes(b'changed')
        self.assertEqual(self.packaging.read(self.app, row['id'], 'SHOTS')['source_status'], 'STALE')
        with self.assertRaises(Invalid):self.save(data, 'bad-bytes', kind='SHOTS')

    def test_closed_inputs_foreign_reads_and_append_only_sql(self):
        row=self.save()
        for data in (dict(draft(), title='x'*301), dict(draft(), sources=[{}]), dict(draft(), token='private')):
            with self.subTest(data=data),self.assertRaises(Invalid):self.save(data)
        with self.assertRaises(Invalid):self.packaging.read('sample-two', row['id'], 'VARIANT')
        with self.assertRaises(Invalid):self.save(identity=row['id'], version=1, kind='SHOTS', data=self.shotlist(row))
        for sql in ('UPDATE packaging_documents SET hash=hash', 'DELETE FROM packaging_documents'):
            with self.subTest(sql=sql),self.assertRaises(sqlite3.IntegrityError):
                with connection(self.store.path) as db:db.execute(sql)

    def test_shot_contract_boundaries(self):
        variant=self.save();data=self.shotlist(variant)
        for update in ({'segment_id':'missing'}, {'kind':'EXECUTE'}, {'start_ms':0}, {'claims':[{}]}, {'source':{}}, {'claim_text':None}):
            changed=copy.deepcopy(data);changed['shots'][0].update(update)
            with self.subTest(update=update),self.assertRaises(Invalid):self.save(changed, 'invalid-shots', kind='SHOTS')
        data['script'].append(dict(data['script'][0]))
        with self.assertRaises(Invalid):self.save(data, 'duplicates', kind='SHOTS')

    def test_gaps_variant_binding_shot_claims_and_script_changes(self):
        variant=self.save();data=self.shotlist(variant)
        self.assertEqual(gaps('VARIANT', draft()), ['sources', 'creative', 'app_proofs'])
        with connection(self.store.path) as db:
            self.assertEqual(variant_binding(db, self.store, self.app, ref('VARIANT', variant), app_context(db, self.app)), ref('VARIANT', variant))
            shot_claims(db, self.app, data['shots'])
            collection_review(db, self.app, None)
        changed=copy.deepcopy(data);changed['script'][0]['text']='Changed script requiring new shot review'
        with self.assertRaisesRegex(Invalid, 'segment changed'):self.save(changed, 'changed-script', kind='SHOTS')
        changed['shots'][0]['segment_sha256']=digest(changed['script'][0])
        saved=self.save(changed, 'changed-script', kind='SHOTS')
        self.assertEqual(saved['data']['definition']['script'], changed['script'])
        data['shots'][0]['claims']=[ref('CLAIM', self.records['claim'])]
        with self.assertRaisesRegex(Invalid, 'match selected app proof'):self.save(data, 'unrelated-claim', kind='SHOTS')

    def test_database_source_tampering_and_precommit_manifest_change_roll_back(self):
        source=dict(self.source['current'], id=self.source['id'])
        data=dict(draft(), sources=[ref('SOURCE', source)])
        saved=self.save(data)
        with connection(self.store.path) as db:
            db.execute('UPDATE creative_captures SET data=? WHERE app_id=? AND reference_id=?', (canonical(dict(source['data'], title='Tampered source bytes')), self.app, source['id']))
        self.assertEqual(self.packaging.read(self.app, saved['id'], 'VARIANT')['source_status'], 'STALE')
        with self.assertRaisesRegex(Invalid, 'integrity'):self.save(data, 'tampered')
        from mission_control.packaging_store import frozen
        def change_after_validation(db, store, app_id, kind, definition, app):
            value=frozen(db, store, app_id, kind, definition, app)
            db.execute('UPDATE apps SET version=version+1 WHERE id=?', (app_id,))
            return value
        before=self.store.app(self.app)['version']
        with patch('mission_control.packaging_store.frozen', side_effect=change_after_validation):
            with self.assertRaisesRegex(Invalid, 'before commit'):self.save(identity='raced')
        self.assertEqual(self.store.app(self.app)['version'], before)
        self.assertEqual(self.packaging.list(self.app)['total'], 1)

    def test_source_changes_during_save_roll_back(self):
        from mission_control.packaging_store import resolve
        source=dict(self.source['current'], id=self.source['id']);data=dict(draft(), sources=[ref('SOURCE', source)])
        def changed(db, store, app_id, ref, app):
            result=resolve(db, store, app_id, ref, app)
            db.execute('UPDATE creative_captures SET hash=? WHERE app_id=? AND reference_id=?', ('0'*64, app_id, ref['id']))
            return result
        with patch('mission_control.packaging_store.resolve', side_effect=changed):
            with self.assertRaisesRegex(Invalid, 'before commit'):self.save(data)
        self.assertEqual(self.packaging.list(self.app)['total'], 0)
        self.assertEqual(Library(self.store).list(self.app)[0]['current']['hash'], source['hash'])

    def test_media_unknown_revoked_and_stale_rights_are_never_usable(self):
        from mission_control.managed_media_store import Media
        from tests.test_managed_media_store import RAW, synthetic_inspection
        media=Media(self.store);version=self.store.app(self.app)['version']
        with connection(self.store.path) as db:
            db.execute('INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)', (self.app, 'packaging-owner', 'packaging-owner', 'OWNER', 'ACTIVE', 1, now(), 'packaging-owner'))
        with patch('mission_control.managed_media_store.inspect', side_effect=synthetic_inspection):
            item=media.upload(self.app, 'synthetic.mp4', RAW, dict(manifest_version=version, request_key='packaging-fixture'))
        variant=self.save();data=self.shotlist(variant);data['shots'][0]['claim_text']=''
        data['shots'][0]['assets']=[dict(kind='MEDIA', id=item['id'], version=1, sha256=item['source_sha256'])]
        with self.assertRaisesRegex(Invalid, 'attestation'):self.save(data, 'unknown-rights', kind='SHOTS')
        body=dict(expected_version=0, manifest_version=version, source_sha256=item['source_sha256'], status='ALLOWED', basis='OWNED', evidence='Synthetic local attestation only')
        allowed=media.review(self.app, item['id'], body, dict(principal='packaging-owner'))
        saved=self.save(data, 'media-shots', kind='SHOTS');self.assertEqual(saved['missing_evidence'], [])
        media.review(self.app, item['id'], dict(body, expected_version=allowed['review_version'], status='REVOKED'), dict(principal='packaging-owner'))
        self.assertEqual(self.packaging.read(self.app, 'media-shots', 'SHOTS')['source_status'], 'STALE')
        with self.assertRaisesRegex(Invalid, 'attestation'):self.save(data, 'revoked-rights', kind='SHOTS')
        media.review(self.app, item['id'], dict(body, expected_version=2), dict(principal='packaging-owner'))
        data['shots'][0]['assets'][0]['version']=3
        current=self.save(data, 'renewed-rights', kind='SHOTS')
        with connection(self.store.path) as db:db.execute("UPDATE operator_roles SET status='REVOKED' WHERE app_id=? AND principal='packaging-owner'", (self.app,))
        self.assertEqual(self.packaging.read(self.app, current['id'], 'SHOTS')['source_status'], 'STALE')

    def test_existing_collection_bindings_and_timestamped_source_shots(self):
        from mission_control.discovery_store import Discovery
        from tests.test_discovery_intelligence import filters
        discovery=Discovery(self.store)
        collection=discovery.collect(self.app, dict(id='research-one', version=0, manifest_version=self.store.app(self.app)['version'],
            query=filters(viral_only=False, published_before=now(), published_after='2026-01-01T00:00:00+00:00'), attempted_sources=1, failed_sources=0))
        data=dict(draft(), sources=[ref('COLLECTION', collection)])
        variant=self.save(data);shots=self.shotlist(variant);shot=shots['shots'][0]
        shot.update(source=ref('SOURCE', dict(self.source['current'], id=self.source['id'])), start_ms=0, end_ms=1000)
        saved=self.save(shots, 'source-shots', kind='SHOTS')
        self.assertEqual(saved['data']['definition']['shots'][0]['end_ms'], 1000)
        shot['end_ms']=0
        with self.assertRaises(Invalid):self.save(shots, 'invalid-time', kind='SHOTS')
        Library(self.store).save(self.app, dict(id=self.source['id'], version=1, data=reference(title='Changed collection source')))
        self.assertEqual(self.packaging.read(self.app, variant['id'], 'VARIANT')['source_status'], 'STALE')
        with self.assertRaises(Invalid):self.save(data, 'obsolete-collection')


if __name__=='__main__':unittest.main()
