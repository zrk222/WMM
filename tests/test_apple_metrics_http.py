"""Synthetic owner-only analytics tests; no live credentials or provider calls."""
from contextlib import closing, contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mission_control import apple_metrics_http as api
from mission_control.apple_metrics_schedule import AppleMetricsSchedules
from mission_control.common import Invalid, canonical, now
from mission_control.db import connection
from mission_control.operation_authority import bound_owner, protected
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once

APP = 'sample-one'
REPORT = 'report-1'


class Identities:
    available = True

    def fresh(self, session):
        if not self.available or session != 'session':
            raise PermissionError('identity unavailable')
        return {'principal': 'owner'}

    def local(self, session, principal, generation=None):
        if not self.available or session != 'session' or principal != 'owner' or generation not in (None, 'generation'):
            raise PermissionError('identity unavailable')
        return {'session_generation': 'generation'}


class Headers:
    def __init__(self):
        self.values = {'Host': ['127.0.0.1:8765'], 'Origin': ['http://127.0.0.1:8765'],
                       'X-CSRF-Token': ['session']}

    def get_all(self, name):
        return self.values.get(name)


class AppleMetricsHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'state.sqlite')
        self.service = Service(self.store)
        app = self.store.app(APP)
        self.app = self.store.save_app(APP, dict(app['data'], store_app_id='123'), app['version'])
        self.record = self.service.evidence(APP, dict(kind='connection', title='Apple', source='fixture',
            data={'provider': 'app_store', 'store_app_id': '123', 'env_ref': 'GROWTH_SAMPLE_ONE_SYNTHETIC', 'account_id': '0'}))
        with connection(self.store.path) as db:
            db.execute('INSERT INTO operator_roles VALUES(?,?,?,?,?,?,?,?)',
                       (APP, 'owner', 'owner', 'OWNER', 'ACTIVE', 1, now(), 'fixture'))
        self.identities = Identities()

    def saved_inventory(self, job_id='job-1', **changes):
        data = dict(connection_id=self.record['id'], connection_version=self.record['version'],
                    connection_hash=self.record['hash'], manifest_version=self.app['version'],
                    options={'operation': 'analytics_reports'})
        data.update(changes)
        result = dict(provider='app_store', operation='analytics_reports', app_id=APP, store_app_id='123',
                      status='WAITING_FOR_REPORTS', coverage='COMPLETE', observed_at=now(),
                      reports=[dict(id=REPORT, name='App Downloads Standard', coverage='COMPLETE', instances=[])],
                      sensitive='synthetic-private-https://example.invalid')
        with connection(self.store.path) as db:
            db.execute('INSERT INTO jobs(id,app_id,action,data,status,result,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?,?)',
                       (job_id, APP, 'sync', canonical(data), 'SUCCEEDED', canonical(result), now(), now(), job_id))

    @contextmanager
    def owner(self):
        envelope = dict(app_id=APP, operation='apple.analytics.owner.fixture', input={})
        with bound_owner(self.store, envelope, self.identities, 'session', {'principal': 'owner'}), protected(self.store, envelope):
            yield

    def dispatch(self, action, body):
        with self.owner():
            return api.dispatch(self.service, APP, action, body)

    def inventory_body(self):
        return dict(manifest_version=self.app['version'], connection_id=self.record['id'],
                    connection_version=self.record['version'])

    def schedule_body(self):
        return dict(manifest_version=self.app['version'], enabled=True, interval_hours=24,
                    report_id=REPORT, version=None)

    def mutate(self, sql, values=()):
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute(sql, values)

    def count(self, table):
        with connection(self.store.path) as db:
            return db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]

    def test_view_only_returns_current_metadata_and_unknown_metrics(self):
        self.saved_inventory()
        value = self.dispatch('view', {})
        self.assertEqual(value['inventory']['status'], 'WAITING_FOR_REPORTS')
        self.assertEqual(value['reports'], [dict(id=REPORT, name='App Downloads Standard',
                                                 instance_count=0, coverage='COMPLETE')])
        self.assertNotIn('synthetic-private', json.dumps(value))
        self.assertNotIn('GROWTH_SAMPLE_ONE_SYNTHETIC', json.dumps(value))
        self.assertNotIn('metrics', value)
        self.assertEqual(value['connection']['status'], 'CONFIGURED_UNVERIFIED')

    def test_inventory_is_selected_only_for_current_app_and_connection(self):
        self.saved_inventory(manifest_version=self.app['version'] - 1)
        value = self.dispatch('view', {})
        self.assertIsNone(value['inventory'])
        self.assertEqual(value['reports'], [])
        with self.assertRaises(Invalid):
            self.dispatch('schedule', self.schedule_body())
        self.assertEqual(self.count('apple_metrics_schedules'), 0)

    def test_queue_schedule_pause_and_strict_fields(self):
        queued = self.dispatch('inventory', self.inventory_body())
        self.assertEqual(queued['status'], 'QUEUED')
        self.saved_inventory()
        scheduled = self.dispatch('schedule', self.schedule_body())
        self.assertTrue(scheduled['enabled'])
        paused = self.dispatch('schedule', dict(manifest_version=self.app['version'], enabled=False,
                                                version=scheduled['version']))
        self.assertFalse(paused['enabled'])
        for action, body in [('view', {'actor': 'owner'}), ('inventory', dict(self.inventory_body(), token='bad')),
                             ('schedule', dict(self.schedule_body(), report_id='foreign'))]:
            with self.subTest(action=action), self.assertRaises(Invalid):
                self.dispatch(action, body)

    def test_queued_inventory_worker_and_view_share_exact_source_binding(self):
        queued = self.dispatch('inventory', self.inventory_body())
        result = dict(provider='app_store', operation='analytics_reports', app_id=APP, store_app_id='123',
                      status='WAITING_FOR_REPORTS', coverage='COMPLETE', observed_at=now(),
                      reports=[dict(id=REPORT, name='App Downloads Standard', coverage='COMPLETE', instances=[])])
        with patch('mission_control.worker.read_report', return_value=result) as reader:
            self.assertTrue(run_once(self.store))
        reader.assert_called_once()
        value = self.dispatch('view', {})
        self.assertEqual(value['inventory']['job_id'], queued['job_id'])
        self.assertEqual(value['reports'][0]['instance_count'], 0)

    def test_queue_rechecks_manifest_in_actual_write_transaction(self):
        original = self.service.queue
        def changed(app, body, **kwargs):
            self.mutate('UPDATE apps SET version=version+1 WHERE id=?', (APP,))
            return original(app, body, **kwargs)
        with patch.object(self.service, 'queue', side_effect=changed), self.assertRaises(Invalid):
            self.dispatch('inventory', self.inventory_body())
        self.assertEqual(self.count('jobs'), 0)

    def test_schedule_rechecks_inventory_in_actual_write_transaction(self):
        self.saved_inventory()
        original = AppleMetricsSchedules.save
        def changed(service, app, body, **kwargs):
            self.mutate("UPDATE jobs SET status='FAILED' WHERE id='job-1'")
            return original(service, app, body, **kwargs)
        with patch.object(AppleMetricsSchedules, 'save', changed), self.assertRaises(Invalid):
            self.dispatch('schedule', self.schedule_body())
        self.assertEqual(self.count('apple_metrics_schedules'), 0)

    def test_schedule_rechecks_connection_and_owner_after_precheck(self):
        self.saved_inventory()
        original = AppleMetricsSchedules.save
        def rotate(service, app, body, **kwargs):
            self.mutate('UPDATE records SET version=version+1 WHERE app_id=? AND id=?',
                        (APP, self.record['id']))
            return original(service, app, body, **kwargs)
        with patch.object(AppleMetricsSchedules, 'save', rotate), self.assertRaises(Invalid):
            self.dispatch('schedule', self.schedule_body())
        self.assertEqual(self.count('apple_metrics_schedules'), 0)

    def test_schedule_rechecks_owner_role_after_precheck(self):
        self.saved_inventory()
        original = AppleMetricsSchedules.save
        def revoke(service, app, body, **kwargs):
            self.mutate("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", (APP,))
            return original(service, app, body, **kwargs)
        with patch.object(AppleMetricsSchedules, 'save', revoke), self.assertRaises(PermissionError):
            self.dispatch('schedule', self.schedule_body())
        self.assertEqual(self.count('apple_metrics_schedules'), 0)

    def test_revoked_owner_cannot_commit_queue_after_precheck(self):
        original = self.service.queue
        def revoked(app, body, **kwargs):
            self.mutate("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?", (APP,))
            return original(app, body, **kwargs)
        with patch.object(self.service, 'queue', side_effect=revoked), self.assertRaises(PermissionError):
            self.dispatch('inventory', self.inventory_body())
        self.assertEqual(self.count('jobs'), 0)

    def test_identity_loss_cannot_commit_queue_after_precheck(self):
        original = self.service.queue
        def lost(app, body, **kwargs):
            self.identities.available = False
            return original(app, body, **kwargs)
        with patch.object(self.service, 'queue', side_effect=lost), self.assertRaises(PermissionError):
            self.dispatch('inventory', self.inventory_body())
        self.assertEqual(self.count('jobs'), 0)

    def test_trusted_callbacks_run_inside_write_transaction_and_roll_back(self):
        observed = []
        def deny(db):
            observed.append(db.in_transaction)
            raise Invalid('synthetic transaction denial')
        with self.assertRaisesRegex(Invalid, 'transaction denial'):
            self.service.queue(APP, dict(action='sync', data=dict(connection_id=self.record['id'],
                connection_version=self.record['version'], options={'operation': 'analytics_reports'}),
                request_key='test-guard'), commit_check=deny)
        self.assertEqual(self.count('jobs'), 0)
        with self.assertRaisesRegex(Invalid, 'transaction denial'):
            AppleMetricsSchedules(self.store).save(APP, dict(enabled=True, interval_hours=24,
                report_id=REPORT, version=None), commit_check=deny)
        self.assertEqual(self.count('apple_metrics_schedules'), 0)
        self.assertEqual(observed, [True, True])

    def test_http_requires_fresh_owner_exact_origin_and_path(self):
        handler = SimpleNamespace(command='POST', path=f'/api/apps/{APP}/apple-analytics/view', headers=Headers(),
            server=SimpleNamespace(server_port=8765, identities=self.identities, service=self.service),
            session=lambda: 'session', send=lambda status, value: (status, value))
        parts = ['api', 'apps', APP, 'apple-analytics', 'view']
        with patch.object(api, 'json_body', return_value={}):
            self.assertEqual(api.post(handler, parts)[0], 200)
            handler.path += '?other=1'
            with self.assertRaises(Invalid):
                api.post(handler, parts)
            handler.path = f'/api/apps/{APP}/apple-analytics/view'
            handler.headers.values['Origin'] = ['https://example.invalid']
            with self.assertRaises(PermissionError):
                api.post(handler, parts)
            handler.headers.values['Origin'] = ['http://127.0.0.1:8765']
            self.identities.available = False
            with self.assertRaises(PermissionError):
                api.post(handler, parts)
            handler.headers.values['Authorization'] = ['Bearer synthetic-agent-token']
            with self.assertRaises(PermissionError):
                api.post(handler, parts)


if __name__ == '__main__':
    unittest.main()
