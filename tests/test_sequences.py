"""Durable sequence approval, app isolation, ownership and cancellation."""
from copy import deepcopy
import unittest,uuid
from mission_control.common import Invalid,canonical,now,uid
from mission_control.db import connection
from mission_control.sequence_store import Sequences,decode,feedback
from mission_control.sequence_jobs import link,guard_owned
from mission_control.worker import jobs,json_job
from tests import test_sequence_plan as fixtures


class SequenceStoreTests(unittest.TestCase):
    setUp=fixtures.SequencePlanTests.setUp
    connected=fixtures.SequencePlanTests.connected
    body=fixtures.SequencePlanTests.body

    def approve(self):
        self.connected();service=Sequences(self.store)
        _,proposal=service.proposal('sample-one');body=self.body(proposal)
        return service,body,service.approve('sample-one',body)

    def child(self,service,run,owned=True):
        with connection(self.store.path) as db:
            saved=decode(db.execute('SELECT * FROM campaign_sequences WHERE id=?',(run['id'],)).fetchone())
            data=saved['plan']['steps'][0]['data'];identity=uid()
            db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                (identity,'sample-one','resolution',canonical(data),'QUEUED',now(),now(),identity))
            link(db,'sample-one',run['id'],identity,owned)
            return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())

    def test_approve_replay_and_history_survive_store_restart(self):
        service,body,run=self.approve()
        self.assertEqual(run,service.approve('sample-one',body))
        self.assertEqual(run['state'],'QUEUED');self.assertEqual(run['checkpoint'],0)
        from mission_control.store import Store
        self.assertEqual(Sequences(Store(self.store.path)).history('sample-one'),[run])
        changed={**body,'selected_steps':body['selected_steps'][:1]}
        with self.assertRaises(Invalid):service.approve('sample-one',changed)
        self.assertEqual(service.history('sample-two'),[])

    def test_stale_extra_and_foreign_approval_never_insert_runs(self):
        self.connected();service=Sequences(self.store);_,proposal=service.proposal('sample-one');body=self.body(proposal)
        for invalid in ({**body,'command':'publish'},{**body,'proposal_hash':'stale'},{**body,'request_key':'bad'}):
            with self.assertRaises(Invalid):service.approve('sample-one',invalid)
        with self.assertRaises(Invalid):service.approve('sample-two',body)
        self.assertEqual(service.history('sample-one'),[])

    def test_cancel_stops_only_owned_active_jobs_and_preserves_shared_reads(self):
        service,body,run=self.approve()
        own=self.child(service,run,True);shared=self.child(service,run,False)
        self.assertEqual(guard_owned(self.store,own)['id'],run['id'])
        self.assertIsNone(guard_owned(self.store,shared))
        stopped=service.cancel('sample-one',run['id'],{'confirm_cancel':True})
        self.assertEqual(stopped['state'],'CANCELLED')
        rows={j['id']:j for j in jobs(self.store,'sample-one')}
        self.assertEqual(rows[own['id']]['status'],'CANCELLED')
        self.assertEqual(rows[shared['id']]['status'],'QUEUED')
        self.assertEqual(stopped,service.cancel('sample-one',run['id'],{'confirm_cancel':True}))
        with self.assertRaises(Invalid):guard_owned(self.store,own)

    def test_cancel_is_app_scoped_and_requires_exact_confirmation(self):
        service,_,run=self.approve()
        for app,body in [('sample-two',{'confirm_cancel':True}),('sample-one',{}),('sample-one',{'confirm_cancel':1,'extra':True})]:
            with self.assertRaises(Invalid):service.cancel(app,run['id'],body)
        self.assertEqual(service.history('sample-one')[0]['state'],'QUEUED')

    def test_source_job_link_cannot_race_after_cancellation(self):
        service,_,run=self.approve();job=self.child(service,run)
        service.cancel('sample-one',run['id'],{'confirm_cancel':True})
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):link(db,'sample-one',run['id'],job['id'],True)

    def test_mutated_owned_job_and_plan_hash_fail_before_execution(self):
        service,_,run=self.approve();job=self.child(service,run)
        changed=deepcopy(job);changed['data']['command']='bad'
        with self.assertRaises(Invalid):guard_owned(self.store,changed)
        with connection(self.store.path) as db:db.execute("UPDATE campaign_sequences SET plan_hash='changed' WHERE id=?",(run['id'],))
        with self.assertRaises(Invalid):guard_owned(self.store,job)

    def test_corrupt_history_remains_visible_and_feedback_is_typed(self):
        service,_,run=self.approve()
        with connection(self.store.path) as db:db.execute("UPDATE campaign_sequences SET plan='not-json' WHERE id=?",(run['id'],))
        row=service.history('sample-one')[0]
        self.assertEqual(row['state'],'APPROVAL_REQUIRED');self.assertIn('integrity review',row['summary'])
        current=feedback(self.store,'sample-one')
        self.assertEqual(current['state'],'INVALID');self.assertNotIn('not-json',str(current))


if __name__=='__main__':unittest.main()
