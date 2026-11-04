"""Evidence of the current collector-to-brief integration boundary.

The synthetic external-agent assertion is not independently verified collection.
This test intentionally does not claim an end-to-end workflow exists.
"""
import unittest
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
from types import SimpleNamespace
from unittest.mock import patch

from mission_control.db import connection
from mission_control.common import Invalid,canonical,digest,now,uid
from mission_control.organic_video_collector import submit
from mission_control.operation_authority import bound_owner,protected
from mission_control.creative_library import Library
from mission_control.creative_briefs import Briefs
from mission_control.managed_media_store import Media
from mission_control.organic_video_capture import import_owner_demo,intake_envelope,SOURCE
from mission_control.organic_video_policy import Policies
from mission_control.organic_video_workflow import prepare
from mission_control.hypit_jobs import HypitRenders
from mission_control.worker import run_once
from mission_control import campaign_video_execution as video
from mission_control.campaign_contract import REEL_SCHEMA
from tests import test_organic_video_collector as collector_fixture
from tests import test_organic_video_intake as intake_fixture
from tests import test_organic_video_policy as policy_fixture
from tests.test_campaign_video_execution import Transport
from tests.production_fixtures import ready_capabilities
from tests.test_managed_media_store import synthetic_inspection


class WorkflowBoundaryTests(unittest.TestCase):
    def test_submitted_qualified_candidate_is_not_yet_a_discovery_collection(self):
        fixture=collector_fixture.CollectorTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        task=fixture.owner_call();claimed=fixture.claim_task(task)
        result=fixture.agent_call('organic-video.submit',fixture.submission(task,claimed),submit)
        self.assertEqual(result['status'],'SUBMITTED')
        self.assertEqual(result['result']['items'][0]['status'],'COLLECTION_REVIEW_REQUIRED')
        self.assertEqual(result['result']['collection_verification'],'REQUIRED')
        with connection(fixture.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_discovery_tasks WHERE submission_hash IS NOT NULL').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM discovery_documents').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM creative_captures').fetchone()[0],0)
        self.assertEqual(result['publication'],'NOT_RUN')


class VerticalWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.f=intake_fixture.IntakeTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.store=self.f.store;self.app=self.f.app;self.owner=self.f.fixture.owner
        self.intake=self.f.call();value=self.intake['data']
        source=next(x for x in Library(self.store).list(self.app) if x['id']==value['source']['id'])
        ready_capabilities(self.store,self.app,[source])
        definition=dict(self.f.brief,analysis_id=value['analysis']['id'],analysis_hash=value['analysis']['hash'],
            discovery=dict(schema='wmm.brief-discovery.v1',mode='ORIGINAL_RECREATION',manifest_version=self.store.app(self.app)['version'],
                collection_id=value['collection']['id'],collection_hash=value['collection']['hash'],
                reference_id=value['source']['id'],review_hash=value['review']['hash']))
        self.brief=Briefs(self.store).save(self.app,dict(data=definition))
        def inspect(raw,suffix,alive):
            value=synthetic_inspection(raw,suffix,alive);value['metadata']['duration_seconds']=60.;value['decoded']['video_frames']=1440
            return value
        self.media=Media(self.store,inspector=inspect)
        selection=dict(request_id='owned-clip',manifest_version=self.store.app(self.app)['version'],
            release=self.store.app(self.app)['data']['release'],filename='synthetic-demo.mp4',source=SOURCE,
            app_owned=True,contains_private_data=False,uses_personal_account=False)
        envelope=intake_envelope(self.app,selection,b'synthetic-owned-footage')
        with bound_owner(self.store,envelope,collector_fixture.Identities(),'owner-session',self.owner):
            with patch('mission_control.organic_video_capture.Media',return_value=self.media):
                imported=import_owner_demo(self.store,self.app,selection,b'synthetic-owned-footage')
        self.source=dict(id=imported['media_id'],source_sha256=imported['source_sha256'])
        self.review=dict(expected_version=0,manifest_version=self.store.app(self.app)['version'],
                         source_sha256=self.source['source_sha256'],status='ALLOWED',basis='OWNED',evidence='Synthetic owner recording')
        self.source=self.media.review(self.app,self.source['id'],self.review,self.owner)
        stamp=now();self.connection=uid();self.template=uid()
        with connection(self.store.path) as db:
            db.execute('INSERT INTO social_configs VALUES(?,?,?,?,?,?,?,?)',(self.app,'facebook',1,canonical(dict(provider='facebook')),'fixture','CONFIGURED_UNTESTED',stamp,stamp))
            db.execute('INSERT INTO social_connections VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (self.app,self.connection,'facebook',1,1,'fixture-subject',canonical(dict(destination=dict(id='123'))),'fixture',
                 'CONNECTED_READ_TESTED',None,None,0,None,0,stamp,stamp))
        self.raw=b'synthetic-workflow-output'
        policy=dict(connection_id=self.connection,page_id='123',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
            sources=[dict(id=self.source['id'],sha256=self.source['source_sha256'],review_version=1)],
            claims=[dict(id=x['id'],sha256=x['hash']) for x in self.brief['data']['records'] if x['kind']=='claim'],
            templates=[dict(id=self.template,caption='Exact synthetic app demo',claim_ids=[x['id'] for x in self.brief['data']['records'] if x['kind']=='claim'])],
            transformations=['DECLARATIVE_COMPOSITION'],generation_providers=['HYPIT_LOCAL'],currency='USD',max_model_minor=0,
            max_generations=1,max_posts=1,max_calls=40,approved_output_hashes=[hashlib.sha256(self.raw).hexdigest()])
        self.policy=self.call('policy-create',dict(request_id=uid(),policy=policy),lambda body:Policies(self.store).create(self.app,body))
        self.body=dict(request_id=uid(),intake_id=self.intake['id'],intake_hash=self.intake['hash'],
            policy_id=self.policy['id'],policy_hash=self.policy['hash'],template_id=self.template,
            render_input=dict(brief_id=self.brief['id'],brief_hash=self.brief['hash'],shape='PORTRAIT',
                footage=[dict(scene_index=0,id=self.source['id'],sha256=self.source['source_sha256'],in_frame=0,audio='MUTE')]))

    def call(self,operation,body,function):
        envelope=dict(app_id=self.app,operation='organic-video.'+operation,input=body)
        with bound_owner(self.store,envelope,collector_fixture.Identities(),'owner-session',self.owner):
            with protected(self.store,envelope):return function(body)

    def plan(self,body=None):
        return self.call('workflow-prepare',body or self.body,lambda value:prepare(self.store,self.app,self.owner['principal'],value))

    def render(self,reservation):
        def runtime(folder,scene,alive,submitted,sources):
            self.assertEqual(sources[0],b'synthetic-owned-footage');alive();submitted('bld_WORKFLOW_00000001')
            (folder/'video.mp4').write_bytes(self.raw);(folder/'font.ttf').write_bytes(b'synthetic-font')
            return dict(build_id='bld_WORKFLOW_00000001',artifact=dict(sha256=hashlib.sha256(self.raw).hexdigest(),bytes=len(self.raw)),
                source=dict(source_hashes={},font_sha256=hashlib.sha256(b'synthetic-font').hexdigest()),
                cleanup=dict(worker='STOPPED'),local_plan=deepcopy(policy_fixture.LOCAL_PLAN))
        request=dict(data=reservation['data']['render_input'],request_key=reservation['data']['job_request_key'])
        with patch('mission_control.hypit_jobs.identity',return_value=dict(launcher='fixture',launcher_sha256='0'*64)):
            job=HypitRenders(self.store).queue(self.app,request)
        with patch('mission_control.hypit_jobs.render',side_effect=runtime):self.assertTrue(run_once(self.store))
        return job,HypitRenders(self.store).list(self.app)['items'][0]

    def test_submitted_source_to_real_local_records_and_fake_reel_recovery(self):
        plan=self.plan();self.assertEqual(plan,self.plan());self.assertEqual(plan['data']['publication'],'NOT_RUN')
        import json
        provenance=self.brief['data']['discovery']['collection_provenance']
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
            task=db.execute('SELECT * FROM organic_discovery_tasks WHERE id=?',(provenance['task_id'],)).fetchone()
            self.assertEqual(task['submission_hash'],provenance['submission_hash'])
            self.assertEqual(task['result_hash'],provenance['result_hash'])
            self.assertEqual(digest(json.loads(task['submission'])['candidates'][0]['candidate']),provenance['candidate_hash'])
        reservation=self.call('policy-reserve',plan['data']['next_operation']['input'],lambda b:Policies(self.store).reserve(self.app,b))
        self.assertEqual(reservation['data']['inputs_hash'],plan['data']['inputs_hash'])
        job,artifact=self.render(reservation)
        admission=self.call('policy-admit',dict(policy_id=self.policy['id'],policy_hash=self.policy['hash'],output=dict(
            request_id=uid(),artifact_id=artifact['id'],artifact_sha256=artifact['data']['artifact']['sha256'],template_id=self.template,
            caption='Exact synthetic app demo',transformation='DECLARATIVE_COMPOSITION',reserve_calls=40,
            reservation_id=reservation['id'],reservation_hash=reservation['hash'])),lambda b:Policies(self.store).admit(self.app,b))
        body=dict(schema=REEL_SCHEMA,request_id=uid(),app_id=self.app,page_id='123',policy_id=self.policy['id'],policy_hash=self.policy['hash'],
            admission_id=admission['id'],admission_hash=admission['hash'],artifact_id=artifact['id'],artifact_sha256=artifact['data']['artifact']['sha256'],
            caption='Exact synthetic app demo',rights_hashes=sorted({x['rights_hash'] for x in admission['data']['proofs']['sources']}))
        intent=self.call('intent-create',body,lambda b:video.create_intent(self.store,self.app,self.owner['principal'],b))
        transport=Transport();transport.failure='publish'
        def facebook(config,secret,token,alive):
            alive();return SimpleNamespace(subject_id='fixture-subject',permissions=['pages_manage_posts','pages_show_list','pages_read_engagement'])
        def page(secret,token,identity,alive):alive();return dict(id='123',tasks=['CREATE_CONTENT']),'synthetic-page-token'
        with patch.object(video,'_credentials',return_value=({},'synthetic-secret',dict(access_token='synthetic-user'))),patch.object(video,'facebook',side_effect=facebook),patch.object(video,'selected_page',side_effect=page):
            from mission_control.campaign_transport import Unconfirmed
            with self.assertRaises(Unconfirmed):
                self.call('intent-execute',dict(intent_id=intent['id']),lambda b:video.execute(self.store,self.app,self.owner['principal'],b['intent_id'],transport))
            with connection(self.store.path) as db:
                interrupted=video._view(video._row(db,self.app,intent['id']))
            self.assertEqual(interrupted['stage'],'FINISH_PENDING')
            self.assertTrue(interrupted['finish_attempted'])
            self.assertEqual(interrupted['remote_id'],'456')
            transport.failure=None
            result=self.call('intent-reconcile',dict(intent_id=intent['id']),lambda b:video.reconcile(self.store,self.app,self.owner['principal'],b['intent_id'],transport))
        self.assertEqual(result['stage'],'PROVIDER_PHASE_COMPLETE');self.assertEqual(transport.calls.count('publish'),1)
        self.assertEqual(result['remote_id'],'456');self.assertEqual(result['observation']['video_id'],'456')
        self.assertEqual(result['observation']['publishing_phase'],'complete')
        self.assertEqual(transport.calls[-1],'read')
        self.assertEqual(result['public_visibility'],'NOT_VERIFIED');self.assertIsNone(result['measured_app_outcome'])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM campaign_video_intents').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='hypit_render'").fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master WHERE name='campaign_paid_intents'").fetchone()[0],0)
        self.assertEqual(self.brief['data']['discovery']['collection_provenance']['intake_id'],self.intake['id'])

    def test_prepare_binds_exact_intake_and_changed_rights_block_reserved_render(self):
        with self.assertRaises(Invalid):self.plan(dict(self.body,intake_hash='0'*64))
        plan=self.plan()
        reservation=self.call('policy-reserve',plan['data']['next_operation']['input'],lambda b:Policies(self.store).reserve(self.app,b))
        self.media.review(self.app,self.source['id'],dict(self.review,expected_version=1,status='REVOKED'),self.owner)
        with self.assertRaises(Invalid):self.render(reservation)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_generation_reservations').fetchone()[0],1)


if __name__=='__main__':unittest.main()
