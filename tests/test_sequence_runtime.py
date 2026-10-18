"""Persistent worker progression, ownership races and revocable source reads."""
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import patch
from mission_control.common import Invalid,canonical,digest,now,iso_time
from mission_control.db import connection
from mission_control.store import Store
from mission_control.sequence_store import Sequences,decode
from mission_control.sequence_runtime import advance
from mission_control.worker import run_once,jobs
from mission_control.campaign_inputs import CampaignInputs
from tests import test_sequence_plan as fixtures
from tests.test_aeo_workflows import CountingReader,ROOT


class SequenceRuntimeTests(unittest.TestCase):
    setUp=fixtures.SequencePlanTests.setUp
    connected=fixtures.SequencePlanTests.connected
    body=fixtures.SequencePlanTests.body

    def approve(self,tool=None):
        self.connected();app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'website':ROOT+'/page'},app['version'])
        service=Sequences(self.store);_,proposal=service.proposal('sample-one');body=self.body(proposal)
        if tool:body['selected_steps']=[s['id'] for s in proposal['steps'] if s['tool']==tool]
        return service,service.approve('sample-one',body)

    def pump(self,store=None):
        store=store or self.store
        for _ in range(20):
            if not run_once(store):return
        self.fail('The finite fixture sequence did not settle')

    def test_worker_advances_independent_steps_and_resumes_saved_checkpoint(self):
        service,run=self.approve()
        with patch('mission_control.worker.sync',return_value={'fixture':True}) as sync, \
             patch('mission_control.worker.read_report',return_value={'fixture':True}) as report, \
             patch('mission_control.aeo_workflows.PublicReader',CountingReader):
            self.assertTrue(run_once(self.store))
            reopened=Store(self.store.path);self.pump(reopened)
        row=Sequences(reopened).history('sample-one')[0]
        self.assertEqual(row['state'],'EVIDENCE_REVIEW_REQUIRED')
        self.assertEqual(row['checkpoint'],2)
        self.assertEqual(len(row['step_outcomes']),2)
        self.assertEqual(sync.call_count+report.call_count,3)
        self.assertEqual(len({o['job_id'] for o in row['step_outcomes']}),2)
        self.assertTrue(all(o['state']=='EVIDENCE_GATHERED' for o in row['step_outcomes']))
        self.assertFalse(row['automatically_verified'])

    def test_owned_queued_sources_cancel_without_provider_calls(self):
        service,run=self.approve('collect_sources')
        self.assertTrue(run_once(self.store))
        service.cancel('sample-one',run['id'],{'confirm_cancel':True})
        with patch('mission_control.worker.sync',side_effect=AssertionError('Cancelled')) as a, \
             patch('mission_control.worker.read_report',side_effect=AssertionError('Cancelled')) as b:
            self.assertFalse(run_once(self.store));a.assert_not_called();b.assert_not_called()
        sources=[j for j in jobs(self.store,'sample-one') if j['action']=='sync']
        self.assertEqual(len(sources),3);self.assertTrue(all(j['status']=='CANCELLED' for j in sources))

    def test_preexisting_shared_reads_survive_sequence_cancellation(self):
        service,run=self.approve('collect_sources')
        collector=CampaignInputs(self.store);plan=collector.preview('sample-one')
        reads=collector.start('sample-one',{k:plan[k] for k in ('manifest_version','source_hash')})
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET created='9999' WHERE action='sync'")
        self.assertTrue(run_once(self.store))
        with connection(self.store.path) as db:
            shared=db.execute("SELECT count(*) FROM sequence_jobs l JOIN jobs j ON l.job_id=j.id WHERE l.run_id=? AND j.action='sync' AND l.owned=0",(run['id'],)).fetchone()[0]
        self.assertEqual(shared,3)
        service.cancel('sample-one',run['id'],{'confirm_cancel':True})
        self.assertTrue(all(j['status']=='QUEUED' for j in jobs(self.store,'sample-one') if j['action']=='sync'))
        with patch('mission_control.worker.sync',return_value={}) as a,patch('mission_control.worker.read_report',return_value={}) as b:self.pump()
        self.assertEqual(a.call_count+b.call_count,3)

    def test_inflight_cancellation_rejects_result_and_stops_next_reads(self):
        service,run=self.approve('collect_sources');self.assertTrue(run_once(self.store))
        def read(*args):
            service.cancel('sample-one',run['id'],{'confirm_cancel':True});return {'must_not_be_adopted':True}
        with patch('mission_control.worker.sync',side_effect=read) as a,patch('mission_control.worker.read_report',side_effect=read) as b:
            self.assertTrue(run_once(self.store));self.assertFalse(run_once(self.store))
        self.assertEqual(a.call_count+b.call_count,1)
        row=service.history('sample-one')[0]
        self.assertEqual(row['state'],'CANCELLED');self.assertEqual(row['checkpoint'],0)
        self.assertEqual(row['step_outcomes'],[])
        self.assertTrue(all(j['result'] is None for j in jobs(self.store,'sample-one') if j['action']=='sync'))

    def test_expiry_stops_owned_reads_before_io_and_explains_new_approval(self):
        service,run=self.approve('collect_sources');self.assertTrue(run_once(self.store))
        with connection(self.store.path) as db:
            saved=decode(db.execute('SELECT * FROM campaign_sequences WHERE id=?',(run['id'],)).fetchone())
            plan=saved['plan'];plan['expires_at']=(iso_time(now())-timedelta(seconds=1)).isoformat()
            db.execute('UPDATE campaign_sequences SET plan=?,plan_hash=? WHERE id=?',(canonical(plan),digest(plan),run['id']))
        with patch('mission_control.worker.sync',side_effect=AssertionError('Expired')) as a, \
             patch('mission_control.worker.read_report',side_effect=AssertionError('Expired')) as b:self.pump();a.assert_not_called();b.assert_not_called()
        row=service.history('sample-one')[0]
        self.assertEqual(row['state'],'APPROVAL_REQUIRED');self.assertIn('expired',' '.join(row['next_actions']))

    def test_one_failed_action_retained_while_other_approved_work_continues(self):
        service,run=self.approve()
        with patch('mission_control.aeo_workflows.Checks.run',side_effect=Invalid('synthetic failure')), \
             patch('mission_control.worker.sync',return_value={}) as a,patch('mission_control.worker.read_report',return_value={}) as b:self.pump()
        row=service.history('sample-one')[0]
        self.assertEqual(row['state'],'EVIDENCE_REVIEW_REQUIRED')
        self.assertEqual({o['state'] for o in row['step_outcomes']},{'NEEDS_RESOLUTION','EVIDENCE_GATHERED'})
        self.assertEqual(a.call_count+b.call_count,3)
        self.assertNotIn('synthetic failure',str(row))

    def test_app_drift_blocks_before_any_child_is_queued(self):
        service,run=self.approve();app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'release':'changed'},app['version'])
        self.assertTrue(advance(self.store));self.assertEqual(jobs(self.store,'sample-one'),[])
        self.assertEqual(service.history('sample-one')[0]['state'],'APPROVAL_REQUIRED')

    def test_saved_child_identity_recovery_does_not_duplicate_execution(self):
        from mission_control.sequence_runtime import enqueue_child
        service,run=self.approve('collect_sources')
        with connection(self.store.path) as db:
            saved=decode(db.execute('SELECT * FROM campaign_sequences WHERE id=?',(run['id'],)).fetchone())
            first=enqueue_child(db,saved,saved['plan']['steps'][0]);second=enqueue_child(db,saved,saved['plan']['steps'][0])
        self.assertEqual(first,second);self.assertEqual(len(jobs(self.store,'sample-one')),1)

    def test_missing_child_receipt_is_a_gap_not_success(self):
        service,run=self.approve('collect_sources');self.assertTrue(advance(self.store))
        with connection(self.store.path) as db:
            saved=decode(db.execute('SELECT * FROM campaign_sequences WHERE id=?',(run['id'],)).fetchone())
            db.execute('PRAGMA foreign_keys=OFF')
            db.execute('DELETE FROM jobs WHERE id=?',(saved['result']['active_job_id'],))
        self.assertTrue(advance(self.store))
        row=service.history('sample-one')[0]
        self.assertEqual(row['state'],'EVIDENCE_REVIEW_REQUIRED')
        self.assertEqual(row['step_outcomes'][0]['state'],'NEEDS_RESOLUTION')
        self.assertFalse(row['automatically_verified'])

    def test_concurrent_advance_creates_only_one_owned_child(self):
        from concurrent.futures import ThreadPoolExecutor
        service,run=self.approve('collect_sources')
        with ThreadPoolExecutor(max_workers=2) as pool:
            result=list(pool.map(lambda _:advance(self.store),range(2)))
        self.assertEqual(sum(result),1)
        self.assertEqual(len(jobs(self.store,'sample-one')),1)


if __name__=='__main__':unittest.main()
