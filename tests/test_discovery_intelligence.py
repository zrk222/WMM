"""Synthetic source research with real SQLite history and native evidence verification."""
import base64
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.creative_library import Library
from mission_control import discovery_contract as contract
from mission_control.discovery_store import Discovery, latest, append, capture, scoped, review_times, collection_state, source_outcomes
from mission_control.discovery_query import evaluate, rankings, velocity, ordered, observed_ratio, filter_reasons, observation_reasons
from tests.test_creative_library import reference
from tests.test_viral_policy import AS_OF, candidate, history


def filters(**changes):
    return dict(dict(outcome='Demonstrate an app outcome',audience='App users',industries=[],narratives=[],treatments=[],
        published_after='2026-10-01T00:00:00+00:00',published_before=AS_OF,freshness_seconds=86400,
        minimum_views=0,baseline_required=False,viral_only=True,ranking='REACH'),**changes)


def reviewed(**changes):
    taxonomy=dict(original_labels=['Third-party outlier'],industry='BUSINESS',narrative='APP_DEMO',treatment='TALKING_HEAD',classified_by='HUMAN_SUPPLIED',rationale='Synthetic direct inspection')
    card=dict(observed_hook='A synthetic question',observed_beats=[dict(start_ms=0,end_ms=1000,text='Synthetic opening')],interpreted_mechanism='Question then demonstration',
              relevance_rationale='An analyst interpretation, not measured app sales',reproduction_requirements=['Authentic screen'],authentic_evidence_ids=[],
              rights_status='UNKNOWN',rights_evidence='',next_experiment='Test an original opening with an authentic app screen')
    return dict(dict(taxonomy=taxonomy,duration_ms=30000,transcript=None,card=card,baseline=history(),metrics=None),**changes)


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'state.sqlite');self.app='sample-one'
        self.stamp=datetime.fromisoformat(AS_OF);self.service=Discovery(self.store,lambda:self.stamp);self.library=Library(self.store)
        self.source=self.add_source();self.review=self.save_review()

    def tearDown(self):self.tmp.cleanup()

    def add_source(self,**changes):
        value=candidate();data=reference(platform=value['platform'],post_id=value['post_id'],creator_id=value['creator_id'],format=value['format'],url=value['url'],
            metric_kind='VIEWS',metric_value=value['views'],metric_at=AS_OF,captured_at=AS_OF,published_at=value['published_at'])
        data.update(changes);saved=self.library.save(self.app,dict(data=data))
        return next(r['current'] for r in self.library.list(self.app) if r['id']==saved['id'])

    def save_review(self,value=None,version=0):
        return self.service.save_review(self.app,dict(id='review-one',version=version,manifest_version=self.store.app(self.app)['version'],
            reference_id=self.source['reference_id'],source_hash=self.source['hash'],data=value or reviewed()))

    def collect(self,**changes):
        body=dict(id='collection-one',version=0,manifest_version=self.store.app(self.app)['version'],query=filters(),attempted_sources=1,failed_sources=0)
        body.update(changes);return self.service.collect(self.app,body)

    def handoff_body(self,collection):
        return dict(manifest_version=self.store.app(self.app)['version'],collection_id=collection['id'],collection_hash=collection['hash'],reference_id=self.source['reference_id'],review_hash=self.review['hash'])

    def authentic_asset(self):
        app=self.store.app(self.app)['data'];app.update(release='synthetic',locale='en-US')
        self.store.save_app(self.app,app,self.store.app(self.app)['version'])
        service=Service(self.store);png=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jmrkAAAAASUVORK5CYII=')
        upload=service.upload(self.app,'synthetic-screen.png',png)
        return service.evidence(self.app,dict(kind='asset',title='Synthetic app screen',source='Synthetic local fixture',data=dict(upload['data'],authentic=True,rights_cleared=True,release='synthetic',locale='en-US',device='Synthetic fixture')))

    def prepared(self,collection_version=0):
        asset=self.authentic_asset();value=reviewed();value['card'].update(rights_status='ALLOWED_BY_ATTESTATION',rights_evidence='Synthetic fixture license attestation',authentic_evidence_ids=[asset['id']])
        self.review=self.save_review(value,1);collection=self.collect(version=collection_version)
        return self.service.handoff(self.app,self.handoff_body(collection)),collection,asset

    def test_separate_taxonomy_and_no_automatic_rights(self):
        value=self.review['data']['review'];self.assertEqual(value['taxonomy']['narrative'],'APP_DEMO');self.assertEqual(value['taxonomy']['treatment'],'TALKING_HEAD')
        self.assertEqual(value['taxonomy']['original_labels'],['Third-party outlier'])
        result=self.collect()['data'];self.assertEqual(result['coverage']['qualified_candidates'],1);self.assertEqual(result['coverage']['rights_missing'],1)
        self.assertEqual(result['boundaries']['reuse_approval'],'NOT_GRANTED');self.assertEqual(result['boundaries']['publication'],'NOT_RUN')
        self.assertIsNone(result['boundaries']['measured_app_sales'])

    def test_viral_requires_both_cutoffs_and_documented_comparable_baseline(self):
        for views,baseline,reason in [(99999,history(1),'BELOW_100000_VIEWS'),(100000,history(10001),'BELOW_TENFOLD_MEDIAN'),(1000000,[],'POSITIVE_MEDIAN_AND_TEN_COMPARABLE_POSTS_REQUIRED')]:
            source=deepcopy(self.source);source['data']['metric_value']=views;review=reviewed(baseline=baseline)
            result=evaluate(source,review,filters(),AS_OF)
            self.assertFalse(result['included']);self.assertFalse(result['qualified']);self.assertIn(reason,result['reasons'])
        for flag in (False,True):
            result=evaluate(self.source,reviewed(baseline=[]),filters(baseline_required=flag),AS_OF)
            self.assertFalse(result['included']);self.assertTrue(result['baseline_missing'])
        self.assertTrue(evaluate(self.source,reviewed(),filters(),AS_OF)['included'])

    def test_outlier_labels_and_other_counters_never_substitute_for_baseline(self):
        result=evaluate(self.source,None,filters(),AS_OF);self.assertFalse(result['qualified'])
        source=deepcopy(self.source);source['data']['metric_kind']='LIKES'
        result=evaluate(source,reviewed(),filters(),AS_OF);self.assertFalse(result['included']);self.assertIsNone(result['rankings']['REACH'])

    def test_transcript_permissions_timing_bounds_and_closed_fields(self):
        value=dict(permission_confirmed=True,language='en',source='Permitted transcript',observed_at=AS_OF,duration_ms=30000,uncertainty='Synthetic words',segments=[dict(start_ms=0,end_ms=1000,text='Synthetic opening')])
        self.assertEqual(contract.review(reviewed(transcript=value))['transcript'],value)
        for delta in [dict(permission_confirmed=False),dict(duration_ms=20000),dict(segments=[dict(start_ms=0,end_ms=30001,text='too long')]),dict(segments=[dict(start_ms=True,end_ms=1,text='bad')]),dict(token='private')]:
            with self.subTest(delta=delta),self.assertRaises(Invalid):contract.review(reviewed(transcript=dict(value,**delta)))
        with self.assertRaises(Invalid):contract.segments([value['segments'][0]]*201,30000,'Transcript')
        with self.assertRaises(Invalid):contract.segments([dict(start_ms=0,end_ms=10,text='a'),dict(start_ms=9,end_ms=20,text='b')],30,'Transcript')
        with self.assertRaises(Invalid):self.save_review(reviewed(transcript=dict(value,observed_at='2999-01-01T00:00:00+00:00')),1)

    def test_query_explains_filters_and_independent_missing_counts(self):
        self.add_source(post_id='unknown-baseline',creator_id=None)
        result=self.collect(query=filters(industries=['GAMING'],narratives=['TUTORIAL'],treatments=['ANIMATION'],minimum_views=100001))['data']
        self.assertEqual(result['coverage']['observed_candidates'],2);self.assertEqual(result['coverage']['baseline_missing'],1)
        self.assertEqual(result['coverage']['rights_missing'],2);self.assertEqual(result['coverage']['included_candidates'],0)
        for row in result['results']:self.assertIn('INDUSTRY_MISMATCH_OR_UNKNOWN',row['reasons']);self.assertIn('BELOW_REQUESTED_MINIMUM_VIEWS',row['reasons'])
        for delta in (dict(viral_only=1),dict(published_before='2026-09-01T00:00:00Z'),dict(industries=['BUSINESS']*25),dict(minimum_views=-1),dict(unapproved='extra')):
            with self.subTest(delta=delta),self.assertRaises(Invalid):contract.query(filters(**delta))

    def test_attention_metrics_have_exact_denominators_and_no_sales(self):
        data=self.source['data'];review=reviewed(metrics=dict(views=100000,likes=4000,comments=1000,shares=None,observed_at=AS_OF,collection_source='Synthetic same-observation export'))
        self.save_review(review,1);policy=evaluate(self.source,review,filters(),AS_OF)['policy']
        previous=dict(data,metric_value=90000,metric_at=(self.stamp-timedelta(hours=1)).isoformat())
        result=rankings(data,review,policy,previous)
        self.assertEqual(result['ENGAGEMENT']['numerator'],5000);self.assertEqual(result['ENGAGEMENT']['denominator'],100000)
        self.assertEqual(result['CREATOR_OUTLIER']['value'],10);self.assertAlmostEqual(result['VELOCITY']['value'],10000/3600)
        self.assertIsNone(velocity(data,None));self.assertIsNone(velocity(data,dict(previous,metric_value=100001)));self.assertIsNone(velocity(data,data))
        self.assertIsNone(observed_ratio(1,0,'ZERO',{}));self.assertNotIn('installs',canonical(result));self.assertNotIn('sales',canonical(result))
        review['metrics']['observed_at']=(self.stamp-timedelta(seconds=1)).isoformat()
        with self.assertRaisesRegex(Invalid,'share'):self.save_review(review,2)

    def test_deduplicated_immutable_collection_revisions_survive_restart(self):
        first=self.collect();self.assertEqual(first['data']['coverage']['observed_candidates'],1)
        self.add_source(post_id='second-source');second=self.collect(version=1)
        self.assertEqual(second['data']['coverage']['observed_candidates'],2)
        restarted=Discovery(Store(self.store.path),lambda:self.stamp)
        historical=restarted.read(self.app,'collection-one','COLLECTION',1)
        self.assertEqual(historical['hash'],first['hash']);self.assertEqual(historical['data'],first['data'])
        for sql in ('UPDATE discovery_documents SET hash=hash','DELETE FROM discovery_documents'):
            with self.assertRaises(sqlite3.IntegrityError),connection(self.store.path) as db:db.execute(sql)
        with self.assertRaises(Invalid):self.collect(version=0)
        with self.assertRaises(Invalid):restarted.read('sample-two','collection-one','COLLECTION')

    def test_empty_failed_partial_and_stale_are_explicit(self):
        empty=dict(id='empty',version=0,manifest_version=1,query=filters(),attempted_sources=0,failed_sources=0)
        self.assertEqual(self.service.collect('sample-two',empty)['data']['state'],'EMPTY')
        self.assertEqual(self.service.collect('sample-two',dict(empty,id='failed',attempted_sources=1,failed_sources=1))['data']['state'],'FAILED')
        self.assertEqual(self.collect(failed_sources=1)['data']['state'],'PARTIAL')
        self.stamp+=timedelta(days=2)
        self.assertEqual(self.collect(version=1)['data']['state'],'STALE')

    def test_filter_reasons_collection_state_texts_and_source_outcomes(self):
        self.assertEqual(filter_reasons(self.source['data'],reviewed(),filters(),AS_OF),[])
        old=dict(self.source['data'],metric_at='2026-10-23T11:59:59+00:00')
        self.assertIn('OBSERVATION_STALE_OR_FUTURE',observation_reasons(old,filters(),AS_OF))
        self.assertEqual(collection_state([],0),'EMPTY');self.assertEqual(collection_state([],1),'FAILED')
        self.assertEqual(contract.texts([' original '],1,20,'Label'),['original'])
        with self.assertRaises(Invalid):contract.texts(['same','same'],2,20,'Label')
        self.assertEqual(source_outcomes([dict(source='creator',status='EMPTY',detail='No authorized observations')]),{'creator'})
        self.assertIsNone(velocity(self.source['data'],dict(old,post_id='another-post')))
        self.assertIsNone(velocity(self.source['data'],dict(old,metric_kind='LIKES')))
        unknown=evaluate(self.source,None,filters(),AS_OF);known=evaluate(self.source,reviewed(),filters(),AS_OF)
        unknown['reference_id']='z';known['reference_id']='a'
        self.assertEqual(ordered([unknown,known],'CREATOR_OUTLIER')[0]['reference_id'],'a')

    def test_review_source_identity_and_watch_subjects_cannot_drift(self):
        another=self.add_source(post_id='another-post')
        with self.assertRaisesRegex(Invalid,'cannot change source'):
            self.service.save_review(self.app,dict(id='review-one',version=1,manifest_version=1,reference_id=another['reference_id'],source_hash=another['hash'],data=reviewed()))
        watch=dict(kind='CREATOR',subjects=['creator'],query=filters(),source='Permitted operator export',interval_seconds=86400,confirm_authorized_reads=True)
        saved=self.service.save_watch(self.app,dict(id='watch-one',version=0,manifest_version=1,data=watch));collection=self.collect()
        with self.assertRaisesRegex(Invalid,'selected watch subjects'):
            self.service.attempt(self.app,dict(id='attempt-other',manifest_version=1,watch_id=saved['id'],watch_hash=saved['hash'],collection_id=collection['id'],collection_hash=collection['hash'],source_results=[dict(source='other',status='OBSERVED',detail='Wrong creator')]))

    def test_prepared_handoff_is_hash_bound_and_confers_no_authority(self):
        packet,collection,asset=self.prepared()
        self.assertEqual(packet['state'],'PREPARED');self.assertEqual(packet['authentic_proofs'][0]['hash'],asset['hash'])
        self.assertEqual(packet['boundaries']['production_execution'],'NOT_RUN');self.assertEqual(packet['boundaries']['reuse_approval'],'NOT_GRANTED')
        self.assertEqual(packet['packet_hash'],digest({k:v for k,v in packet.items() if k!='packet_hash'}))
        self.assertEqual(packet['boundaries']['authority'],'RECHECK_EXACT_DOWNSTREAM_AUTHORITY')
        for key in ('collection_hash','review_hash'):
            with self.subTest(key=key),self.assertRaises(Invalid):self.service.handoff(self.app,dict(self.handoff_body(collection),**{key:'0'*64}))
        folder=self.store.path.parent/'files'/self.app;(folder/asset['data']['file_id']).write_bytes(b'changed fixture')
        with self.assertRaisesRegex(Invalid,'missing or changed'):self.service.handoff(self.app,self.handoff_body(collection))

    def test_handoff_denies_missing_rights_proof_and_changed_source_review_or_app(self):
        saved=self.collect()
        with self.assertRaisesRegex(Invalid,'rights'):self.service.handoff(self.app,self.handoff_body(saved))
        packet,saved,asset=self.prepared(1);self.save_review(reviewed(),2)
        with self.assertRaisesRegex(Invalid,'Review changed'):self.service.handoff(self.app,self.handoff_body(saved))
        source=self.library.list(self.app)[0]
        self.library.save(self.app,dict(id=source['id'],version=source['current']['version'],data=dict(source['current']['data'],title='Revised source')))
        with self.assertRaisesRegex(Invalid,'capture hash changed'):self.service.handoff(self.app,self.handoff_body(saved))
        app=self.store.app(self.app);self.store.save_app(self.app,dict(app['data'],name='Changed app'),app['version'])
        body=self.handoff_body(saved)
        with self.assertRaisesRegex(Invalid,'app changed'):self.service.handoff(self.app,body)

    def test_stale_or_foreign_review_is_not_applied_to_research(self):
        data=self.store.app(self.app);self.store.save_app(self.app,dict(data['data'],name='New app context'),data['version'])
        row=self.collect()['data']['results'][0];self.assertIsNone(row['review']);self.assertTrue(row['baseline_missing'])
        with self.assertRaises(Invalid):self.service.save_review('sample-two',dict(id='foreign',version=0,manifest_version=1,reference_id=self.source['reference_id'],source_hash=self.source['hash'],data=reviewed()))

    def test_watch_history_retains_failures_without_activating_schedule(self):
        watch=dict(kind='CREATOR',subjects=['creator'],query=filters(),source='Permitted operator export',interval_seconds=86400,confirm_authorized_reads=True)
        saved=self.service.save_watch(self.app,dict(id='watch-one',version=0,manifest_version=1,data=watch));collection=self.collect()
        self.assertEqual(saved['data']['schedule'],'NOT_ACTIVATED')
        body=dict(id='attempt-one',manifest_version=1,watch_id=saved['id'],watch_hash=saved['hash'],collection_id=collection['id'],collection_hash=collection['hash'],source_results=[dict(source='creator',status='FAILED',detail='Synthetic provider unavailable')])
        outcome=self.service.attempt(self.app,body)
        self.assertEqual(outcome['data']['source_results'][0]['status'],'FAILED');self.assertIn('NOT_INDEPENDENTLY_VERIFIED',outcome['data']['provenance'])
        with self.assertRaises(Invalid):self.service.attempt(self.app,body)
        with self.assertRaises(Invalid):contract.watch(dict(watch,confirm_authorized_reads=False))
        with self.assertRaises(Invalid):self.service.attempt(self.app,dict(body,id='duplicate-source',source_results=body['source_results']*2))

    def test_write_transaction_rechecks_existing_authority_and_rolls_back(self):
        import mission_control.automation_execution as authority
        calls=[]
        def guard(path,db,committing=False):
            calls.append(1)
            if len(calls)==2:raise Invalid('Synthetic standing authority revoked before commit')
        with patch.object(authority,'guard_connection',guard),self.assertRaisesRegex(Invalid,'authority revoked'):self.collect()
        with self.assertRaises(Invalid):self.service.read(self.app,'collection-one','COLLECTION')

    def test_ugc_intake_remains_independent_of_discovery_policy(self):
        from mission_control.managed_media_store import Media
        from tests.test_managed_media_store import synthetic_inspection, RAW
        with patch('mission_control.managed_media_store.inspect',side_effect=synthetic_inspection):
            item=Media(self.store).upload(self.app,'synthetic-ugc.mp4',RAW,dict(manifest_version=1,request_key='ugc-no-viral-stats'))
        self.assertEqual(item['rights_status'],'UNKNOWN');self.assertFalse(item['reuse_available'])
        self.assertFalse(evaluate(self.source,reviewed(baseline=[]),filters(),AS_OF)['qualified'])

    def test_limits_privacy_and_app_currentness(self):
        with self.assertRaises(Invalid):contract.taxonomy(dict(reviewed()['taxonomy'],original_labels=['x']*25))
        value=reviewed();value['card']['authentic_evidence_ids']=['x']*25
        with self.assertRaises(Invalid):contract.review(value)
        value=reviewed();value['card']['rights_status']='APPROVED'
        with self.assertRaises(Invalid):contract.review(value)
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):append(db,self.app,'secret',0,'WATCH',dict(api_key='synthetic-secret'),AS_OF)
            with self.assertRaises(Invalid):capture(db,self.app,self.source['reference_id'],'0'*64)
        saved=self.collect();self.assertTrue(self.service.read(self.app,saved['id'],'COLLECTION')['current_app_context'])
        app=self.store.app(self.app);self.store.save_app(self.app,dict(app['data'],name='Different context'),app['version'])
        self.assertFalse(self.service.read(self.app,saved['id'],'COLLECTION')['current_app_context'])

    def test_revision_document_and_baseline_caps_are_enforced(self):
        with self.assertRaises(Invalid):contract.review(reviewed(baseline=history()*101))
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):append(db,self.app,'too-many-revisions',100,'WATCH',{},AS_OF)
            data=dict(synthetic=True)
            db.executemany('INSERT INTO discovery_documents VALUES(?,?,?,?,?,?,?)',[(self.app,'bounded-'+str(i),1,'WATCH',canonical(data),digest(data),AS_OF) for i in range(1999)])
        with self.assertRaisesRegex(Invalid,'2000 documents'):self.collect()

    def test_facebook_sources_use_the_same_viral_policy(self):
        source=self.add_source(platform='facebook',post_id='facebook-source')
        baseline=[dict(row,platform='facebook') for row in history()]
        self.assertTrue(evaluate(source,reviewed(baseline=baseline),filters(),AS_OF)['qualified'])
        self.assertFalse(evaluate(source,reviewed(baseline=[]),filters(),AS_OF)['included'])
