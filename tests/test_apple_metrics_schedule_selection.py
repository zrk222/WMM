"""Choose the newest complete daily Apple downloads instance deterministically."""
import gzip
import hashlib
import unittest
from unittest.mock import patch

from mission_control.apple_analytics import DISCOVERY
from mission_control.common import Invalid, digest
from mission_control.marketing_agent_manifest import APPLE_READ_OPERATIONS, authorize_read, operating_manifest
from mission_control.provider_reports import prepare_analytics_metrics, report_options

APP = 'sample-one'
STORE_APP = '123'
REPORT = 'report-1'


def inventory(instances, coverage='COMPLETE'):
    return {'coverage':coverage,'reports':[{'id':REPORT,'name':'App Downloads Standard',
        'coverage':'COMPLETE','instances':instances}]}


def segment(day):
    body=('Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n'
          f'{day}\t{STORE_APP}\tFirst-time download\t7\tUS\n').encode()
    data=gzip.compress(body,mtime=0)
    return [dict(id='segment-'+day,size=len(data),
        checksum=hashlib.md5(data,usedforsecurity=False).hexdigest(),data=data)]


class Reader:
    hashes = ['synthetic-report-metadata-hash']


class AppleMetricsScheduleSelectionTests(unittest.TestCase):
    def setUp(self):
        self.binding={'provider':'app_store','store_app_id':STORE_APP,'env_ref':'GROWTH_SAMPLE_ONE_ANALYTICS'}
        self.reader=Reader()

    def prepare(self, options, rows):
        with patch('mission_control.provider_reports.read_analytics',return_value=inventory(rows)), \
             patch('mission_control.provider_reports.read_instance_segments',side_effect=lambda reader,store,report,instance: segment(
                 next(row['processing_date'] for row in rows if row['id']==instance))) as download:
            result=prepare_analytics_metrics(self.reader,self.binding,APP,STORE_APP,options,'connection-1',2)
        return result,download

    def test_latest_operation_selects_only_newest_complete_daily_instance(self):
        rows=[{'id':'older','processing_date':'2026-10-23','granularity':'DAILY'},
              {'id':'weekly','processing_date':'2026-10-27','granularity':'WEEKLY'},
              {'id':'newest','processing_date':'2026-10-26','granularity':'DAILY'}]
        prepared,download=self.prepare({'operation':'analytics_metrics_latest','report_id':REPORT},rows)
        download.assert_called_once_with(self.reader,STORE_APP,REPORT,'newest')
        self.assertEqual(prepared.identity['report_id'],REPORT)
        self.assertEqual(prepared.partitions[0]['partition']['event_date'],'2026-10-26')
        self.assertEqual(prepared.summary(['INSERTED'])['operation'],'analytics_metrics_latest')

    def test_exact_owner_selection_is_preserved(self):
        rows=[{'id':'older','processing_date':'2026-10-23','granularity':'DAILY'},
              {'id':'newest','processing_date':'2026-10-26','granularity':'DAILY'}]
        prepared,download=self.prepare({'operation':'analytics_metrics','report_id':REPORT,'instance_id':'older'},rows)
        download.assert_called_once_with(self.reader,STORE_APP,REPORT,'older')
        self.assertEqual(prepared.summary(['INSERTED'])['operation'],'analytics_metrics')

    def test_latest_rejects_partial_report_before_segment_download(self):
        rows=[{'id':'newest','processing_date':'2026-10-26','granularity':'DAILY'}]
        with patch('mission_control.provider_reports.read_analytics',return_value=inventory(rows,'PARTIAL')), \
             patch('mission_control.provider_reports.read_instance_segments') as download, \
             self.assertRaisesRegex(Invalid,'complete App Downloads Standard'):
            prepare_analytics_metrics(self.reader,self.binding,APP,STORE_APP,
                {'operation':'analytics_metrics_latest','report_id':REPORT},'connection-1',2)
        download.assert_not_called()

    def test_existing_downloads_paths_reject_discovery_before_segment_download(self):
        rows = [dict(id='newest', processing_date='2026-10-26', granularity='DAILY')]
        discovery = inventory(rows)
        discovery['reports'][0]['name'] = DISCOVERY
        for options in (dict(operation='analytics_metrics_latest', report_id=REPORT),
                        dict(operation='analytics_metrics', report_id=REPORT, instance_id='newest')):
            with self.subTest(options=options), \
                 patch('mission_control.provider_reports.read_analytics', return_value=discovery), \
                 patch('mission_control.provider_reports.read_instance_segments') as download, \
                 self.assertRaisesRegex(Invalid, 'complete App Downloads Standard'):
                prepare_analytics_metrics(self.reader, self.binding, APP, STORE_APP,
                                          options, 'connection-1', 2)
            download.assert_not_called()

    def test_latest_waits_for_daily_and_rejects_ambiguous_daily(self):
        for rows in ([], [{'id':'weekly','processing_date':'2026-10-27','granularity':'WEEKLY'}]):
            prepared, download = self.prepare({'operation':'analytics_metrics_latest','report_id':REPORT}, rows)
            self.assertEqual(prepared.partitions, ())
            self.assertEqual(prepared.summary([])['status'], 'WAITING_FOR_REPORTS')
            self.assertIsNone(prepared.summary([])['metric_observations'])
            download.assert_not_called()
        rows=[{'id':'a','processing_date':'2026-10-26','granularity':'DAILY'},
              {'id':'b','processing_date':'2026-10-26','granularity':'DAILY'}]
        with patch('mission_control.provider_reports.read_analytics',return_value=inventory(rows)), \
             patch('mission_control.provider_reports.read_instance_segments') as download, \
             self.assertRaises(Invalid):
            prepare_analytics_metrics(self.reader,self.binding,APP,STORE_APP,
                {'operation':'analytics_metrics_latest','report_id':REPORT},'connection-1',2)
        download.assert_not_called()

    def test_waiting_requires_complete_selected_report_and_source_evidence(self):
        for value in ({'coverage':'PARTIAL','reports':inventory([])['reports']},
                      {'coverage':'COMPLETE','reports':[]},
                      {'coverage':'COMPLETE','reports':[{'id':REPORT,'name':'App Downloads Standard',
                                                          'coverage':'PARTIAL','instances':[]}]}):
            with self.subTest(value=value), patch('mission_control.provider_reports.read_analytics',return_value=value), \
                 self.assertRaises(Invalid):
                prepare_analytics_metrics(self.reader,self.binding,APP,STORE_APP,
                    {'operation':'analytics_metrics_latest','report_id':REPORT},'connection-1',2)
        reader=Reader()
        reader.hashes=[]
        with patch('mission_control.provider_reports.read_analytics',return_value=inventory([])),self.assertRaises(Invalid):
            prepare_analytics_metrics(reader,self.binding,APP,STORE_APP,
                {'operation':'analytics_metrics_latest','report_id':REPORT},'connection-1',2)

    def test_agent_manifest_allows_latest_read_only_operation(self):
        self.assertIn('analytics_metrics_latest',APPLE_READ_OPERATIONS)
        app={'id':APP,'version':1,'data':{'store_app_id':STORE_APP}}
        policy=operating_manifest(app)
        request={'connection_id':'connection-1','connection_version':2,'manifest_version':1,
                 'agent_policy_sha256':digest(policy),
                 'options':{'operation':'analytics_metrics_latest','report_id':REPORT}}
        authorize_read(app,self.binding,request)
        with self.assertRaisesRegex(Invalid,'does not permit'):
            authorize_read(app,self.binding,dict(request,options={'operation':'campaign_report'}))

    def test_latest_options_are_provider_and_field_bounded(self):
        options={'operation':'analytics_metrics_latest','report_id':REPORT}
        self.assertEqual(report_options('app_store',options),options)
        for provider in ('apple_ads','google_play'):
            with self.subTest(provider=provider),self.assertRaises(Invalid):
                report_options(provider,options)
        with self.assertRaises(Invalid):
            report_options('app_store',dict(options,instance_id='newest'))


if __name__=='__main__':
    unittest.main()
