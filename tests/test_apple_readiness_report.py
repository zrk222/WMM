"""Scheduled Apple read readiness in the shared app-scoped report."""
import json
from datetime import timedelta
import unittest
from unittest.mock import patch

from mission_control.common import canonical, iso_time, now
from mission_control.db import connection
from mission_control.ios_reports import read, snapshot
from mission_control.worker import jobs, run_once
from mission_control.service import Service
from tests import test_apple_metrics_schedule as fixture
from tests import test_ios_host as host_fixture


class AppleReadinessReportTests(unittest.TestCase):
    setUp = fixture.AppleMetricsScheduleTests.setUp
    save = fixture.AppleMetricsScheduleTests.save
    waiting_read = fixture.AppleMetricsScheduleTests.waiting_read
    run_latest = fixture.AppleMetricsScheduleTests.run_latest

    def rows(self):
        return {r['metric']: r for r in read(self.store, fixture.APP)['rows']}

    def wait_once(self):
        self.save()
        self.assertEqual(self.schedules.tick(), 1)
        with patch('mission_control.provider_reports.read_analytics', side_effect=self.waiting_read):
            self.assertTrue(run_once(self.store))

    def test_verified_waiting_is_reported_without_numeric_outcome(self):
        self.wait_once()
        report = read(self.store, fixture.APP)
        rows = {r['metric']: r for r in report['rows']}
        self.assertEqual(rows['Apple scheduled read']['observed'], 'WAITING_FOR_REPORTS')
        self.assertEqual(rows['Apple schedule']['observed'], 'ENABLED')
        self.assertIsNotNone(rows['Apple read observed']['observed'])
        self.assertIsNotNone(rows['Apple next due']['observed'])
        self.assertIn('no daily report', rows['Apple next action']['observed'])
        self.assertIsNone(rows['Apple numeric outcome']['observed'])
        self.assertIsNone(rows['App performance']['observed'])
        encoded = json.dumps(report)
        for private in (fixture.REPORT, '"'+fixture.STORE_APP+'"', fixture.REF, self.connection_record['id'], 'synthetic-private-key'):
            self.assertNotIn(private, encoded)

    def test_workspace_guided_workflow_projects_waiting_exception(self):
        self.wait_once()
        workflow = Service(self.store).workspace(fixture.APP)['workflow']
        self.assertEqual(len(workflow['exceptions']), 1)
        exception = workflow['exceptions'][0]
        self.assertEqual(exception['state'], 'WAITING_FOR_REPORTS')
        self.assertEqual(exception['repair_route'], 'apple-analytics')
        self.assertIn('does not mean zero activity', exception['reason'])
        self.assertIsNotNone(exception['observed_at'])
        self.assertIsNotNone(exception['next_due'])
        self.assertNotIn(fixture.REPORT, json.dumps(exception))

    def test_waiting_read_shows_repair_after_saved_due_time(self):
        self.wait_once()
        service = Service(self.store)
        before = service.workspace(fixture.APP)['workflow']['exceptions'][0]
        self.assertIn('keep the schedule enabled', before['next_action'].lower())
        after_due = (iso_time(before['next_due']) + timedelta(seconds=1)).isoformat()
        schedule = self.schedules.get(fixture.APP)
        saved_jobs = jobs(self.store, fixture.APP)
        with patch('mission_control.service.now', return_value=after_due):
            after = service.workspace(fixture.APP)['workflow']['exceptions'][0]
        self.assertEqual(after['state'], 'WAITING_FOR_REPORTS')
        self.assertEqual(after['observed_at'], before['observed_at'])
        self.assertEqual(after['next_due'], before['next_due'])
        self.assertIn('scheduled refresh is overdue', after['next_action'])
        self.assertIn('Check that the WMM worker is running', after['next_action'])
        self.assertEqual(after['repair_route'], 'apple-analytics')
        self.assertEqual(self.schedules.get(fixture.APP), schedule)
        self.assertEqual(jobs(self.store, fixture.APP), saved_jobs)

    def test_absent_paused_and_source_changed_are_distinct(self):
        self.assertEqual(self.rows()['Apple schedule']['observed'], 'NOT_CONFIGURED')
        self.wait_once()
        self.save(False, self.schedules.get(fixture.APP)['version'])
        rows = self.rows()
        self.assertEqual(rows['Apple schedule']['observed'], 'PAUSED')
        self.assertNotEqual(rows['Apple scheduled read']['observed'], 'WAITING_FOR_REPORTS')
        with connection(self.store.path) as db:
            db.execute('UPDATE records SET version=version+1 WHERE id=?', (self.connection_record['id'],))
        self.assertEqual(self.rows()['Apple schedule']['observed'], 'SOURCE_CHANGED')
        with connection(self.store.path) as db:
            db.execute('UPDATE records SET version=version-1 WHERE id=?', (self.connection_record['id'],))
            app_data = json.loads(db.execute('SELECT data FROM apps WHERE id=?', (fixture.APP,)).fetchone()['data'])
            app_data.pop('store_app_id')
            db.execute('UPDATE apps SET data=? WHERE id=?', (canonical(app_data), fixture.APP))
        self.assertEqual(self.rows()['Apple schedule']['observed'], 'SOURCE_CHANGED')

    def test_non_apple_app_has_no_irrelevant_apple_setup_rows(self):
        self.store.save_app('android-only', dict(name='Synthetic Android app'))
        report = read(self.store, 'android-only')
        self.assertFalse(any(r['metric'].startswith('Apple ') for r in report['rows']))

    def test_numeric_and_failed_job_states_do_not_expose_raw_results(self):
        self.save()
        self.assertEqual(self.schedules.tick(), 1)
        self.run_latest()
        rows = self.rows()
        self.assertEqual(rows['Apple scheduled read']['observed'], 'DOWNLOAD_OBSERVATIONS_AVAILABLE')
        self.assertIsNone(rows['Apple numeric outcome']['observed'])
        self.assertTrue(any(k.endswith('download_events') for k in rows))
        saved = jobs(self.store, fixture.APP)[0]
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET result=? WHERE id=?',
                       (canonical(dict(saved['result'], observed_at='2099-01-01T00:00:00+00:00')), saved['id']))
        self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET status=?,result=? WHERE id=?',
                       ('FAILED', canonical({'error':'PRIVATE_PROVIDER_ERROR'}), saved['id']))
        report = read(self.store, fixture.APP)
        self.assertEqual(next(r for r in report['rows'] if r['metric']=='Apple scheduled read')['observed'], 'FAILED')
        self.assertNotIn('PRIVATE_PROVIDER_ERROR', json.dumps(report))
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET updated=? WHERE id=?', ('2099-01-01T00:00:00+00:00', saved['id']))
        self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET updated=? WHERE id=?', (now(), saved['id']))
        with connection(self.store.path) as db:
            db.execute("UPDATE apple_metrics_schedules SET enabled=0,status='BLOCKED' WHERE app_id=?", (fixture.APP,))
        rows = self.rows()
        self.assertEqual(rows['Apple schedule']['observed'], 'BLOCKED')
        self.assertEqual(rows['Apple scheduled read']['observed'], 'FAILED')
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET updated=? WHERE id=?', ('2099-01-01T00:00:00+00:00', saved['id']))
        self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')
        self.assertIsNone(self.rows()['Apple read observed']['observed'])
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET data=? WHERE id=?',
                (canonical(dict(saved['data'], analytics_schedule_version=999)), saved['id']))
        self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')

    def test_waiting_observation_must_not_be_after_report_time(self):
        self.wait_once()
        saved = jobs(self.store, fixture.APP)[0]
        for timestamp, expected in (('2099-01-01T00:00:00+00:00', 'UNCONFIRMED'),
                                    ('2024-01-01T00:00:00-05:00', 'WAITING_FOR_REPORTS')):
            with self.subTest(timestamp=timestamp), connection(self.store.path) as db:
                db.execute('UPDATE jobs SET result=? WHERE id=?',
                           (canonical(dict(saved['result'], observed_at=timestamp)), saved['id']))
            rows = self.rows()
            self.assertEqual(rows['Apple scheduled read']['observed'], expected)
            self.assertEqual(rows['Apple read observed']['observed'], timestamp if expected == 'WAITING_FOR_REPORTS' else None)

    def test_malformed_foreign_and_changed_bindings_are_unconfirmed(self):
        self.wait_once()
        saved = jobs(self.store, fixture.APP)[0]
        for field, value in (('app_id','foreign'), ('report_id','foreign'), ('connection_id','foreign'),
                             ('connection_hash','0'*64), ('metric_observations',0), ('coverage','PARTIAL')):
            with self.subTest(field=field):
                with connection(self.store.path) as db:
                    db.execute('UPDATE jobs SET result=? WHERE id=?',
                               (canonical(dict(saved['result'], **{field:value})), saved['id']))
                self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')
        with connection(self.store.path) as db:
            db.execute('UPDATE jobs SET result=?,data=? WHERE id=?',
                (canonical(saved['result']), canonical(dict(saved['data'], analytics_schedule_version=999)), saved['id']))
        self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')
        with connection(self.store.path) as db:
            db.execute('UPDATE apple_metrics_schedules SET last_job=? WHERE app_id=?', ('foreign-job', fixture.APP))
        self.assertEqual(self.rows()['Apple scheduled read']['observed'], 'UNCONFIRMED')

    def test_health_is_source_bound_but_business_projection_is_unchanged(self):
        stamp = now()
        with connection(self.store.path) as db:
            before = snapshot(db, self.store, fixture.APP, stamp)
            business_before = snapshot(db, self.store, fixture.APP, stamp, include_workflows=False)
        self.wait_once()
        with connection(self.store.path) as db:
            after = snapshot(db, self.store, fixture.APP, stamp)
            business_after = snapshot(db, self.store, fixture.APP, stamp, include_workflows=False)
        self.assertNotEqual(before['sourceHash'], after['sourceHash'])
        self.assertEqual(business_before, business_after)
        self.assertFalse(any(r['metric'].startswith('Apple schedule') for r in business_after['rows']))


