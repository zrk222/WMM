"""Native App Store protected storage, signer and read-only inventory on SQLite."""
import base64
import copy
import gzip
import json
import unittest
from unittest.mock import patch
from uuid import uuid4

from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.ios_store_connection import NativeStoreConnection
from tests import test_ios_host as fixture
from tests.test_apple_analytics import pages
from tests.test_apple_metrics_transport import readiness_pages, segment

KEY='-----BEGIN PRIVATE KEY-----\nQUJDRA==\n-----END PRIVATE KEY-----'


class NativeStoreConnectionTests(unittest.TestCase):
    setUp=fixture.NativeRuntimeTests.setUp
    verify=fixture.NativeRuntimeTests.verify
    creation=fixture.NativeRuntimeTests.creation

    def start(self):
        body=json.loads(self.creation());body['manifest']['store_app_id']='123'
        self.runtime.create_workspace(self.session,json.dumps(body).encode())
        self.values={};self.operations=[];self.fail_delete=False
        self.gateway=NativeStoreConnection(self.runtime.service,self.runtime.identities,self.vault,self.sign)

    def vault(self,raw):
        body=json.loads(raw);self.operations.append((body['action'],body['target']))
        if body['action']=='put':self.values[body['target']]=copy.deepcopy(body['value']);value=None
        elif body['action']=='get':value=copy.deepcopy(self.values.get(body['target']))
        else:
            if self.fail_delete:return json.dumps({'ok':False,'value':None}).encode()
            self.values.pop(body['target'],None);value=None
        return json.dumps({'ok':True,'value':value}).encode()

    def sign(self,raw):
        body=json.loads(raw);self.operations.append(('signer',body['operation']))
        value={'public_key':'-----BEGIN PUBLIC KEY-----\nSYNTHETIC\n-----END PUBLIC KEY-----'} if body['operation']=='inspect' else {'signature':base64.b64encode(b'x'*64).decode()}
        return json.dumps({'ok':True,'value':value}).encode()

    def call(self,action,body=None,app='new-app'):
        return json.loads(self.gateway.call(self.session,app,action,json.dumps(body or {}).encode()))

    def setup(self,**extra):
        return self.call('setup',dict({'store_app_id':'123','key_id':'KEY1','issuer_id':'issuer-1','private_key':KEY,'confirm_storage':True},**extra))

    def queue(self,record,key='inventory-1'):
        return self.call('queue_inventory',dict(connection_id=record['id'],connection_version=record['version'],request_key=key))

    def queue_metrics(self,record,report='report-1',key='metrics-1'):
        return self.call('queue_metrics',dict(connection_id=record['id'],connection_version=record['version'],request_key=key,report_id=report))

    def test_protected_setup_inventory_read_and_disconnect(self):
        self.start();result=self.setup();record=result['record'];job=self.queue(record)
        with patch('mission_control.provider_reports.report_request',side_effect=pages()) as http:
            done=self.call('run_inventory',{'id':job['id']})
        self.assertEqual(done['status'],'SUCCEEDED');self.assertEqual(done['result']['operation'],'analytics_reports')
        self.assertEqual(done['result']['status'],'WAITING_FOR_REPORTS');self.assertEqual(http.call_count,4)
        self.assertEqual(self.call('view')['connections'][0]['status']['status'],'PROTECTED_KEY_PRESENT')
        self.assertTrue(next(iter(self.values)).startswith('AppGrowth/'))
        self.assertIn(('signer','inspect'),self.operations);self.assertIn(('signer','sign'),self.operations)
        self.assertNotIn(KEY,json.dumps(result)+json.dumps(done)+json.dumps(self.call('view')))
        for file in self.path.parent.glob(self.path.name+'*'):self.assertNotIn(KEY.encode(),file.read_bytes())
        self.assertEqual(self.call('disconnect',{'id':record['id'],'version':1,'confirm_disconnect':True})['status'],'DISCONNECTED')
        self.assertEqual(self.values,{})

    def test_scope_fixed_actions_and_invalid_signer_fail_closed(self):
        self.start()
        with self.assertRaises(PermissionError):self.call('view',app='other')
        with self.assertRaises(Invalid):self.setup(store_app_id='999')
        with self.assertRaises(Invalid):self.call('setup',dict(store_app_id='123',key_id='KEY1',issuer_id='issuer-1',private_key=KEY,confirm_storage=False))
        with self.assertRaises(Invalid):self.call('arbitrary',{})
        self.gateway.signer_callback=lambda raw:b'{"ok":false,"value":null}'
        with self.assertRaises(Invalid):self.setup()
        self.assertEqual(self.values,{})

    def test_rotation_stale_job_and_cleanup_failure(self):
        self.start();old=self.setup()['record'];job=self.queue(old)
        rotated=self.setup(id=old['id'],version=1)['record']
        with self.assertRaises(Invalid):self.call('run_inventory',{'id':job['id']})
        self.fail_delete=True
        result=self.call('disconnect',{'id':rotated['id'],'version':2,'confirm_disconnect':True})
        self.assertEqual(result['cleanup'],'PRIOR_LOCAL_KEY_CLEANUP_REQUIRED')
        self.assertEqual(self.call('view')['connections'][0]['status']['status'],'DISCONNECTED')
        self.assertTrue(self.call('cleanup')['cleanup_required'])
        self.fail_delete=False
        self.assertEqual(self.call('cleanup')['removed'],1)
        self.assertEqual(self.values,{})

    def test_generation_changes_during_network_cannot_commit_result(self):
        self.start();record=self.setup()['record'];job=self.queue(record)
        values=iter(pages())
        def provider(*args,**kwargs):
            result=next(values);self.generation=str(uuid4());return result
        with patch('mission_control.provider_reports.report_request',side_effect=provider) as reader:
            with self.assertRaises(PermissionError):self.call('run_inventory',{'id':job['id']})
        self.assertEqual(reader.call_count,1)
        with connection(self.path) as db:
            row=db.execute('SELECT status,result FROM jobs WHERE id=?',(job['id'],)).fetchone()
            self.assertEqual(row['status'],'RUNNING');self.assertIsNone(row['result'])

    def test_tampered_connection_and_provider_errors_do_not_commit_success(self):
        self.start();record=self.setup()['record'];job=self.queue(record)
        with connection(self.path) as db:
            db.execute("UPDATE records SET data=replace(data,'123','999') WHERE id=?",(record['id'],))
        with self.assertRaises(Invalid):self.call('run_inventory',{'id':job['id']})
        with connection(self.path) as db:
            db.execute("UPDATE records SET data=replace(data,'999','123') WHERE id=?",(record['id'],))
        with patch('mission_control.provider_reports.report_request',side_effect=OSError('secret detail')):
            result=self.call('run_inventory',{'id':job['id']})
        self.assertEqual(result['status'],'BLOCKED');self.assertNotIn('secret detail',json.dumps(result))

    def test_invalid_signature_never_starts_provider_request_or_falls_back(self):
        self.start();record=self.setup()['record'];job=self.queue(record)
        self.gateway.signer_callback=lambda raw:json.dumps({'ok':True,'value':{'signature':'bad'}}).encode()
        with patch('mission_control.provider_auth.CNG',side_effect=AssertionError('desktop fallback')):
            with patch('mission_control.provider_reports.report_request') as provider:
                result=self.call('run_inventory',{'id':job['id']})
        self.assertEqual(result['status'],'BLOCKED');provider.assert_not_called()

    def test_unknown_staged_put_cleanup_preserves_active_key(self):
        self.start();old=self.setup()['record'];old_key=next(iter(self.values))
        real=self.vault
        def uncertain_put(raw):
            body=json.loads(raw);result=real(raw)
            return b'{"ok":false,"value":null}' if body['action']=='put' else result
        self.gateway.vault_callback=uncertain_put
        with self.assertRaises(Invalid):self.setup(id=old['id'],version=1)
        self.gateway.vault_callback=real
        self.assertEqual(self.call('cleanup')['removed'],1)
        self.assertEqual(list(self.values),[old_key])
        self.assertEqual(self.call('view')['connections'][0]['version'],1)

    def test_inventory_to_selected_metrics_persists_typed_downloads_and_history(self):
        from mission_control.apple_segments import read_instance_segments
        self.start();record=self.setup()['record'];inventory=self.queue(record)
        with patch('mission_control.provider_reports.report_request',side_effect=copy.deepcopy(readiness_pages())):
            first=self.call('run_inventory',{'id':inventory['id']})
        self.assertEqual(first['result']['reports'][0]['id'],'report-1')
        job=self.queue_metrics(record)
        raw=('Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n'
             '2026-10-01\t123\tFirst-time download\t9\tUS\n').encode()
        compressed=gzip.compress(raw,mtime=0)
        values=copy.deepcopy(readiness_pages()+readiness_pages()+[{'data':[segment(compressed)],'links':{}}])
        def download(reader,store,report,instance):
            return read_instance_segments(reader,store,report,instance,downloader=lambda *args:compressed)
        with patch('mission_control.provider_reports.report_request',side_effect=values), \
             patch('mission_control.provider_reports.read_instance_segments',side_effect=download):
            done=self.call('run_metrics',{'id':job['id']})
        self.assertEqual(done['status'],'SUCCEEDED')
        self.assertEqual(done['result']['operation'],'analytics_metrics_latest')
        self.assertEqual(done['result']['observation_count'],1)
        with connection(self.path) as db:
            saved=db.execute('SELECT * FROM apple_metric_partitions WHERE app_id=?',('new-app',)).fetchone()
            self.assertEqual(saved['report_id'],'report-1');self.assertIn('First-time download',saved['data'])
        observed=self.call('metrics',{'id':job['id']})
        self.assertEqual(observed['partitions'][0]['instance']['rows'][0]['count'],9)
        self.assertEqual(observed['observations'][0]['count'],9)
        self.assertEqual(observed['observations'][0]['metric'],'download_events')
        self.assertEqual(observed['observations'][0]['date'],'2026-10-01')
        with self.assertRaises(Invalid):self.call('metrics',{'id':inventory['id']})
        exported=json.loads(self.runtime.report(self.session,'new-app'))
        row=next(row for row in exported['rows'] if row['metric']=='Apple partition 1, observation 1: download_events')
        self.assertEqual(row['observed'],'9');self.assertIn('event_date=2026-10-01',row['evidence'])
        self.assertIn('finality=UNKNOWN',row['evidence']);self.assertIn('source=',row['evidence'])
        serialized=json.dumps(exported)
        for private in (KEY,'issuer-1','KEY1',record['data']['credential_ref']):self.assertNotIn(private,serialized)
        history=self.call('history')['jobs'];self.assertEqual({row['id'] for row in history},{job['id'],inventory['id']})
        self.assertNotIn('X-Amz-Signature',json.dumps(history))
        with self.assertRaises(Invalid):self.call('run_inventory',{'id':job['id']})

    def test_metrics_wrong_report_foreign_app_and_empty_segments_store_nothing(self):
        self.start();record=self.setup()['record']
        for index, mutation in enumerate(('wrong_report','foreign_app','wrong_type','partial','empty_segments')):
            job=self.queue_metrics(record,'foreign' if mutation=='wrong_report' else 'report-1',f'metrics-{index}')
            values=copy.deepcopy(readiness_pages())
            if mutation=='foreign_app':values[0]['data']['id']='999'
            if mutation=='wrong_type':values[2]['data'][0]['attributes']['name']='App Store Discovery and Engagement Standard'
            if mutation=='partial':
                path='https://api.appstoreconnect.apple.com/v1/apps/123/analyticsReportRequests'
                request_page=values[1]; values=[values[0]]+[dict(data=request_page['data'],links={'next':path+'?cursor='+str(i)}) for i in range(3)]
            if mutation=='empty_segments':values+=copy.deepcopy(readiness_pages())+[{'data':[],'links':{}}]
            with patch('mission_control.provider_reports.report_request',side_effect=values):
                result=self.call('run_metrics',{'id':job['id']})
            self.assertEqual(result['status'],'BLOCKED')
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM apple_metric_partitions').fetchone()[0],0)

    def test_lock_after_segment_download_prevents_metric_commit(self):
        from mission_control.apple_segments import read_instance_segments
        self.start();record=self.setup()['record'];job=self.queue_metrics(record)
        raw=('Date\tApp Apple Identifier\tDownload Type\tCounts\tTerritory\n2026-10-01\t123\tFirst-time download\t9\tUS\n').encode()
        compressed=gzip.compress(raw,mtime=0)
        values=copy.deepcopy(readiness_pages()+readiness_pages()+[{'data':[segment(compressed)],'links':{}}])
        def receive(*args):
            self.generation=str(uuid4());return compressed
        def segments(reader,store,report,instance):
            return read_instance_segments(reader,store,report,instance,downloader=receive)
        with patch('mission_control.provider_reports.report_request',side_effect=values), \
             patch('mission_control.provider_reports.read_instance_segments',side_effect=segments):
            with self.assertRaises(PermissionError):self.call('run_metrics',{'id':job['id']})
        with connection(self.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM apple_metric_partitions').fetchone()[0],0)


if __name__=='__main__':unittest.main()
