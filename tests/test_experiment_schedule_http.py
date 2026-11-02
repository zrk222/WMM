"""Owner-only finite experiment schedule through the real loopback server."""
from datetime import timedelta
from contextlib import closing
import sqlite3
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from mission_control.common import now,iso_time
from mission_control.db import connection
from mission_control.operator_client import ClientError,OperatorClient
from mission_control.server import Server
from tests import test_schedules as schedule_fixture


class ExperimentScheduleHTTPTests(unittest.TestCase):
    def setUp(self):
        fixture=schedule_fixture.ScheduleTests('test_configuration_scope_and_fixed_due');fixture.setUp()
        self.addCleanup(fixture.tearDown)
        self.store,self.owner,self.e,self.schedules=fixture.store,fixture.owner,fixture.e,fixture.schedules
        identity=patch('mission_control.operator_identity.github_read',return_value={**self.owner,'provider':'GITHUB','verified_at':now()})
        identity.start();self.addCleanup(identity.stop)
        self.server=Server(('127.0.0.1',0),self.store)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def stop():self.server.shutdown();self.server.server_close();thread.join(timeout=10)
        self.addCleanup(stop)
        self.client=OperatorClient('http://127.0.0.1:'+str(self.server.server_port));self.client.bootstrap()
        self.client.request('POST','/api/identity/login',{'token':'synthetic_owner_identity_token'})
        self.path='/api/apps/sample-one/experiments/'+self.e['id']+'/schedule'

    def body(self):
        return dict(enabled=True,interval_hours=24,version=None,manifest_version=self.store.app('sample-one')['version'],expires_at=(iso_time(now())+timedelta(days=7)).isoformat(),max_observations=2)

    def test_fresh_owner_only_and_current_manifest(self):
        anonymous=OperatorClient(self.client.origin);anonymous.bootstrap()
        with self.assertRaises(ClientError) as denied:anonymous.request('POST',self.path,self.body())
        self.assertEqual(denied.exception.status,403)
        with self.assertRaises(ClientError) as denied:self.client.request('POST',self.path,dict(self.body(),manifest_version=999))
        self.assertEqual(denied.exception.status,400)
        with self.assertRaises(ClientError) as denied:self.client.request('POST',self.path+'?query=1',self.body())
        self.assertEqual(denied.exception.status,400)
        saved=self.client.request('POST',self.path,self.body())
        self.assertEqual(saved['finite_limit']['remaining'],2)
        paused=self.client.request('POST',self.path,dict(enabled=False,interval_hours=24,version=saved['version']))
        self.assertFalse(paused['enabled'])

    def test_csrf_and_role_revocation_before_commit_leave_no_schedule(self):
        request=Request(self.client.origin+self.path,data=b'{}',method='POST',headers={'Origin':self.client.origin,'Content-Type':'application/json','X-CSRF-Token':'wrong'})
        with self.assertRaises(HTTPError) as denied:self.client.opener.open(request,timeout=10)
        self.assertEqual(denied.exception.code,403);denied.exception.close()
        original=type(self.schedules).save
        def revoke(service,*args,**kwargs):
            with closing(sqlite3.connect(str(self.store.path))) as db:
                with db:db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",('sample-one',))
            return original(service,*args,**kwargs)
        with patch('mission_control.experiment_schedules.Schedules.save',revoke):
            with self.assertRaises(ClientError) as denied:self.client.request('POST',self.path,self.body())
        self.assertIn(denied.exception.status,(400,403))
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM experiment_schedules').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM experiment_schedule_limits').fetchone()[0],0)