class NativeAppleReadinessReportTests(unittest.TestCase):
    setUp = host_fixture.NativeRuntimeTests.setUp
    verify = host_fixture.NativeRuntimeTests.verify
    creation = host_fixture.NativeRuntimeTests.creation
    waiting_read = fixture.AppleMetricsScheduleTests.waiting_read

    def test_owner_and_scoped_agent_receive_same_verified_waiting_rows(self):
        from datetime import datetime, timedelta, timezone
        from mission_control.apple_metrics_schedule import AppleMetricsSchedules
        from mission_control.ios_agent_access import NativeAgentAccess

        self.runtime.create_workspace(self.session, self.creation())
        store = self.runtime.service.store
        app = store.app('new-app')
        app = store.save_app('new-app', dict(app['data'], store_app_id=fixture.STORE_APP), app['version'])
        self.runtime.service.evidence('new-app', dict(kind='connection', title='Synthetic Apple', source='fixture',
            data={'provider':'app_store', 'store_app_id':fixture.STORE_APP, 'env_ref':'GROWTH_NEW_APP_ANALYTICS', 'account_id':'0'}))
        schedules = AppleMetricsSchedules(store)
        schedules.save('new-app', dict(enabled=True, version=None, interval_hours=24, report_id=fixture.REPORT))
        self.assertEqual(schedules.tick(), 1)
        with patch.dict('os.environ', {'GROWTH_NEW_APP_ANALYTICS':'synthetic-private-key'}), \
             patch('mission_control.provider_reports.read_analytics', side_effect=self.waiting_read):
            self.assertTrue(run_once(store))
        owner = json.loads(self.runtime.report(self.session, 'new-app'))
        access = NativeAgentAccess(self.runtime.service, self.runtime.identities)
        scope = dict(agent_id='report-agent', manifest_version=app['version'], operations=['report.read'],
                     expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(), max_calls=2)
        issued = json.loads(access.manage(self.session, 'new-app', 'issue',
            json.dumps({'confirm_scope':True, 'grant':scope}).encode()))
        value = json.loads(access.call(self.session, issued['token'],
            json.dumps(dict(app_id='new-app', operation='report.read', input={})).encode()))
        self.assertEqual(value['rows'], owner['rows'])
        self.assertEqual(value['sourceHash'], owner['sourceHash'])
        self.assertEqual(next(r['observed'] for r in value['rows'] if r['metric']=='Apple scheduled read'), 'WAITING_FOR_REPORTS')
        self.assertNotIn(issued['token'], json.dumps(value))
        with self.assertRaises(PermissionError):
            access.call(self.session, issued['token'], json.dumps(dict(app_id='other',operation='report.read',input={})).encode())


if __name__ == '__main__':
    unittest.main()
