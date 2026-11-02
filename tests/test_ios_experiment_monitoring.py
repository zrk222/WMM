"""Native owner bridge exercises the shared finite experiment scheduler."""
import json
import time
import unittest
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import iso_time
from mission_control.db import connection
from mission_control.ios_host import Runtime
from mission_control.operation_runtime import execute
from tests import test_schedules as fixtures


class NativeExperimentMonitoringTests(unittest.TestCase):
    def setUp(self):
        source=fixtures.ScheduleTests('test_configuration_scope_and_fixed_due');source.setUp();self.addCleanup(source.tearDown)
        self.source=source;self.session=str(uuid4());self.principal=str(uuid4());self.generation=str(uuid4());self.active=True
        with connection(source.store.path) as db:
            db.execute('UPDATE operator_roles SET principal=? WHERE app_id=?',('native:'+self.principal,'sample-one'))
        self.runtime=Runtime(source.store.path,self.verify)

    def verify(self,session):
        if not self.active or session!=self.session:return None
        return dict(principal=self.principal,session_generation=self.generation,expires_at_epoch=time.time()+300)

    def call(self,operation,body,resource=None):
        envelope=dict(app_id='sample-one',operation=operation,input=body)
        if resource is not None:envelope['resource_id']=resource
        return json.loads(self.runtime.owner_call(self.session,json.dumps(envelope).encode()))

    def test_owner_foreground_reservation_and_identity_loss(self):
        experiment=self.source.e['id'];stamp=fixtures.ANALYZE
        body=dict(enabled=True,interval_hours=24,version=None,manifest_version=self.source.store.app('sample-one')['version'],
                  expires_at=(iso_time(stamp)+timedelta(days=7)).isoformat(),max_observations=1)
        with patch('mission_control.experiment_schedules.now',return_value=stamp),patch('mission_control.experiments.now',return_value=stamp):
            saved=self.call('experiment.schedule',body,experiment)
            self.assertEqual(saved['finite_limit']['remaining'],1)
            observed=self.call('experiment.schedule-run',{},experiment)
            self.assertEqual(observed['status'],'SUCCEEDED')
            self.assertEqual(self.call('experiment.schedule-run',{},experiment)['status'],'EXHAUSTED')
            self.assertEqual(len(self.source.experiments.list('sample-one')[0]['assessments']),1)
            self.active=False
            with self.assertRaises(PermissionError):self.call('experiment.schedule',dict(enabled=False,interval_hours=24,version=saved['version']),experiment)
        with connection(self.source.store.path) as db:
            row=db.execute('SELECT reserved,max_observations FROM experiment_schedule_limits').fetchone()
            self.assertEqual(tuple(row),(1,1))

    def test_unbound_or_agent_dispatch_cannot_impersonate_owner(self):
        envelope=dict(app_id='sample-one',operation='experiment.schedule-run',resource_id=self.source.e['id'],input={})
        with self.assertRaises(PermissionError):execute(self.runtime.service,envelope,caller='SCOPED_AGENT')
        with self.assertRaises(PermissionError):execute(self.runtime.service,envelope,caller='LOCAL_SESSION')
