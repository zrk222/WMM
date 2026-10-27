"""Durable Apple metrics reads through the existing bounded worker path."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.apple_metrics_store import read_partition
from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.marketing_agent_manifest import operating_manifest
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once

APP='sample-one'
STORE_APP='123'
REPORT='report-1'
INSTANCE='instance-1'
REF='GROWTH_SAMPLE_ONE_ANALYTICS'
OPTIONS={'operation':'analytics_metrics','report_id':REPORT,'instance_id':INSTANCE}
INVENTORY={'coverage':'COMPLETE','reports':[{'id':REPORT,'name':'App Downloads Standard',
    'coverage':'COMPLETE','instances':[{'id':INSTANCE,'processing_date':'2026-10-24',
    'granularity':'DAILY'}]}]}


def segment(count='7'):
    body=('Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n'
          f'2026-10-24\t{STORE_APP}\tFirst-time download\t{count}\tUS\n').encode()
    data=gzip.compress(body,mtime=0)
    return [dict(id='segment-1',size=len(data),
        checksum=hashlib.md5(data,usedforsecurity=False).hexdigest(),data=data)]


class AppleMetricsWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=Store(Path(self.temp.name)/'state.sqlite')
        self.service=Service(self.store)
        self.binding=dict(provider='app_store',env_ref=REF,store_app_id=STORE_APP,account_id='0')
        self.connection=self.service.evidence(APP,dict(kind='connection',title='Apple analytics',
            source='Synthetic fixture',data=self.binding))
        self.environ=patch.dict(os.environ,{REF:'synthetic-private-key'})
        self.environ.start()
        self.addCleanup(self.environ.stop)

    def queue(self,options=None,request_key='metrics-1',extra=None):
        data=dict(connection_id=self.connection['id'],options=OPTIONS if options is None else options)
        data.update(extra or {})
        return self.service.queue(APP,dict(action='sync',data=data,request_key=request_key))

    def read(self):
        return read_partition(self.store.path,dict(app_id=APP,store_app_id=STORE_APP,
            connection_id=self.connection['id'],connection_version=self.connection['version'],
            report_id=REPORT,report_family='App Downloads Standard',granularity='DAILY',
            event_date='2026-10-24'))

    def run_prepared(self,count='7',inventory=None):
        self.queue()
        with patch('mission_control.provider_reports.read_analytics',
                   return_value=INVENTORY if inventory is None else inventory), \
             patch('mission_control.provider_reports.read_instance_segments',
                   return_value=segment(count)):
            run_once(self.store)
        return Service(Store(self.store.path)).workspace(APP)['jobs'][0]

    def test_complete_instance_is_committed_with_job_and_source_readback(self):
        job=self.run_prepared()
        self.assertEqual(job['status'],'SUCCEEDED')
        self.assertEqual(job['result']['operation'],'analytics_metrics')
        self.assertEqual(job['result']['coverage'],'COMPLETE')
        self.assertEqual(job['result']['observation_count'],1)
        self.assertEqual(job['result']['partitions'][0]['status'],'INSERTED')
        self.assertEqual(self.read()['instance']['rows'][0]['count'],7)
        self.assertNotIn('synthetic-private-key',json.dumps(job['result']))
        self.assertNotIn('signed_url',json.dumps(job['result']))

    def test_agent_manifest_allows_only_the_supported_analytics_read(self):
        app=self.store.app(APP)
        data=dict(app['data'],store_app_id=STORE_APP)
        app=self.store.save_app(APP,data,app['version'])
        policy=operating_manifest(app)
        request=dict(connection_id=self.connection['id'],connection_version=self.connection['version'],
            manifest_version=app['version'],agent_policy_sha256=digest(policy),options=OPTIONS)
        self.queue(request_key='agent-metrics-1',extra={
            'manifest_version':app['version'],'agent_policy_sha256':digest(policy)})
        with patch('mission_control.provider_reports.read_analytics',return_value=INVENTORY), \
             patch('mission_control.provider_reports.read_instance_segments',return_value=segment()):
            run_once(self.store)
        job=Service(Store(self.store.path)).workspace(APP)['jobs'][0]
        self.assertEqual(job['status'],'SUCCEEDED')
        self.assertEqual(job['result']['operation'],'analytics_metrics')
        from mission_control.marketing_agent_manifest import authorize_read
        authorize_read(app,self.binding,request)
        with self.assertRaisesRegex(Invalid,'does not permit'):
            authorize_read(app,self.binding,dict(request,options=dict(operation='campaign_report')))

    def test_partial_or_unselected_inventory_never_downloads_or_persists(self):
        partial=dict(INVENTORY,coverage='PARTIAL')
        self.queue()
        with patch('mission_control.provider_reports.read_analytics',return_value=partial), \
             patch('mission_control.provider_reports.read_instance_segments') as download:
            run_once(self.store)
        job=Service(Store(self.store.path)).workspace(APP)['jobs'][0]
        self.assertEqual(job['status'],'BLOCKED')
        download.assert_not_called()
        self.assertIsNone(self.read())

    def test_connection_rotation_after_read_prevents_metric_commit(self):
        self.queue()
        calls=0
        def guard_after_read(store,job):
            nonlocal calls
            calls+=1
            if calls==2:
                with connection(store.path) as db:
                    db.execute('UPDATE records SET version=version+1 WHERE id=?',(self.connection['id'],))
            return None
        with patch('mission_control.provider_reports.read_analytics',return_value=INVENTORY), \
             patch('mission_control.provider_reports.read_instance_segments',return_value=segment()), \
             patch('mission_control.sequence_jobs.guard_owned',side_effect=guard_after_read):
            run_once(self.store)
        job=Service(Store(self.store.path)).workspace(APP)['jobs'][0]
        self.assertEqual(job['status'],'BLOCKED')
        self.assertIsNone(self.read())

    def test_sql_failure_rolls_back_partitions_and_records_blocked_job(self):
        self.queue()
        with connection(self.store.path) as db:
            db.execute("CREATE TRIGGER apple_metrics_test_fail BEFORE INSERT ON apple_metric_partitions "
                       "BEGIN SELECT RAISE(ABORT,'synthetic database failure'); END")
        with patch('mission_control.provider_reports.read_analytics',return_value=INVENTORY), \
             patch('mission_control.provider_reports.read_instance_segments',return_value=segment()):
            run_once(self.store)
        job=Service(Store(self.store.path)).workspace(APP)['jobs'][0]
        self.assertEqual(job['status'],'BLOCKED')
        self.assertNotIn('synthetic database failure',json.dumps(job['result']))
        self.assertIsNone(self.read())

    def test_options_are_closed_to_other_providers_and_input_fields(self):
        from mission_control.provider_reports import report_options
        self.assertEqual(report_options('app_store',OPTIONS),OPTIONS)
        for provider in ('apple_ads','google_play'):
            with self.subTest(provider=provider),self.assertRaises(Invalid):
                report_options(provider,OPTIONS)
        with self.assertRaises(Invalid):
            report_options('app_store',dict(OPTIONS,store_app_id='999'))


if __name__=='__main__':
    unittest.main()
