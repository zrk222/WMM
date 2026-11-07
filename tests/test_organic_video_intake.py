"""Protected owner intake of synthetic external-agent reports into native briefs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from mission_control.common import Invalid, digest, now, uid
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.organic_video_collector import submit
from mission_control.organic_video_intake import adopt
from mission_control.creative_briefs import Briefs
from tests import test_organic_video_collector as collector_fixture
from tests.test_creative_production import ready_production
from tests.test_discovery_intelligence import reviewed, filters
from tests.production_fixtures import ready_capabilities
from mission_control.creative_library import Library
from mission_control.discovery_store import Discovery


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.fixture=collector_fixture.CollectorTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.store=self.fixture.store;self.app='sample-one'
        app=self.store.app(self.app)
        self.store.save_app(self.app,dict(app['data'],name='Synthetic QA App',job='Rehearse a conversation',audience='Synthetic users',
            activation='Fictional next step',release='test-build',locale='en-US',currency='USD'),app['version'])
        self.fixture.grant=self.fixture.grants.issue(self.app,self.fixture.owner,dict(agent_id='personal-agent',manifest_version=2,
            expires=self.fixture.expires,operations=['organic-video.claim','organic-video.submit'],max_calls=100))
        self.fixture.body['policy']['recipient_grant_id']=self.fixture.grant['grant']['id']
        _,_,self.records,self.brief=ready_production(self.store,self.app)
        task=self.fixture.owner_call();claim=self.fixture.claim_task(task)
        request=self.fixture.submission(task,claim);result=self.fixture.agent_call('organic-video.submit',request,submit)
        candidate=request['result']['candidates'][0]['candidate'];stamp=datetime.now(timezone.utc)
        review=reviewed();review.pop('baseline');review['card']['authentic_evidence_ids']=[self.records['asset']['id']]
        analysis=dict(inspection_kind='DIRECT_VIEW',inspection_confirmed=True,inspected_at=now(),analyst='Synthetic reviewer',
            format_family='Question demonstration',duration_seconds=30,observations=[dict(role='HOOK',basis='OBSERVED',
            detail='Synthetic observation',evidence_note='Synthetic inspection',start_seconds=0,end_seconds=3)],uncertainty='Synthetic fixture only')
        self.body=dict(request_id='intake-one',task_id=task['id'],task_hash=task['task_hash'],submission_hash=result['submission_hash'],
            result_hash=digest(result['result']),candidate_id=candidate['post_id'],candidate_hash=digest(candidate),
            source_metadata=dict(title='Synthetic reference',locale=self.store.app(self.app)['data']['locale'],traffic_class='UNKNOWN',
                                 topic='Synthetic topic',relevance_note='Synthetic review',permission_confirmed=True),
            review=review,analysis=analysis,query=filters(published_after=(stamp-timedelta(days=3)).isoformat(),
                published_before=(stamp+timedelta(minutes=1)).isoformat()))

    def call(self,body=None,actor=None):
        body=self.body if body is None else body
        envelope=dict(app_id=self.app,operation='organic-video.intake',input=body)
        with bound_owner(self.store,envelope,collector_fixture.Identities(),'owner-session',self.fixture.owner):
            with protected(self.store,envelope) as accepted:return adopt(self.store,self.app,actor or accepted,body)

    def test_adoption_binds_exact_report_through_real_brief(self):
        result=self.call();self.assertEqual(result,self.call())
        self.assertEqual(result['data']['provenance']['classification'],'EXTERNAL_AGENT_REPORTED_NOT_INDEPENDENTLY_VERIFIED')
        self.assertEqual(result['data']['foreign_bytes'],'NOT_AUTHORIZED')
        identity=result['data'];source=next(x for x in Library(self.store).list(self.app) if x['id']==identity['source']['id'])
        ready_capabilities(self.store,self.app,[source])
        value=dict(self.brief,analysis_id=identity['analysis']['id'],analysis_hash=identity['analysis']['hash'],
            discovery=dict(schema='wmm.brief-discovery.v1',mode='ORIGINAL_RECREATION',manifest_version=self.store.app(self.app)['version'],
                collection_id=identity['collection']['id'],collection_hash=identity['collection']['hash'],
                reference_id=identity['source']['id'],review_hash=identity['review']['hash']))
        brief=Briefs(self.store).save(self.app,{'data':value})
        self.assertEqual(brief['data']['discovery']['collection_provenance'],identity['provenance'])
        self.assertEqual(identity['provenance']['intake_id'],result['id'])
        self.assertEqual(brief['data']['source']['data']['rights'],'REFERENCE_ONLY')
        self.assertEqual(brief['data']['publication'],'NOT_RUN')

    def test_bad_binding_and_invalid_supplied_proof_roll_back(self):
        for changes in (dict(candidate_hash='0'*64),dict(result_hash='0'*64),dict(submission_hash='0'*64),dict(candidate_id='wrong')):
            with self.subTest(changes=changes),self.assertRaises(Invalid):self.call(dict(self.body,**changes))
        value=deepcopy(self.body);value['review']['card']['authentic_evidence_ids']=['missing-app-proof']
        with self.assertRaises(Invalid):self.call(value)
        with self.assertRaises(PermissionError):self.call(actor='github:forged')
        with connection(self.store.path) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='organic_video_intakes'").fetchone()
            self.assertFalse(exists)
            self.assertEqual(db.execute('SELECT count(*) FROM discovery_documents').fetchone()[0],0)

    def test_same_post_id_on_two_platforms_adopts_each_exact_candidate(self):
        body = deepcopy(self.fixture.body)
        body['request_id'] = 'mixed-platform-task'
        body['policy']['platforms'].append('facebook')
        body['policy']['hosts'].append('www.facebook.com')
        task = self.fixture.owner_call(body)
        claim = self.fixture.claim_task(task)
        request = self.fixture.submission(task, claim)
        tiktok = request['result']['candidates'][0]
        facebook = deepcopy(tiktok)
        for observation, receipt in zip([facebook['candidate'], *facebook['history']], facebook['evidence']):
            url = 'https://www.facebook.com/reel/' + observation['post_id']
            observation.update(platform='facebook', format='reel', url=url)
            receipt.update(url=url, observation_hash=digest(observation))
        request['result']['candidates'].append(facebook)
        request['result']['read_count'] = 22
        result = self.fixture.agent_call('organic-video.submit', request, submit)
        self.assertEqual([row['status'] for row in result['result']['items']], ['COLLECTION_REVIEW_REQUIRED'] * 2)
        for item in (facebook, tiktok):
            candidate = item['candidate']
            value = dict(self.body, request_id=uid(), task_id=task['id'], task_hash=task['task_hash'],
                         submission_hash=result['submission_hash'], result_hash=digest(result['result']),
                         candidate_id=candidate['post_id'], candidate_hash=digest(candidate))
            intake = self.call(value)
            self.assertEqual(self.call(value), intake)
            source = next(row for row in Library(self.store).list(self.app) if row['id'] == intake['data']['source']['id'])
            self.assertEqual(source['current']['data']['platform'], candidate['platform'])
            self.assertEqual(source['current']['data']['url'], candidate['url'])
            self.assertEqual(intake['data']['foreign_bytes'], 'NOT_AUTHORIZED')
            self.assertEqual(intake['data']['publication'], 'NOT_RUN')

    def test_research_without_app_proof_saves_but_cannot_enter_production(self):
        value=deepcopy(self.body);value['review']['card']['authentic_evidence_ids']=[]
        value['review']['card'].update(rights_status='ALLOWED_BY_ATTESTATION',rights_evidence='Synthetic owner permission')
        result=self.call(value);self.assertEqual(result,self.call(value))
        identity=result['data']
        self.assertEqual(identity['foreign_bytes'],'NOT_AUTHORIZED')
        self.assertEqual(identity['publication'],'NOT_RUN')
        handoff=dict(manifest_version=self.store.app(self.app)['version'],collection_id=identity['collection']['id'],
            collection_hash=identity['collection']['hash'],reference_id=identity['source']['id'],review_hash=identity['review']['hash'])
        with self.assertRaisesRegex(Invalid,'Select authentic app proof'):
            Discovery(self.store).handoff(self.app,handoff)
        source=next(x for x in Library(self.store).list(self.app) if x['id']==identity['source']['id'])
        ready_capabilities(self.store,self.app,[source])
        brief=dict(self.brief,analysis_id=identity['analysis']['id'],analysis_hash=identity['analysis']['hash'],
            discovery=dict(schema='wmm.brief-discovery.v1',mode='ORIGINAL_RECREATION',**handoff))
        with self.assertRaisesRegex(Invalid,'Select authentic app proof'):
            Briefs(self.store).save(self.app,{'data':brief})

    def test_replay_conflict_stale_app_and_concurrent_exact_replay(self):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.call(),range(2)))
        self.assertEqual(results[0],results[1])
        changed=deepcopy(self.body);changed['source_metadata']['title']='Changed'
        with self.assertRaises(Invalid):self.call(changed)
        app=self.store.app(self.app);self.store.save_app(self.app,dict(app['data'],name='Changed app'),app['version'])
        with self.assertRaises(Invalid):self.call()

    def test_stale_observation_and_unconfirmed_source_permission_rejected(self):
        later=(datetime.now(timezone.utc)+timedelta(hours=25)).isoformat()
        with patch('mission_control.organic_video_intake.now',return_value=later),self.assertRaisesRegex(Invalid,'stale'):
            self.call()
        value=deepcopy(self.body);value['source_metadata']['permission_confirmed']=False
        with self.assertRaises(Invalid):self.call(value)

    def test_prior_agent_grant_revocation_does_not_erase_owner_adoption(self):
        with connection(self.store.path) as db:
            db.execute("UPDATE agent_grants SET status='REVOKED',version=version+1 WHERE id=?",(self.fixture.grant['grant']['id'],))
        self.assertEqual(self.call()['data']['publication'],'NOT_RUN')

    def test_different_request_cannot_duplicate_adopted_platform_post(self):
        self.call()
        with self.assertRaisesRegex(Invalid, 'already has an inspection'):
            self.call(dict(self.body, request_id=uid()))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_intakes').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM discovery_documents WHERE kind='COLLECTION'").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM discovery_documents WHERE kind='REVIEW'").fetchone()[0], 1)

    def test_review_metrics_cannot_replace_submitted_views_and_transcript_permission_stays_explicit(self):
        value=deepcopy(self.body)
        value['review']['metrics']=dict(views=999999, likes=1, comments=1, shares=None, observed_at=now())
        with self.assertRaises(Invalid):
            self.call(value)
        value=deepcopy(self.body)
        value['review']['transcript']=dict(permission_confirmed=False, language='en', source='Synthetic source',
            observed_at=now(), duration_ms=30000, uncertainty='Synthetic fixture', segments=[])
        with self.assertRaisesRegex(Invalid, 'permission'):
            self.call(value)

    def test_current_owner_revocation_and_changed_protected_body_deny_adoption(self):
        envelope=dict(app_id=self.app,operation='organic-video.intake',input=self.body)
        with bound_owner(self.store,envelope,collector_fixture.Identities(),'owner-session',self.fixture.owner):
            with protected(self.store,envelope) as actor:
                with self.assertRaises(PermissionError):
                    adopt(self.store,self.app,actor,dict(self.body,request_id=uid()))
        with connection(self.store.path) as db:
            db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=? AND principal=?",
                       (self.app,self.fixture.owner['principal']))
        with self.assertRaises(PermissionError):
            self.call()


if __name__=='__main__':unittest.main()
