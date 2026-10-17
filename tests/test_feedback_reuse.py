"""Exact approved observation reuse is local, fresh, app-owned and hash-bound."""
import json,tempfile,unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from mission_control.store import Store,decode
from mission_control.resolutions import Resolutions
from mission_control.agent_feedback import reuse_candidate
from mission_control.common import canonical,digest,now,iso_time,Invalid
from mission_control.db import connection
from mission_control.worker import run_once,jobs
from tests.test_agent_feedback import initialize,inspect,request


class ReuseTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(Path(tmp.name)/'reuse.sqlite3');initialize(self.store)

    def test_reuse_observation_zero_network_and_same_artifact(self):
        original=inspect(self.store)
        job=Resolutions(self.store).start('sample-one',request(self.store,'reuse_observation'))
        with patch('mission_control.aeo_workflows.PublicReader',side_effect=AssertionError('No network permitted')):self.assertTrue(run_once(self.store))
        saved=next(j for j in jobs(self.store,'sample-one') if j['id']==job['id'])
        self.assertEqual(saved['status'],'SUCCEEDED')
        self.assertEqual(saved['result']['artifacts'],original['result']['artifacts'])
        self.assertEqual(saved['result']['proof_status'],'PARTIAL')
        self.assertEqual(reuse_candidate(self.store,self.store.app('sample-one'))['source_job_id'],job['id'])

    def test_new_failed_read_supersedes_queued_reuse(self):
        inspect(self.store);queued=Resolutions(self.store).start('sample-one',request(self.store,'reuse_observation'))
        with connection(self.store.path) as db:
            # Keep the owned reuse queued while a newer read fails independently.
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=?",(queued['id'],))
        inspect(self.store,fail=True)
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET status='QUEUED' WHERE id=?",(queued['id'],))
        self.assertTrue(run_once(self.store))
        saved=next(j for j in jobs(self.store,'sample-one') if j['id']==queued['id'])
        self.assertEqual(saved['status'],'BLOCKED')

    def test_public_artifact_corruption_and_foreign_reference_cannot_reuse(self):
        original=inspect(self.store);queued=Resolutions(self.store).start('sample-one',request(self.store,'reuse_observation'))
        ref=original['result']['artifacts'][0]
        with connection(self.store.path) as db:db.execute("UPDATE aeo_checks SET hash='changed' WHERE id=?",(ref['id'],))
        with patch('mission_control.aeo_workflows.PublicReader',side_effect=AssertionError('No fallback read')):run_once(self.store)
        self.assertEqual(next(j for j in jobs(self.store,'sample-one') if j['id']==queued['id'])['status'],'BLOCKED')

    def test_expired_native_artifact_rehashed_consistently_is_still_not_reusable(self):
        original=inspect(self.store);ref=original['result']['artifacts'][0]
        stamp=(iso_time(now())-timedelta(days=2)).isoformat()
        with connection(self.store.path) as db:
            row=decode(db.execute('SELECT * FROM aeo_checks WHERE id=?',(ref['id'],)).fetchone())
            row['data']['started_at']=stamp;row['data']['observed_at']=stamp;sha=digest(row['data'])
            db.execute('UPDATE aeo_checks SET data=?,hash=?,created=? WHERE id=?',(canonical(row['data']),sha,stamp,ref['id']))
            original['result']['artifacts'][0]['sha256']=sha
            db.execute('UPDATE jobs SET result=? WHERE id=?',(canonical(original['result']),original['id']))
        self.assertIsNone(reuse_candidate(self.store,self.store.app('sample-one')))


if __name__=='__main__':unittest.main()
