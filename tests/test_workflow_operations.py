"""Workflow operations through actual scoped gateway, domains and local worker."""
import json
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.operator_client import OperatorClient,ClientError
from mission_control.operation_catalog import request_data
from mission_control.store import Store
from mission_control.worker import run_once,jobs
from tests import test_agent_review_http as fixture
from tests.test_mission_control import evidence_data


class WorkflowOperationTests(unittest.TestCase):
    setUp=fixture.ReviewHTTPTests.setUp
    setUp_base=fixture.ReviewHTTPTests.setUp_base
    tearDown=fixture.ReviewHTTPTests.tearDown
    body=fixture.ReviewHTTPTests.body
    envelope=fixture.ReviewHTTPTests.envelope
    listing_body=fixture.ReviewHTTPTests.listing_body
    issue_reviewed=fixture.ReviewHTTPTests.issue_reviewed
    human=fixture.ReviewHTTPTests.human
    approve=fixture.ReviewHTTPTests.approve

    def workflow_grant(self,review=False,max_calls=100):
        names=['evidence.save','pipeline.prepare','jobs.read','job.cancel','workspace.read','operations.read']
        value=self.body(names,max_calls)
        value['review_operations']=['evidence.save','pipeline.prepare','job.cancel'] if review else []
        issued=self.owner.request('POST','/api/apps/sample-one/agent-grants/issue',value)
        return OperatorClient(self.origin,grant_token=issued['token']),issued

    def evidence(self,kind='measurement',identity='agent-evidence'):
        return dict(id=identity,manifest_version=1,kind=kind,title='Synthetic workflow evidence',source='Synthetic inspected fixture; operator assertion',data=evidence_data(kind))

    def pipeline(self,key='workflow-pipeline',stage=0):
        return self.envelope('pipeline.prepare',dict(action='pipeline',data=dict(stage=stage),request_key=key))

    def test_evidence_create_update_conflict_and_cross_app_isolation(self):
        client,_=self.workflow_grant();body=self.evidence()
        saved=client.call(self.envelope('evidence.save',body))
        self.assertEqual(saved['kind'],'measurement');self.assertEqual(saved['app_id'],'sample-one')
        changed=client.call(self.envelope('evidence.save',dict(body,version=saved['version'],title='Corrected assertion')))
        self.assertEqual(changed['version'],2)
        for value in (dict(body,manifest_version=2),dict(body,version=1)):
            with self.assertRaises(ClientError):client.call(self.envelope('evidence.save',value))
        with self.assertRaises(ClientError):client.call(self.envelope('evidence.save',body,app_id='sample-two'))
        self.assertEqual(self.store.records('sample-two'),[])
        self.assertEqual(Store(self.store.path,seed=False).records('sample-one')[0]['hash'],changed['hash'])

    def test_connection_and_hidden_pipeline_fields_reject_before_network(self):
        client,_=self.workflow_grant()
        invalid=[self.envelope('evidence.save',dict(self.evidence(),kind='connection')),self.envelope('evidence.save',dict(self.evidence(),approved=True))]
        invalid.extend(self.envelope('pipeline.prepare',value) for value in [dict(action='sync',data=dict(stage=0),request_key='x'),dict(action='render',data=dict(stage=0),request_key='x'),dict(action='pipeline',data=dict(stage=0,connection_id='x'),request_key='x'),dict(action='pipeline',data=dict(stage=True),request_key='x'),dict(action='pipeline',data=dict(stage=13),request_key='x'),dict(action='pipeline',data=dict(stage=-1),request_key='x'),dict(action='pipeline',data=dict(stage=1),request_key=''),dict(action='pipeline',data=dict(stage=1),request_key='x'*121)])
        with patch.object(client,'request') as transport:
            for value in invalid:
                with self.subTest(value=value),self.assertRaises(Invalid):client.call(value)
            transport.assert_not_called()
        self.assertEqual(jobs(self.store,'sample-one'),[])

    def test_existing_connection_kind_and_new_record_version_cannot_be_repurposed(self):
        client,_=self.workflow_grant()
        connection_row=self.store.save_record('sample-one',dict(kind='connection',title='Preserved connection',source='Synthetic protected fixture',manifest_version=1,data=dict(provider='app_store',account_id='fixture',store_app_id='123')))
        body=dict(self.evidence(identity=connection_row['id']),version=connection_row['version'])
        for caller in (client,self.owner):
            with self.assertRaises(ClientError):caller.call(self.envelope('evidence.save',body))
        self.assertEqual(self.store.records('sample-one')[0]['hash'],connection_row['hash'])
        with self.assertRaises(ClientError):client.call(self.envelope('evidence.save',dict(self.evidence(),version=1)))
        saved=client.call(self.envelope('evidence.save',self.evidence()))
        with self.assertRaises(ClientError):client.call(self.envelope('evidence.save',dict(self.evidence(),version=True)))
        with self.assertRaises(ClientError):client.call(self.envelope('evidence.save',dict(self.evidence('claim'),version=saved['version'])))
        self.assertEqual(next(r for r in self.store.records('sample-one') if r['id']==saved['id'])['kind'],'measurement')

    def test_pipeline_queue_is_distinct_from_completed_real_twelve_output_result(self):
        client,_=self.workflow_grant()
        queued=client.call(self.pipeline());self.assertEqual(queued['status'],'QUEUED');self.assertIsNone(queued['result'])
        self.assertEqual(client.call(self.pipeline())['id'],queued['id'])
        with self.assertRaises(ClientError):client.call(self.pipeline(stage=1))
        self.assertTrue(run_once(self.store))
        saved=client.call(self.envelope('jobs.read'))[0]
        self.assertEqual(saved['id'],queued['id']);self.assertEqual(saved['status'],'SUCCEEDED')
        self.assertEqual(len(saved['result']['outputs']),12)
        self.assertEqual(saved['result']['external_execution'],'NOT_RUN');self.assertEqual(saved['result']['spend_minor'],0)
        with self.assertRaises(ClientError):client.call(dict(self.envelope('job.cancel'),resource_id=queued['id']))

    def test_cancellation_is_scoped_durable_and_does_not_create_worker_outputs(self):
        client,_=self.workflow_grant();queued=client.call(self.pipeline())
        with self.assertRaises(ClientError):client.call(dict(self.envelope('job.cancel',app_id='sample-two'),resource_id=queued['id']))
        self.assertEqual(client.call(dict(self.envelope('job.cancel'),resource_id=queued['id']))['status'],'CANCELLED')
        self.assertFalse(run_once(self.store));saved=client.call(self.envelope('jobs.read'))[0]
        self.assertEqual(saved['status'],'CANCELLED');self.assertIsNone(saved['result'])
        with self.assertRaises(ClientError):client.call(dict(self.envelope('job.cancel'),resource_id=queued['id']))

    def test_review_required_enqueue_cannot_dispatch_early_or_twice(self):
        client,_=self.workflow_grant(review=True);envelope=self.pipeline()
        with self.assertRaises(ClientError):client.call(envelope)
        view=client.review('prepare',dict(id='pipeline-reviewed',envelope=envelope))
        row=view['checkpoint'];self.assertEqual(jobs(self.store,'sample-one'),[])
        with self.assertRaises(ClientError):client.review('resume',dict(app_id='sample-one',id=view['id'],revision=row['revision'],packet_hash=row['hash']))
        approved=self.approve(view)
        result=client.review('resume',dict(app_id='sample-one',id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(result['checkpoint']['state'],'SUCCEEDED')
        self.assertEqual(result['result']['data']['status'],'QUEUED')
        with self.assertRaises(ClientError):client.review('resume',dict(app_id='sample-one',id=view['id'],revision=approved['revision'],packet_hash=approved['hash']))
        self.assertEqual(len(jobs(self.store,'sample-one')),1);self.assertTrue(run_once(self.store))

    def test_jobs_route_exact_query_and_bounded_app_history(self):
        client,_=self.workflow_grant(max_calls=200)
        for index in range(101):client.call(self.pipeline('bounded-'+str(index)))
        rows=client.call(self.envelope('jobs.read'));self.assertEqual(len(rows),100)
        self.assertEqual(len(self.owner.request('GET','/api/apps/sample-one/jobs')),100)
        self.assertEqual(self.owner.request('GET','/api/apps/sample-two/jobs'),[])
        with self.assertRaises(ClientError):self.owner.request('GET','/api/apps/sample-one/jobs?all=true')
        with self.assertRaises(ClientError):self.owner.request('GET','/api/apps/missing-app/jobs')

    def test_legacy_local_client_and_catalog_currentness(self):
        body=self.evidence();saved=self.owner.call(self.envelope('evidence.save',body))
        self.assertEqual(saved['data'],body['data'])
        queued=self.owner.call(self.pipeline());self.assertEqual(self.owner.call(self.envelope('jobs.read'))[0]['id'],queued['id'])
        self.owner.call(dict(self.envelope('job.cancel'),resource_id=queued['id']))
        discovery=self.owner.call(self.envelope('operations.read'))
        self.assertIn('pipeline.prepare',discovery['local_catalog']['operations'])
        self.assertEqual(discovery['checkpoints'][1]['state'],'SCOPED_GRANTS_AND_INDEPENDENT_REVIEW_IMPLEMENTED')
        self.assertFalse(discovery['execution_authority'])
        self.assertEqual(discovery['local_catalog']['workflow']['job_submission'],'QUEUED_IS_NOT_COMPLETED')
