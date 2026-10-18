"""Exact approved retry, durable readback, bounds and immutable failure receipts."""
from copy import deepcopy
import unittest, uuid
from unittest.mock import patch
from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.service import Service
from mission_control.campaign_inputs import CampaignInputs
from mission_control.resolutions import Resolutions
from mission_control.worker import run_once, jobs
from mission_control.resolution_tools import execute
from tests import test_source_progress as fixtures


class SourceRetryTests(unittest.TestCase):
    setUp=fixtures.SourceProgressTests.setUp
    request=fixtures.SourceProgressTests.request
    dispatch=fixtures.SourceProgressTests.dispatch

    def failed(self):
        _,ids=self.dispatch()
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='SUCCEEDED',result='{}' WHERE id IN (?,?,?)",ids)
            db.execute("UPDATE jobs SET status='BLOCKED',result=? WHERE id=?",(canonical({'error':'SYNTHETIC_PRIVATE_DIAGNOSTIC'}),ids[0]))
        return ids

    def parameters(self):
        plan=CampaignInputs(self.store).preview('sample-one')
        return dict(collection_hash=plan['source_hash'],retry_candidates=plan['retry_candidates'])

    def approval(self):
        plan=Resolutions(self.store).proposal('sample-one')[1]
        issue=next(i for i in plan['issues'] if any(o['ready'] and 'retry_candidates' in o['parameters'] for o in i['options']))
        option=next(o for o in issue['options'] if o['ready'] and 'retry_candidates' in o['parameters'])
        return dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],
                    target_url=None,request_key=str(uuid.uuid4()))

    def test_retry_runs_only_failed_read_preserves_original_and_reloads_latest(self):
        ids=self.failed();before=next(j for j in jobs(self.store,'sample-one') if j['id']==ids[0])
        parent=Resolutions(self.store).start('sample-one',self.approval())
        self.assertTrue(run_once(self.store))
        result=Resolutions(self.store).history('sample-one')[0]
        self.assertEqual(result['status'],'COLLECTING_SOURCES')
        self.assertEqual(len(result['children']),1)
        with patch('mission_control.worker.sync',return_value={'fixture':True}) as a, \
             patch('mission_control.worker.read_report',return_value={'fixture':True}) as b:
            self.assertTrue(run_once(self.store));self.assertEqual(a.call_count+b.call_count,1)
        reloaded=Store(self.store.path);plan=CampaignInputs(reloaded).preview('sample-one')
        self.assertEqual(plan['retry_candidates'],[])
        retried=next(t for t in plan['tasks'] if t['retry_history'])
        self.assertEqual(retried['job']['status'],'SUCCEEDED')
        self.assertEqual(len(retried['retry_history']),1)
        self.assertEqual(retried['retry_request_key'],retried['job']['request_key'])
        self.assertEqual(before,next(j for j in jobs(reloaded,'sample-one') if j['id']==ids[0]))
        latest=next(h for h in Resolutions(reloaded).history('sample-one') if h['job_id']==parent['id'])
        self.assertEqual(latest['status'],'EVIDENCE_GATHERED');self.assertFalse(latest['automatically_verified'])

    def test_exact_replay_keeps_ids_attempts_and_blocks_changed_input(self):
        self.failed();parameters=self.parameters();key=str(uuid.uuid4())
        service=CampaignInputs(self.store);first=service.retry('sample-one',parameters,key)
        self.assertEqual(first,service.retry('sample-one',parameters,key))
        self.assertEqual(first['tasks'][0]['job']['attempts'],0)
        altered=deepcopy(parameters);altered['retry_candidates'][0]['job_hash']='a'*64
        with self.assertRaises(Invalid):service.retry('sample-one',altered,key)
        self.assertEqual(len(jobs(self.store,'sample-one')),5)

    def test_latest_changed_source_or_other_app_rejects_before_insert(self):
        ids=self.failed();parameters=self.parameters();key=str(uuid.uuid4())
        with self.assertRaises(Invalid):CampaignInputs(self.store).retry('sample-two',parameters,key)
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET result='{}' WHERE id=?",(ids[0],))
        with self.assertRaises(Invalid):CampaignInputs(self.store).retry('sample-one',parameters,key)
        self.assertEqual(len(jobs(self.store,'sample-one')),4)

    def test_pending_successful_and_unknown_reads_are_not_retry_candidates(self):
        ids=self.failed()
        for status in ('QUEUED','RUNNING','SUCCEEDED','UNKNOWN'):
            with self.subTest(status=status),connection(self.store.path) as db:
                db.execute('UPDATE jobs SET status=? WHERE id=?',(status,ids[0]))
            self.assertEqual(self.parameters()['retry_candidates'],[])

    def test_cancelled_failed_and_blocked_require_new_explicit_approval(self):
        ids=self.failed()
        for status in ('CANCELLED','FAILED','BLOCKED'):
            with self.subTest(status=status),connection(self.store.path) as db:
                db.execute('UPDATE jobs SET status=? WHERE id=?',(status,ids[0]))
            params=self.parameters();self.assertEqual(len(params['retry_candidates']),1)
            self.assertEqual(len(jobs(self.store,'sample-one')),4)
            self.assertNotIn('SYNTHETIC_PRIVATE_DIAGNOSTIC',canonical(params))

    def test_three_manual_retries_then_current_window_explanation(self):
        self.failed();service=CampaignInputs(self.store)
        for count in range(3):
            saved=service.retry('sample-one',self.parameters(),str(uuid.uuid4()))
            target=saved['tasks'][0]['job']['id']
            with connection(self.store.path) as db:db.execute("UPDATE jobs SET status='BLOCKED' WHERE id=?",(target,))
            task=next(t for t in service.preview('sample-one')['tasks'] if t['retry_history'])
            self.assertEqual(len(task['retry_history']),count+1)
        plan=service.preview('sample-one');self.assertEqual(plan['retry_candidates'],[])
        issue=Resolutions(self.store).proposal('sample-one')[1]['issues'][0]
        option=next(o for o in issue['options'] if 'retry_candidates' in o['parameters'])
        self.assertFalse(option['ready']);self.assertIn(plan['next_collection_at'],option['fallback'])
        self.assertIn('source access',option['fallback'])

    def test_worker_recovery_after_dispatch_replays_child_without_new_read(self):
        self.failed();job=Resolutions(self.store).start('sample-one',self.approval())
        first=execute(self.store,'sample-one',job['data']);second=execute(self.store,'sample-one',job['data'])
        self.assertEqual(first['children'],second['children'])
        self.assertEqual(len(jobs(self.store,'sample-one')),6)
        self.assertFalse(first['external_writes']);self.assertEqual(first['spend_minor'],0)

    def test_rotated_connection_and_new_collection_hour_reject_old_retry(self):
        self.failed();params=self.parameters();service=CampaignInputs(self.store)
        with patch('mission_control.campaign_inputs.datetime') as clock:
            clock.now.return_value.strftime.return_value='2099-01-01T12'
            from datetime import datetime
            clock.fromisoformat.side_effect=datetime.fromisoformat
            with self.assertRaises(Invalid):service.retry('sample-one',params,str(uuid.uuid4()))
        record=next(r for r in self.store.records('sample-one') if r['kind']=='connection')
        with connection(self.store.path) as db:db.execute('UPDATE records SET version=version+1 WHERE id=?',(record['id'],))
        with self.assertRaises(Invalid):service.retry('sample-one',params,str(uuid.uuid4()))

    def test_direct_commands_empty_selection_and_invalid_request_never_queue(self):
        self.failed();service=CampaignInputs(self.store);params=self.parameters()
        for body in ({**params,'command':'publish'},dict(collection_hash=params['collection_hash'],retry_candidates=[])):
            with self.assertRaises(Invalid):service.retry('sample-one',body,str(uuid.uuid4()))
        for key in (None,'not-a-request'):
            with self.assertRaises(Invalid):service.retry('sample-one',params,key)
        self.assertEqual(len(jobs(self.store,'sample-one')),4)


if __name__=='__main__':unittest.main()
