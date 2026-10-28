"""Durable owner-opt-in Apple analytics scheduling through the shared worker."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from urllib.error import URLError
from unittest.mock import patch

from mission_control.apple_metrics_schedule import AppleMetricsSchedules, configuration
from mission_control.apple_metrics_store import read_partition
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import jobs, run_once

APP='sample-one'
STORE_APP='123'
REPORT='report-1'
REF='GROWTH_SAMPLE_ONE_ANALYTICS'
DAY='2026-10-26'
INVENTORY={'coverage':'COMPLETE','reports':[{'id':REPORT,'name':'App Downloads Standard',
    'coverage':'COMPLETE','instances':[{'id':'instance-1','processing_date':DAY,
    'granularity':'DAILY'}]}]}


def segment():
    raw=('Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n'
         f'{DAY}\t{STORE_APP}\tFirst-time download\t9\tUS\n').encode()
    packed=gzip.compress(raw,mtime=0)
    return [dict(id='segment-1',size=len(packed),
        checksum=hashlib.md5(packed,usedforsecurity=False).hexdigest(),data=packed)]


class AppleMetricsScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'state.sqlite')
        self.service=Service(self.store)
        app=self.store.app(APP)
        self.app=self.store.save_app(APP,dict(app['data'],store_app_id=STORE_APP),app['version'])
        self.connection_record=self.service.evidence(APP,dict(kind='connection',title='Apple analytics',
            source='Synthetic fixture',data={'provider':'app_store','store_app_id':STORE_APP,
                'env_ref':REF,'account_id':'0'}))
        self.schedules=AppleMetricsSchedules(self.store)
        self.environ=patch.dict(os.environ,{REF:'synthetic-private-key'})
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def save(self,enabled=True,version=None,interval=24):
        body={'enabled':enabled,'version':version}
        if enabled:
            body.update(interval_hours=interval,report_id=REPORT)
        return self.schedules.save(APP,body)

    def run_latest(self):
        with patch('mission_control.provider_reports.read_analytics',return_value=INVENTORY), \
             patch('mission_control.provider_reports.read_instance_segments',return_value=segment()):
            run_once(self.store)

    def test_owner_enable_dispatch_restart_and_atomic_success_readback(self):
        setting=self.save()
        self.assertTrue(setting['enabled'])
        self.assertEqual(setting['status'],'ENABLED')
        restarted=AppleMetricsSchedules(Store(self.store.path)).get(APP)
        self.assertEqual(restarted['id'],setting['id'])
        self.assertEqual(self.schedules.tick(),1)
        job=jobs(self.store,APP)[0]
        self.assertEqual(job['data']['options'],{'operation':'analytics_metrics_latest','report_id':REPORT})
        self.run_latest()
        saved=jobs(self.store,APP)[0]
        self.assertEqual(saved['status'],'SUCCEEDED')
        self.assertEqual(saved['result']['operation'],'analytics_metrics_latest')
        current=self.schedules.get(APP)
        self.assertEqual(current['last_job_status'],'SUCCEEDED')
        self.assertIsNotNone(current['last_success'])
        self.assertEqual(current['failures'],0)
        self.assertEqual(current['status'],'ENABLED')
        partition=read_partition(self.store.path,dict(app_id=APP,store_app_id=STORE_APP,
            connection_id=self.connection_record['id'],connection_version=self.connection_record['version'],
            report_id=REPORT,report_family='App Downloads Standard',granularity='DAILY',event_date=DAY))
        self.assertEqual(partition['instance']['rows'][0]['count'],9)
        self.assertNotIn('synthetic-private-key',json.dumps(current))
        self.assertNotIn('connection_hash',current)

    def test_configuration_requires_explicit_bounded_opt_in(self):
        for body in (
            {'enabled':1,'version':None},
            {'enabled':True,'interval_hours':23,'report_id':REPORT,'version':None},
            {'enabled':True,'interval_hours':169,'report_id':REPORT,'version':None},
            {'enabled':True,'interval_hours':True,'report_id':REPORT,'version':None},
            {'enabled':True,'interval_hours':24,'report_id':REPORT,'version':True},
            {'enabled':True,'interval_hours':24,'report_id':REPORT,'version':None,'api_key':'secret'},
        ):
            with self.subTest(body=body),self.assertRaises(Invalid):configuration(body)
        with self.assertRaises(KeyError):self.schedules.get('another-app')
        with self.assertRaises(Invalid):
            AppleMetricsSchedules(self.store).save(APP,{'enabled':True,'interval_hours':24,
                'report_id':REPORT,'version':1})
        self.assertIsNone(self.schedules.get(APP))

    def test_pause_cancels_queued_job_and_stale_attempt_cannot_commit(self):
        setting=self.save()
        self.assertEqual(self.schedules.tick(),1)
        job=jobs(self.store,APP)[0]
        paused=self.save(False,setting['version'])
        self.assertFalse(paused['enabled'])
        self.assertEqual(jobs(self.store,APP)[0]['status'],'CANCELLED')
        with patch('mission_control.provider_reports.read_analytics',side_effect=AssertionError('paused job read')):
            self.assertFalse(run_once(self.store))
        self.assertIsNone(read_partition(self.store.path,dict(app_id=APP,store_app_id=STORE_APP,
            connection_id=self.connection_record['id'],connection_version=self.connection_record['version'],
            report_id=REPORT,report_family='App Downloads Standard',granularity='DAILY',event_date=DAY)))
        self.assertEqual(jobs(self.store,APP)[0]['status'],'CANCELLED')

    def test_connection_rotation_after_download_stops_and_disables_schedule(self):
        self.save()
        self.assertEqual(self.schedules.tick(),1)
        def rotate(reader,store_id,report_id,instance_id):
            with connection(self.store.path) as db:
                db.execute('UPDATE records SET version=version+1 WHERE app_id=? AND id=?',
                           (APP,self.connection_record['id']))
            return segment()
        with patch('mission_control.provider_reports.read_analytics',return_value=INVENTORY), \
             patch('mission_control.provider_reports.read_instance_segments',side_effect=rotate):
            run_once(self.store)
        self.assertEqual(self.schedules.get(APP)['status'],'CONNECTION_CHANGED')
        self.assertFalse(self.schedules.get(APP)['enabled'])
        self.assertIsNone(read_partition(self.store.path,dict(app_id=APP,store_app_id=STORE_APP,
            connection_id=self.connection_record['id'],connection_version=self.connection_record['version'],
            report_id=REPORT,report_family='App Downloads Standard',granularity='DAILY',event_date=DAY)))

    def test_pausing_during_provider_read_prevents_persistence(self):
        setting=self.save()
        self.assertEqual(self.schedules.tick(),1)
        def pause_after_download(reader,store_id,report_id,instance_id):
            self.save(False,setting['version'])
            return segment()
        with patch('mission_control.provider_reports.read_analytics',return_value=INVENTORY), \
             patch('mission_control.provider_reports.read_instance_segments',side_effect=pause_after_download):
            run_once(self.store)
        self.assertEqual(self.schedules.get(APP)['status'],'PAUSED')
        self.assertIsNone(read_partition(self.store.path,dict(app_id=APP,store_app_id=STORE_APP,
            connection_id=self.connection_record['id'],connection_version=self.connection_record['version'],
            report_id=REPORT,report_family='App Downloads Standard',granularity='DAILY',event_date=DAY)))

    def test_transient_provider_errors_retry_only_three_attempts(self):
        self.save()
        self.assertEqual(self.schedules.tick(),1)
        for attempt in range(1,4):
            with patch('mission_control.provider_reports.read_analytics',side_effect=URLError('synthetic network')):
                run_once(self.store)
            job=jobs(self.store,APP)[0]
            if attempt < 3:
                self.assertEqual(job['status'],'RUNNING')
                self.assertEqual(job['result']['attempt'],attempt)
                with connection(self.store.path) as db:
                    db.execute('UPDATE jobs SET lease=0 WHERE id=?',(job['id'],))
            else:
                self.assertEqual(job['status'],'BLOCKED')
                self.assertEqual(self.schedules.get(APP)['failures'],1)
        self.assertEqual(self.schedules.get(APP)['status'],'ENABLED')

    def test_three_terminal_runs_block_until_explicit_resume(self):
        setting=self.save()
        for failure_count in range(1,4):
            with connection(self.store.path) as db:
                db.execute('UPDATE apple_metrics_schedules SET next_due=? WHERE app_id=?',
                           (time.time()-failure_count,APP))
            self.assertEqual(self.schedules.tick(),1)
            with patch('mission_control.worker.process',side_effect=Invalid('Synthetic schedule failure')):
                run_once(self.store)
            current=self.schedules.get(APP)
            self.assertEqual(current['failures'],failure_count)
        self.assertFalse(current['enabled'])
        self.assertEqual(current['status'],'BLOCKED')
        resumed=self.save(True,current['version'])
        self.assertTrue(resumed['enabled'])
        self.assertEqual(resumed['failures'],0)
        self.assertEqual(resumed['status'],'ENABLED')


if __name__=='__main__':
    unittest.main()
