"""Resolution proposals and execution boundaries; isolated app data only."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import json
import uuid
from datetime import timedelta
from mission_control.common import Invalid
from mission_control.store import Store
from mission_control.service import Service
from mission_control.resolution_plan import prepare,grouped_issues
from mission_control.resolutions import Resolutions,child_state
from mission_control.resolution_tools import execute
from mission_control.common import digest,iso_time,now
from mission_control.db import connection
from mission_control.worker import jobs
from mission_control.worker import run_once


class ResolutionPlanTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'test.sqlite3')
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'website':'https://synthetic.example/','release':'synthetic-release','locale':'en-US'},app['version'])
        self.workspace=Service(self.store).workspace('sample-one')

    def proposal(self,w=None):
        w=w or self.workspace
        return prepare(w['app'],w['records'],w['workflow'],w['preparation']['collection'],w['insights'],w['experiments'])

    def test_all_unverified_inputs_have_explained_options_and_access_paths(self):
        plan=self.proposal()
        self.assertTrue(plan['issues'])
        expected={(step['id'],message) for step in self.workspace['workflow']['steps']
                  for message in [*step['direct_needs'],*step['critical_findings']]}
        actual={(stage,issue['gap']) for issue in plan['issues'] for stage in issue['stages']}
        self.assertEqual(expected,actual)
        for issue in plan['issues']:
            self.assertTrue(issue['options']);self.assertEqual(len(issue['setup_options']),2)
            for option in issue['options']:
                self.assertTrue(all(option[key] for key in ('title','access','artifact','verifies','limits','fallback','cost','stop')))
        self.assertFalse(plan['automatic_external_writes'])
        self.assertEqual(plan['spend_minor'],0)

    def test_preview_has_no_network_or_jobs_and_hash_changes_with_sources(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('No network in proposal')):
            a=self.proposal();b=self.proposal()
        self.assertEqual(a,b)
        self.assertEqual(self.workspace['jobs'],[])
        changed=deepcopy(self.workspace);changed['app']['version']+=1
        self.assertNotEqual(a['source_hash'],self.proposal(changed)['source_hash'])

    def test_foreign_record_rejected_and_same_gap_grouped(self):
        w=deepcopy(self.workspace)
        w['records']=[dict(app_id='sample-two')]
        with self.assertRaises(Invalid):self.proposal(w)
        g=deepcopy(self.workspace['workflow'])
        g['steps']=[dict(id=n,direct_needs=['Add current measurement evidence'],critical_findings=[],
                         primary={'id':'measurement'},verify='Verify test scope') for n in (3,9)]
        issues=grouped_issues(self.workspace['app'],g)
        self.assertEqual(len(issues),1);self.assertEqual(issues[0]['stages'],[3,9])

    def test_missing_destination_does_not_fabricate_execution_or_hide_access(self):
        w=deepcopy(self.workspace);w['app']['data']['website']='http://127.0.0.1/private'
        plan=self.proposal(w)
        for issue in plan['issues']:
            option=next(o for o in issue['options'] if o['tool']=='inspect_site')
            self.assertFalse(option['ready']);self.assertIsNone(option['parameters']['url'])
            self.assertEqual(option['prerequisite'],'app')
            self.assertTrue(issue['setup_options'])


class ResolutionExecutionTests(unittest.TestCase):
    setUp=ResolutionPlanTests.setUp

    def request(self,tool='inspect_site'):
        resolver=Resolutions(self.store);app,plan=resolver.proposal('sample-one')
        issue=plan['issues'][0]
        option=next(o for o in issue['options'] if o['tool']==tool)
        return dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],
                    target_url=None,request_key=str(uuid.uuid4()))

    def test_exact_approval_replay_and_changed_input_rejection(self):
        resolver=Resolutions(self.store);body=self.request()
        first=resolver.start('sample-one',body);second=resolver.start('sample-one',body)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(first['status'],'QUEUED');self.assertEqual(len(jobs(self.store,'sample-one')),1)
        with self.assertRaises(Invalid):resolver.start('sample-one',{**body,'target_url':'https://synthetic.example/changed'})
        with connection(self.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action='resolution.approved'").fetchone()[0],1)
        self.assertEqual(first['data']['envelope_hash'],digest(first['data']['envelope']))

    def test_foreign_stale_extra_and_unready_options_never_queue(self):
        resolver=Resolutions(self.store);body=self.request()
        for invalid in ({**body,'shell':'bad'},{**body,'source_hash':'stale'},{**body,'option_id':'unknown'},
                        {**body,'request_key':'not-canonical'}):
            with self.assertRaises(Invalid):resolver.start('sample-one',invalid)
        with self.assertRaises(Invalid):resolver.start('sample-two',body)
        with self.assertRaises(Invalid):resolver.start('sample-one',self.request('collect_sources'))
        self.assertEqual(jobs(self.store,'sample-one'),[])

    def test_only_same_origin_url_edit_is_permitted(self):
        resolver=Resolutions(self.store);body=self.request()
        for target in ('https://other.example/','https://synthetic.example/?secret=x','http://127.0.0.1/private'):
            with self.assertRaises(Invalid):resolver.start('sample-one',{**body,'target_url':target})
        saved=resolver.start('sample-one',{**body,'target_url':'https://synthetic.example/help'})
        self.assertEqual(saved['data']['envelope']['parameters']['url'],'https://synthetic.example/help')

    def test_site_tool_retains_partial_evidence_not_readiness_pass(self):
        job=Resolutions(self.store).start('sample-one',self.request())
        fixture=dict(id='synthetic-check',hash='f'*64,data={'repairs':['Fix a synthetic metadata gap']})
        with patch('mission_control.aeo_workflows.Checks.run',return_value=fixture) as checked:
            value=execute(self.store,'sample-one',job['data'])
        self.assertEqual(checked.call_count,1)
        self.assertEqual(value['status'],'EVIDENCE_GATHERED')
        self.assertEqual(value['proof_status'],'PARTIAL');self.assertFalse(value['automatically_verified'])
        self.assertFalse(value['external_writes']);self.assertEqual(value['spend_minor'],0)
        self.assertEqual(self.store.records('sample-one'),[])

    def test_expiry_integrity_policy_and_evidence_drift_stop_before_io(self):
        resolver=Resolutions(self.store);job=resolver.start('sample-one',self.request())
        expired=deepcopy(job['data']);expired['envelope']['expires_at']=(iso_time(now())-timedelta(seconds=1)).isoformat()
        expired['envelope_hash']=digest(expired['envelope'])
        tampered=deepcopy(job['data']);tampered['envelope']['tool']='publish'
        with patch('mission_control.aeo_workflows.Checks.run',side_effect=AssertionError('No IO')) as read:
            for data in (expired,tampered):
                with self.assertRaises(Invalid):execute(self.store,'sample-one',data)
            with patch('mission_control.resolution_tools.operating_manifest',return_value={'policy_version':'changed'}):
                with self.assertRaises(Invalid):execute(self.store,'sample-one',job['data'])
            self.store.save_record('sample-one',dict(kind='review',title='New evidence',source='Synthetic',
                data={'release':'synthetic-release','confirmed':False,'severity':'P1','finding':'test'}))
            with self.assertRaises(Invalid):execute(self.store,'sample-one',job['data'])
            read.assert_not_called()

    def test_child_states_cannot_silently_verify_failed_or_missing_sources(self):
        self.assertEqual(child_state([]),'NEEDS_RESOLUTION')
        self.assertEqual(child_state(['MISSING']),'NEEDS_RESOLUTION')
        self.assertEqual(child_state(['SUCCEEDED','BLOCKED']),'NEEDS_RESOLUTION')
        self.assertEqual(child_state(['SUCCEEDED','QUEUED']),'COLLECTING_SOURCES')
        self.assertEqual(child_state(['SUCCEEDED','SUCCEEDED']),'EVIDENCE_GATHERED')

    def test_generic_queue_cannot_bypass_resolution_approval(self):
        with self.assertRaises(Invalid):Service(self.store).queue('sample-one',dict(action='resolution',data={},request_key='anything'))

    def test_worker_public_inspection_persists_evidence_and_restart_history(self):
        from tests.test_aeo_workflows import CountingReader,ROOT
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'website':ROOT+'/page'},app['version'])
        job=Resolutions(self.store).start('sample-one',self.request())
        with patch('mission_control.aeo_workflows.PublicReader',CountingReader):self.assertTrue(run_once(self.store))
        current=next(j for j in jobs(self.store,'sample-one') if j['id']==job['id'])
        self.assertEqual(current['status'],'SUCCEEDED')
        self.assertEqual(len(Service(self.store).workspace('sample-one')['aeo']['checks']),1)
        reopened=Resolutions(Store(self.store.path)).history('sample-one')
        self.assertEqual(reopened[0]['status'],'EVIDENCE_GATHERED')
        self.assertFalse(reopened[0]['automatically_verified'])
        self.assertEqual(self.store.records('sample-one'),[])

    def test_worker_provider_children_do_not_claim_completion_on_dispatch(self):
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'store_app_id':'123'},app['version'])
        self.store.save_record('sample-one',dict(kind='connection',title='Synthetic provider',source='Fixture',
            data=dict(provider='app_store',store_app_id='123',account_id='0',env_ref='SYNTHETIC_TOKEN')))
        resolver=Resolutions(self.store);job=resolver.start('sample-one',self.request('collect_sources'))
        self.assertTrue(run_once(self.store))
        projected=resolver.history('sample-one')[0]
        self.assertEqual(projected['status'],'COLLECTING_SOURCES');self.assertEqual(len(projected['children']),3)
        with patch('mission_control.worker.sync',return_value={'synthetic':True}), \
             patch('mission_control.worker.read_report',return_value={'synthetic':True}):
            for _ in range(3):self.assertTrue(run_once(self.store))
        self.assertEqual(resolver.history('sample-one')[0]['status'],'EVIDENCE_GATHERED')
        self.assertEqual(len(jobs(self.store,'sample-one')),4)

    def test_connected_analytics_dispatch_uses_saved_source_and_preserves_gaps(self):
        from tests.test_measurement_connectors import FakeVault,setup_body,payloads
        from mission_control.insights import Insights
        FakeVault.values={}
        with patch('mission_control.insights.Vault',FakeVault):
            with patch('mission_control.insights_transport.request',side_effect=deepcopy(payloads()['posthog'])):
                Insights(self.store).setup('sample-one',setup_body())
            job=Resolutions(self.store).start('sample-one',self.request('refresh_analytics'))
            with patch('mission_control.insights_transport.request',side_effect=deepcopy(payloads()['posthog'])):
                self.assertTrue(run_once(self.store))
            self.assertEqual(len(Insights(self.store).list('sample-one')['reports']),2)
            row=next(j for j in jobs(self.store,'sample-one') if j['id']==job['id'])
            self.assertEqual(row['result']['proof_status'],'PARTIAL')
            self.assertFalse(row['result']['automatically_verified'])
            self.assertNotIn(setup_body()['api_key'],json.dumps(row))

    def test_actual_experiment_evaluation_and_wait_do_not_invent_a_winner(self):
        from tests.test_experiments import prepared,observations,REGISTER,EXPOSE
        from mission_control.experiments import Experiments
        plan=prepared(self.store);experiments=Experiments(self.store)
        with patch('mission_control.experiments.now',return_value=REGISTER):test=experiments.create('sample-one',plan)
        with patch('mission_control.experiments.now',return_value=EXPOSE):
            experiments.act('sample-one',test['id'],dict(operation='observe',version=test['version'],source='Synthetic exposure',observed_at=EXPOSE))
        for arm in ('control','treatment'):
            Service(self.store).events('sample-one',dict(cohort_id='experiment-'+arm,events=observations(arm)))
        resolver=Resolutions(self.store)
        early=resolver.start('sample-one',self.request('evaluate_experiment'))
        with patch('mission_control.experiments.now',return_value=EXPOSE):self.assertTrue(run_once(self.store))
        early=next(j for j in jobs(self.store,'sample-one') if j['id']==early['id'])
        self.assertEqual(early['result']['status'],'WAITING_FOR_MATURITY')
        self.assertEqual(early['result']['artifacts'],[])
        ready=resolver.start('sample-one',self.request('evaluate_experiment'))
        self.assertTrue(run_once(self.store))
        ready=next(j for j in jobs(self.store,'sample-one') if j['id']==ready['id'])
        self.assertEqual(ready['status'],'SUCCEEDED')
        self.assertFalse(ready['result']['automatically_verified'])
        self.assertEqual(len(experiments.list('sample-one')[0]['assessments']),1)

    def test_cancelled_resolution_does_not_run_and_history_survives_reload(self):
        resolver=Resolutions(self.store);job=resolver.start('sample-one',self.request())
        Service(self.store).cancel('sample-one',job['id'])
        with patch('mission_control.aeo_workflows.Checks.run',side_effect=AssertionError('Cancelled work cannot run')):
            self.assertFalse(run_once(self.store))
        self.assertEqual(Resolutions(Store(self.store.path)).history('sample-one')[0]['status'],'CANCELLED')


if __name__=='__main__':unittest.main()
