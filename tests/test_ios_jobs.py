"""Shared durable queue and current native owner recovery; not background/device proof."""
import json
import unittest
from unittest.mock import patch
from tests import test_ios_host as fixture
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_jobs import NativeJobs


class NativeJobTests(unittest.TestCase):
    setUp = fixture.NativeRuntimeTests.setUp
    verify = fixture.NativeRuntimeTests.verify
    creation = fixture.NativeRuntimeTests.creation

    def setup_jobs(self):
        self.runtime.create_workspace(self.session,self.creation())
        self.stamp = 10000
        self.jobs = NativeJobs(self.runtime.service,self.runtime.identities,lambda:self.stamp)

    def call(self, action, body=None, app='new-app'):
        return json.loads(self.jobs.call(self.session,app,action,json.dumps(body or {}).encode()))

    def queue(self, key='native-preparation'):
        return self.call('queue',dict(stage=0,request_key=key))

    def test_real_twelve_stage_preparation_durable_progress_and_idempotent_result(self):
        self.setup_jobs()
        queued = self.queue()
        self.assertEqual(self.queue()['id'],queued['id'])
        result = self.call('run',dict(id=queued['id']))
        self.assertEqual(result['status'],'SUCCEEDED')
        self.assertEqual(result['attempts'],1)
        self.assertEqual(self.call('run',dict(id=queued['id'])),result)
        monitor = self.call('monitor')
        self.assertEqual(monitor['runs'][0]['processed_stages'],12)
        self.assertGreater(monitor['runs'][0]['blocked_stages'],0)
        self.assertEqual(monitor['runs'][0]['latest']['code'],'SUCCEEDED')
        reopened = NativeJobs(self.runtime.service,self.runtime.identities,lambda:self.stamp)
        self.assertEqual(json.loads(reopened.call(self.session,'new-app','run',json.dumps(dict(id=queued['id'])).encode())),result)

    def test_live_lease_does_not_restart_and_expired_lease_recovers_once(self):
        self.setup_jobs();queued=self.queue()
        with connection(self.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?",(self.stamp+60,queued['id']))
        with self.assertRaises(Invalid):self.call('run',dict(id=queued['id']))
        self.stamp += 61
        recovered=self.call('run',dict(id=queued['id']))
        self.assertEqual(recovered['status'],'SUCCEEDED')
        self.assertEqual(recovered['attempts'],2)

    def test_attempt_ceiling_and_cancelled_result_never_replay(self):
        self.setup_jobs();queued=self.queue()
        with connection(self.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=3,lease=0 WHERE id=?",(queued['id'],))
        self.assertEqual(self.call('run',dict(id=queued['id']))['status'],'FAILED')
        another=self.queue('cancel-this')
        cancelled=self.call('cancel',dict(id=another['id']))
        self.assertEqual(cancelled['status'],'CANCELLED')
        self.assertEqual(self.call('run',dict(id=another['id'])),cancelled)

    def test_current_owner_app_scope_and_no_provider_job_execution(self):
        self.setup_jobs();queued=self.queue()
        with self.assertRaises(PermissionError):self.call('run',dict(id=queued['id']),app='other')
        with connection(self.path) as db:
            db.execute("UPDATE jobs SET action='sync' WHERE id=?",(queued['id'],))
        with self.assertRaises(PermissionError):self.call('run',dict(id=queued['id']))
        self.available=False
        with self.assertRaises(PermissionError):self.call('monitor')

    def test_lock_during_progress_preserves_lease_then_recovers_with_current_identity(self):
        from mission_control import workflow_telemetry
        self.setup_jobs();queued=self.queue()
        original=workflow_telemetry.emit
        def lock_then_emit(*args,**kwargs):
            self.available=False
            return original(*args,**kwargs)
        with patch.object(workflow_telemetry,'emit',lock_then_emit):
            with self.assertRaises(PermissionError):self.call('run',dict(id=queued['id']))
        with connection(self.path) as db:
            row=db.execute('SELECT status,result FROM jobs WHERE id=?',(queued['id'],)).fetchone()
            self.assertEqual(row['status'],'RUNNING');self.assertIsNone(row['result'])
        self.available=True;self.stamp+=61
        self.assertEqual(self.call('run',dict(id=queued['id']))['status'],'SUCCEEDED')

    def test_mutated_manifest_and_invalid_controls_deny(self):
        self.setup_jobs();queued=self.queue()
        for body in (dict(stage=True,request_key='bad'),dict(stage=13,request_key='bad')):
            with self.assertRaises(Invalid):self.call('queue',body)
        with self.assertRaises(Invalid):self.call('shell')
        with self.assertRaises(Invalid):self.call('run',dict(id=queued['id'],role='OWNER'))
        with connection(self.path) as db:db.execute("UPDATE apps SET version=version+1 WHERE id='new-app'")
        with self.assertRaises(Invalid):self.call('run',dict(id=queued['id']))


if __name__ == '__main__':unittest.main()
