"""Synthetic analytics readiness, hostile-source boundaries and durable worker reads."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control.apple_analytics import BASE, collection, read_analytics
from mission_control.common import Invalid
from mission_control.provider_reports import Reader as BoundedReader, read_report, report_options
from mission_control.providers import report_destination
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import run_once


def request():
    return dict(id='request-1', type='analyticsReportRequests',
        attributes=dict(accessType='ONGOING', stoppedDueToInactivity=False))


def report():
    return dict(id='report-1', type='analyticsReports',
        attributes=dict(name='App Downloads Standard', category='COMMERCE'))


def instance():
    return dict(id='instance-1', type='analyticsReportInstances',
        attributes=dict(processingDate='2026-10-01', granularity='DAILY'))


def pages(instances=None):
    return [dict(data=dict(id='123', type='apps')),
        dict(data=[request()], links={}), dict(data=[report()], links={}),
        dict(data=instances or [], links={})]


class Reader:
    def __init__(self, values):
        self.values = iter(copy.deepcopy(values))
        self.calls = []

    def read(self, url):
        self.calls.append(url)
        report_destination(url, None)
        return next(self.values)


class AnalyticsTests(unittest.TestCase):
    def test_read_analytics_waiting_never_means_zero_metrics(self):
        reader = Reader(pages())
        result = read_analytics(reader, '123')
        self.assertEqual(result['status'], 'WAITING_FOR_REPORTS')
        self.assertIsNone(result['metric_observations'])
        self.assertEqual(result['rows'], [])
        self.assertEqual(result['coverage'], 'COMPLETE')
        self.assertEqual(len(result['missing_report_types']), 4)
        self.assertEqual(len(reader.calls), 4)

    def test_instance_keeps_date_and_granularity_without_claiming_download(self):
        result = read_analytics(Reader(pages([instance()])), '123')
        self.assertEqual(result['status'], 'METRIC_DOWNLOAD_REQUIRED')
        self.assertEqual(result['reports'][0]['instances'][0]['processing_date'], '2026-10-01')
        self.assertIsNone(result['metric_observations'])

    def test_no_request_stopped_and_snapshot_require_setup(self):
        stopped = request(); stopped['attributes']['stoppedDueToInactivity'] = True
        snapshot = request(); snapshot['attributes']['accessType'] = 'ONE_TIME_SNAPSHOT'
        for rows in ([], [stopped], [snapshot]):
            with self.subTest(rows=rows):
                values = pages(); values[1]['data'] = rows
                reader = Reader(values)
                self.assertEqual(read_analytics(reader, '123')['status'], 'REPORT_SETUP_REQUIRED')
                self.assertEqual(len(reader.calls), 2)

    def test_foreign_app_and_malformed_app_fail_before_followup(self):
        for value in (dict(id='999', type='apps'), [], dict(id='123', type='other')):
            values = pages(); values[0]['data'] = value
            reader = Reader(values)
            with self.assertRaises(Invalid): read_analytics(reader, '123')
            self.assertEqual(len(reader.calls), 1)
        for value in ('../123', '١٢٣', None):
            reader = Reader([])
            with self.assertRaises(Invalid): read_analytics(reader, value)
            self.assertEqual(reader.calls, [])

    def test_partial_request_inventory_cannot_imply_new_setup_is_needed(self):
        path='/v1/apps/123/analyticsReportRequests'
        values=[dict(data=dict(id='123',type='apps'))]
        for index in range(3):
            row=request(); row['id']='snapshot-'+str(index)
            row['attributes']['accessType']='ONE_TIME_SNAPSHOT'
            values.append(dict(data=[row],links=dict(next=BASE+path+'?cursor='+str(index))))
        result=read_analytics(Reader(values),'123')
        self.assertEqual(result['status'],'REQUEST_INVENTORY_PARTIAL')
        self.assertEqual(result['coverage'],'PARTIAL')
        self.assertIsNone(result['metric_observations'])

    def test_foreign_parent_relationships_reject(self):
        for position, name, kind, foreign in ((1, 'app', 'apps', '999'),
                (2, 'analyticsReportRequest', 'analyticsReportRequests', 'foreign'),
                (3, 'analyticsReport', 'analyticsReports', 'foreign')):
            values = pages([instance()])
            values[position]['data'][0]['relationships'] = {name:dict(data=dict(type=kind,id=foreign))}
            with self.subTest(position=position), self.assertRaises(Invalid):
                read_analytics(Reader(values), '123')

    def test_bad_resource_types_identifiers_and_duplicate_requests_reject(self):
        for kind in ('other', None):
            values = pages(); values[1]['data'][0]['type'] = kind
            with self.assertRaises(Invalid): read_analytics(Reader(values), '123')
        for key in ('../other', 'a?x=1', 'a/b', 'a'*201):
            values = pages(); values[1]['data'][0]['id'] = key
            with self.assertRaises(Invalid): read_analytics(Reader(values), '123')
        values = pages(); values[1]['data'].append(dict(request(),id='request-2'))
        with self.assertRaises(Invalid): read_analytics(Reader(values), '123')

    def test_next_page_rejects_foreign_hosts_scopes_ports_fragments_and_loops(self):
        path = '/v1/apps/123/analyticsReportRequests'
        unsafe = ['https://evil.example'+path, BASE+path+'#fragment', BASE+'/v1/apps/999/analyticsReportRequests',
            'https://api.appstoreconnect.apple.com:443'+path, BASE+path+'?limit=100']
        for url in unsafe:
            reader = Reader([dict(data=[request()], links=dict(next=url))])
            with self.subTest(url=url), self.assertRaises(Invalid):
                collection(reader, path, 'analyticsReportRequests')
            self.assertEqual(len(reader.calls), 1)

    def test_collection_bounds_conflicts_and_partial_coverage(self):
        path = '/v1/apps/123/analyticsReportRequests'
        values = [dict(data=[dict(request(),id='request-'+str(i))],links=dict(next=BASE+path+'?cursor='+str(i))) for i in range(3)]
        rows, complete = collection(Reader(values), path, 'analyticsReportRequests')
        self.assertEqual(len(rows), 3); self.assertFalse(complete)
        changed = request(); changed['attributes']['stoppedDueToInactivity'] = True
        with self.assertRaises(Invalid):
            collection(Reader([dict(data=[request(), changed],links={})]), path, 'analyticsReportRequests')
        for payload in (dict(data=[request()]*101,links={}),dict(data=[],links=[])):
            with self.assertRaises(Invalid): collection(Reader([payload]),path,'analyticsReportRequests')

    def test_instance_dates_granularity_and_duplicate_report_names_reject(self):
        for field, value in (('processingDate','2026-02-30'),('processingDate','20261001'),('granularity','UNKNOWN')):
            values = pages([instance()]); values[3]['data'][0]['attributes'][field] = value
            with self.assertRaises(Invalid): read_analytics(Reader(values),'123')
        values = pages(); values[2]['data'].append(dict(report(),id='report-2'))
        with self.assertRaises(Invalid): read_analytics(Reader(values),'123')

    def test_allowlist_only_permits_read_endpoints(self):
        urls = [BASE+'/v1/apps/123/analyticsReportRequests',BASE+'/v1/analyticsReportRequests/request-1/reports',BASE+'/v1/analyticsReports/report-1/instances']
        for url in urls:
            report_destination(url,None)
            with self.assertRaises(Invalid): report_destination(url,{})
        for url in (BASE+'/v1/analyticsReportRequests',BASE+'/v1/analyticsReports/report-1/segments'):
            with self.assertRaises(Invalid): report_destination(url,None)
        for options in ({'operation':'analytics_reports','app_id':'999'},{'operation':'analytics_reports','request_id':'foreign'}):
            with self.assertRaises(Invalid): report_options('app_store',options)

    def test_reader_deadline_rejects_before_network(self):
        with patch('mission_control.provider_reports.time.monotonic',side_effect=[0,46]), patch('mission_control.provider_reports.report_request') as network:
            reader=BoundedReader({'Authorization':'Bearer synthetic'})
            with self.assertRaisesRegex(Invalid,'budget expired'): reader.read(BASE+'/v1/apps/123')
            network.assert_not_called()

    def test_worker_persists_source_hashes_and_rejects_cross_app(self):
        binding = dict(provider='app_store',env_ref='GROWTH_SAMPLE_ONE_ANALYTICS',store_app_id='123',account_id='0')
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{binding['env_ref']:'synthetic-token'}):
            store = Store(Path(directory)/'state.sqlite'); service = Service(store)
            connection = service.evidence('sample-one',dict(kind='connection',title='Synthetic analytics',source='Synthetic only',data=binding))
            body = dict(action='sync',data=dict(connection_id=connection['id'],options=dict(operation='analytics_reports')),request_key='analytics-1')
            job = service.queue('sample-one',body)
            with patch('mission_control.provider_reports.report_request',side_effect=pages()): run_once(store)
            saved = Service(Store(store.path)).workspace('sample-one')['jobs'][0]
            self.assertEqual(saved['id'],job['id']); self.assertEqual(saved['status'],'SUCCEEDED')
            result = saved['result']
            self.assertEqual(result['app_id'],'sample-one'); self.assertEqual(len(result['page_source_hashes']),4)
            self.assertEqual(result['status'],'WAITING_FOR_REPORTS'); self.assertFalse(result['external_writes'])
            self.assertNotIn('synthetic-token',json.dumps(result))
            with self.assertRaises(Invalid): service.queue('sample-two',dict(body,request_key='foreign'))

    def test_protected_dispatch_is_closed_to_another_provider(self):
        with self.assertRaises(Invalid): report_options('apple_ads',dict(operation='analytics_reports'))
        with patch.dict(os.environ,{'GROWTH_SAMPLE_ONE_ANALYTICS':'synthetic-token'}), patch('mission_control.provider_reports.report_request',side_effect=pages()):
            result=read_report(dict(provider='app_store',env_ref='GROWTH_SAMPLE_ONE_ANALYTICS',store_app_id='123'),'sample-one',dict(operation='analytics_reports'))
        self.assertEqual(result['store_app_id'],'123'); self.assertIsNone(result['metric_observations'])
