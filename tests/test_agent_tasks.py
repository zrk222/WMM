"""Approval integrity and restart/cancellation behavior, without provider charges."""
import json,tempfile,time,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid,canonical,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.agent_access import AgentAccess
from mission_control.agent_tasks import AgentWork,proposal
from mission_control.worker import jobs,run_once
from mission_control.service import Service
from tests.test_agent_access import body,answer,connection_test_fixture
from tests.test_measurement_connectors import FakeVault


class AgentTaskTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.store=Store(Path(self.folder.name)/'isolated.sqlite3')
        FakeVault.values={}
        vault=patch('mission_control.agent_access.Vault',FakeVault);vault.start();self.addCleanup(vault.stop)
        self.access=AgentAccess(self.store);self.identity=self.access.save('sample-one',body())['connection']

    def approve(self,task='connection_test',focus='',app_id='sample-one'):
        data=dict(task=task,focus=focus,connection_id=self.identity)
        reviewed=proposal(self.store,app_id,data)
        return AgentWork(self.store).start(app_id,{**data,'source_hash':reviewed['source_hash'],'request_key':str(uuid.uuid4())})

    def result(self):return jobs(self.store,'sample-one')[0]

    def test_valid_test_and_draft_use_selected_key_and_preserve_uncertainty(self):
        queued=self.approve()
        with patch('mission_control.agent_tasks.api_run',return_value=(connection_test_fixture(),{'input_tokens':10,'raw_secret':'not saved'})) as run:
            self.assertTrue(run_once(self.store));self.assertEqual(run.call_args.args[1],body()['api_key'])
        self.assertEqual(self.access.get('sample-one',self.identity)['status'],'TESTED')
        request=queued['data']['original_request']
        self.assertEqual(AgentWork(self.store).start('sample-one',request)['id'],queued['id'])
        with self.assertRaises(Invalid):AgentWork(self.store).start('sample-one',{**request,'focus':'Different'})
        self.access.routes('sample-one',dict(version=0,mode='byok',routes={'campaign_plan':self.identity}))
        work=self.approve('campaign_plan','Test a concrete hook')
        with patch('mission_control.agent_tasks.api_run',return_value=(answer(),{'output_tokens':20})):
            run_once(self.store)
        result=self.result()['result'];self.assertEqual(result['draft'],answer())
        self.assertEqual(result['publication'],'NOT_RUN');self.assertEqual(result['cost'],'UNKNOWN')
        self.assertFalse(result['automatically_verified']);self.assertNotIn(body()['api_key'],canonical(jobs(self.store,'sample-one')))
        self.assertNotEqual(work['id'],queued['id'])

    def test_wrong_app_malformed_task_and_unapproved_mode_do_not_run(self):
        for data in (dict(task=[],focus='',connection_id=self.identity),
                     dict(task='connection_test',focus='x'*1001,connection_id=self.identity),
                     dict(task='connection_test',focus='',connection_id={'command':'bad'})):
            with self.subTest(data=data),self.assertRaises(Invalid):proposal(self.store,'sample-one',data)
        with self.assertRaises(Invalid):self.approve(app_id='sample-two')
        with self.assertRaises(Invalid):self.approve('campaign_plan')
        self.assertEqual(jobs(self.store,'sample-one'),[])

    def test_changed_profile_or_app_invalidates_queued_work(self):
        for change in ('profile','app'):
            with self.subTest(change=change):
                queued=self.approve()
                if change=='profile':self.access.save('sample-one',{**body(),'id':self.identity,'version':1})
                else:
                    app=self.store.app('sample-one');self.store.save_app('sample-one',{**app['data'],'job':'Changed'},app['version'])
                with patch('mission_control.agent_tasks.api_run') as run:
                    run_once(self.store);run.assert_not_called()
                self.assertEqual(self.result()['status'],'BLOCKED')

    def test_cancel_before_or_during_request_never_marks_tested(self):
        queued=self.approve();Service(self.store).cancel('sample-one',queued['id'])
        with patch('mission_control.agent_tasks.api_run') as run:
            self.assertFalse(run_once(self.store));run.assert_not_called()
        queued=self.approve()
        def provider(*args):
            Service(self.store).cancel('sample-one',queued['id']);return answer(),{}
        with patch('mission_control.agent_tasks.api_run',side_effect=provider):run_once(self.store)
        self.assertEqual(self.result()['status'],'CANCELLED')
        self.assertEqual(self.access.get('sample-one',self.identity)['status'],'CONFIGURED_UNTESTED')

    def test_expired_lease_does_not_replay_ambiguous_inference_after_restart(self):
        queued=self.approve()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?",(time.time()-1,queued['id']))
        reopened=Store(self.store.path)
        with patch('mission_control.agent_tasks.api_run') as run:
            run_once(reopened);run.assert_not_called()
        self.assertEqual(self.result()['status'],'BLOCKED')
        self.assertIn('consumed allowance',self.result()['result']['error'])

    def test_incomplete_or_secret_output_fails_without_retaining_raw_output(self):
        for response in ({**answer(),'summary':body()['api_key']},{'summary':'incomplete'}):
            with self.subTest(response=response):
                self.approve()
                with patch('mission_control.agent_tasks.api_run',return_value=(response,{})):run_once(self.store)
                self.assertEqual(self.result()['status'],'BLOCKED')
                self.assertNotIn(body()['api_key'],canonical(self.result()))

    def test_corrupt_envelope_is_terminal_and_does_not_change_connection(self):
        queued=self.approve()
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET data=? WHERE id=?',(canonical({'envelope':{},'envelope_hash':'wrong','original_request':{}}),queued['id']))
        with patch('mission_control.agent_tasks.api_run') as run:
            run_once(self.store);run.assert_not_called()
        self.assertEqual(self.result()['status'],'BLOCKED')
        self.assertEqual(self.access.get('sample-one',self.identity)['status'],'CONFIGURED_UNTESTED')


if __name__=='__main__':unittest.main()
