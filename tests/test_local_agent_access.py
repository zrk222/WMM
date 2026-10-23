"""App-owned local profile, protected optional key and actual worker integration."""
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
from mission_control.common import Invalid,canonical
from mission_control.store import Store
from mission_control.agent_access import AgentAccess
from mission_control.agent_contract import profile
from mission_control.agent_tasks import AgentWork,proposal
from mission_control.worker import run_once,jobs
from mission_control.service import Service
from tests.test_local_agent_api import ModelServer
from tests.test_measurement_connectors import FakeVault
from tests.test_agent_access import answer,connection_test_fixture,body as public_body


def local_body(url,key=''):
    return dict(provider='local_api',label='Synthetic local model',model='synthetic-model',endpoint=url,api_key=key,allow_api_charges=True,id=None,version=None)


class LocalAccessTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'local.sqlite');self.access=AgentAccess(self.store)
        self.model=ModelServer();self.addCleanup(self.model.close)
        FakeVault.values={};self.vault=patch('mission_control.agent_access.Vault',FakeVault);self.vault.start();self.addCleanup(self.vault.stop)

    def approve(self,identity,task='connection_test'):
        data=dict(task=task,focus='',connection_id=identity);review=proposal(self.store,'sample-one',data)
        return AgentWork(self.store).start('sample-one',dict(data,source_hash=review['source_hash'],request_key=str(uuid.uuid4())))

    def test_keyless_profile_does_not_stage_secret_and_local_routing_is_explicit(self):
        identity=self.access.save('sample-one',local_body(self.model.url))['connection']
        row=self.access.get('sample-one',identity)
        self.assertIsNone(self.access.secret('sample-one',row));self.assertNotIn('credential_ref',row['data'])
        self.assertFalse(self.access.view('sample-one')['profiles'][0]['data']['protected_key'])
        self.access.routes('sample-one',dict(version=0,mode='local',routes={'campaign_plan':identity}))
        self.assertEqual(self.access.view('sample-one')['routing']['data']['mode'],'local')
        with self.assertRaises(Invalid):self.access.routes('sample-one',dict(version=1,mode='byok',routes={'campaign_plan':identity}))
        with self.assertRaises(Invalid):self.access.routes('sample-two',dict(version=0,mode='local',routes={'campaign_plan':identity}))

    def test_optional_key_is_protected_rotated_removed_and_excluded_from_exports(self):
        key='synthetic-local-secret';identity=self.access.save('sample-one',local_body(self.model.url,key))['connection']
        row=self.access.get('sample-one',identity);self.assertEqual(self.access.secret('sample-one',row),key)
        self.assertNotIn(key,canonical(self.access.view('sample-one')));self.assertNotIn(key,canonical(self.store.export('sample-one')))
        self.access.save('sample-one',dict(local_body(self.model.url),id=identity,version=1))
        self.assertIsNone(self.access.secret('sample-one',self.access.get('sample-one',identity)))
        self.assertFalse(FakeVault.values)

    def test_real_worker_capability_test_then_routed_draft(self):
        identity=self.access.save('sample-one',local_body(self.model.url))['connection']
        self.model.value['choices'][0]['message']['content']=canonical(connection_test_fixture())
        self.approve(identity);self.assertTrue(run_once(self.store))
        self.assertEqual(self.access.get('sample-one',identity)['status'],'TESTED')
        self.access.routes('sample-one',dict(version=0,mode='local',routes={'campaign_plan':identity}))
        self.model.value['choices'][0]['message']['content']=canonical(answer())
        queued=self.approve(identity,'campaign_plan');self.assertTrue(run_once(self.store))
        saved=next(r for r in jobs(self.store,'sample-one') if r['id']==queued['id'])
        self.assertEqual(saved['status'],'SUCCEEDED');self.assertEqual(saved['result']['draft'],answer())
        self.assertEqual(saved['result']['publication'],'NOT_RUN');self.assertFalse(saved['result']['automatically_verified'])
        self.assertEqual(len(self.model.calls),2)

    def test_changed_profile_and_cancelled_job_do_not_send_or_fallback(self):
        identity=self.access.save('sample-one',local_body(self.model.url))['connection']
        queued=self.approve(identity)
        self.access.save('sample-one',dict(local_body(self.model.url),id=identity,version=1))
        run_once(self.store);self.assertEqual(self.model.calls,[])
        self.assertEqual(next(r for r in jobs(self.store,'sample-one') if r['id']==queued['id'])['status'],'BLOCKED')
        queued=self.approve(identity);Service(self.store).cancel('sample-one',queued['id']);self.assertFalse(run_once(self.store));self.assertEqual(self.model.calls,[])

    def test_local_consent_model_and_url_validation_leave_public_rules_intact(self):
        for change in ({'allow_api_charges':False},{'model':''},{'endpoint':'https://remote.example/v1'},{'api_key':'bad key'}):
            with self.subTest(change=change),self.assertRaises(Invalid):profile(dict(local_body(self.model.url),**change))
        self.assertEqual(profile(public_body())['endpoint'],'https://synthetic.example/v1')
        with self.assertRaises(Invalid):profile(dict(public_body(),endpoint=self.model.url))

    def test_local_server_errors_do_not_mark_tested_or_replay_request(self):
        identity=self.access.save('sample-one',local_body(self.model.url))['connection']
        self.model.status=500;queued=self.approve(identity);run_once(self.store)
        saved=next(r for r in jobs(self.store,'sample-one') if r['id']==queued['id'])
        self.assertEqual(saved['status'],'BLOCKED');self.assertNotEqual(self.access.get('sample-one',identity)['status'],'TESTED')
        self.assertFalse(run_once(self.store));self.assertEqual(len(self.model.calls),1)
