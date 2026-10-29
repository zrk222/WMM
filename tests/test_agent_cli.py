"""Real CLI subprocesses communicate with an isolated WMM server; no alternate DB path."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from datetime import datetime,timedelta,timezone
from mission_control.server import Server
from mission_control.store import Store
from tests.test_aso_validation import listing
from tests.test_ledger import cohort,event
from tests.test_subscription_variants import configuration


class AgentCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'cli.sqlite',seed=False)
        for app in ('sample-one','sample-two'):
            self.store.save_app(app,dict(name='Synthetic Café 東京',release='build-1',locale='en-US',currency='USD'))
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def cli(self,raw=None,command='call',origin=None):
        args=[sys.executable,'-m','mission_control.agent_cli',command]
        if command=='call':args+=['--origin',origin or self.origin]
        result=subprocess.run(args,input=raw or b'',capture_output=True,timeout=30)
        return result,json.loads(result.stdout or result.stderr)

    def call(self,operation,value=None,app='sample-one',**extra):
        return self.cli(json.dumps(dict(app_id=app,operation=operation,input=value or {},**extra)).encode())

    def test_catalog_subprocess_is_json_and_requires_no_server(self):
        result,value=self.cli(command='catalog')
        self.assertEqual(result.returncode,0)
        self.assertEqual(result.stderr,b'')
        self.assertEqual(value['schema'],'growth.operation-catalog.v1')
        self.assertFalse(value['full_agent_operation'])

    def test_cli_growth_save_and_unicode_history_readback(self):
        body=dict(id='cli-listing',manifest_version=1,kind='ASO_LISTING',data=dict(release='build-1',listing=listing()))
        result,saved=self.call('growth.save',body)
        self.assertEqual(result.returncode,0)
        result,rows=self.call('growth.history')
        self.assertEqual(rows['history'][0]['hash'],saved['hash'])
        result,workspace=self.call('workspace.read')
        self.assertEqual(workspace['app']['data']['name'],'Synthetic Café 東京')
        self.assertEqual(self.call('growth.history',app='sample-two')[1]['history'],[])

    def test_cli_cohort_events_and_measurement_use_existing_ledger(self):
        result,_=self.call('cohort.define',cohort())
        self.assertEqual(result.returncode,0)
        result,value=self.call('events.import',dict(cohort_id='pilot-1',events=[event('install','INSTALL')]))
        self.assertEqual(result.returncode,0)
        self.assertEqual(value['inserted'],1)
        result,value=self.call('measurement.read')
        self.assertEqual(result.returncode,0)
        self.assertEqual(value[0]['cohort']['cohort_id'],'pilot-1')

    def test_cli_consolidated_report_reuses_app_scope_and_unknown_measurements(self):
        result,value=self.call('report.read')
        self.assertEqual(result.returncode,0)
        self.assertEqual(value['appID'],'sample-one')
        self.assertIsNone(next(row['observed'] for row in value['rows'] if row['metric']=='App performance'))
        self.assertEqual(self.call('report.read',app='sample-two')[1]['appID'],'sample-two')

    def test_errors_are_json_nonzero_and_rejected_write_leaves_no_entry(self):
        for raw in (b'{',b'{"app_id":"sample-one","app_id":"sample-two"}',b'{"n":NaN}'):
            result,value=self.cli(raw)
            self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
            self.assertEqual(value['error']['code'],'INVALID_INPUT')
        result,value=self.call('human.approve')
        self.assertEqual(result.returncode,2)
        result,value=self.call('growth.save',dict(id='bad',manifest_version=99,kind='ASO_LISTING',data=dict(release='build-1',listing=listing())))
        self.assertEqual(result.returncode,3);self.assertEqual(value['error']['http_status'],400)
        self.assertEqual(self.call('growth.history')[1]['history'],[])
        self.assertEqual(list(Path(self.tmp.name).glob('*session*')),[])

    def test_cli_typed_experiment_register_evaluate_and_cancel_readback(self):
        stamp=datetime.now(timezone.utc).replace(microsecond=0)
        time=lambda days:(stamp+timedelta(days=days)).isoformat()
        arms={}
        for arm in ('control','treatment'):
            result,_=self.call('cohort.define',cohort(cohort_id=arm,starts_at=time(2),ends_at=time(3),matures_at=time(33)))
            self.assertEqual(result.returncode,0)
            config=configuration(arm)
            data=dict(release='build-1',platform='iOS',locale='en-US',result='PASS',sku=config['product_id'],currency='USD',price_minor=1000,restore_tested=True,trial_eligibility_tested=True,eligibility_status='ELIGIBLE',checked_at=time(-1),expires_at=time(60),subscription_configuration=config)
            result,record=self.call('billing.save',dict(id='billing-'+arm,manifest_version=1,kind='billing',title='Synthetic terms',source='Synthetic test receipt',data=data))
            self.assertEqual(result.returncode,0)
            arms[arm]=dict(variant_type='SUBSCRIPTION',cohort_id=arm,source_record_id=record['id'],configuration=config)
        plan=dict(manifest_version=1,name='CLI typed test',owner='Synthetic operator',hypothesis='Compare access methods',primary_metric='paid_conversion',baseline_rate=.1,minimum_detectable_effect=.1,treatment_allocation=.5,analysis_at=time(34),assignment_method='OBSERVATIONAL',assignment_source='Synthetic assignment receipt',guardrails=dict(min_retention_rate=.2,max_refund_fraction=.1,min_contribution_minor=0,max_acquisition_minor=5000),stop_rule='Stop for billing failure',rollback_plan='Restore prior terms',**arms)
        result,experiment=self.call('experiment.register',plan)
        self.assertEqual(result.returncode,0,experiment)
        self.assertEqual(experiment['data']['control']['variant_type'],'SUBSCRIPTION')
        # A planned experiment cannot be evaluated before its exposure observation.
        result,rejected=self.call('experiment.evaluate',resource_id=experiment['id'])
        self.assertEqual(result.returncode,3)
        self.assertEqual(rejected['error']['http_status'],400)
        with patch('mission_control.experiments.now',return_value=time(2)):
            result,observing=self.call('experiment.action',dict(operation='observe',version=1,source='Synthetic exposure observation',observed_at=time(2)),resource_id=experiment['id'])
        self.assertEqual(result.returncode,0,observing)
        with patch('mission_control.experiments.now',return_value=time(34)):
            result,assessment=self.call('experiment.evaluate',resource_id=experiment['id'])
        self.assertEqual(result.returncode,0,assessment)
        self.assertIn('result',assessment)
        current=self.call('workspace.read')[1]['experiments'][0]
        result,cancelled=self.call('experiment.action',dict(operation='cancel',version=current['version'],reason='Synthetic CLI lifecycle check'),resource_id=experiment['id'])
        self.assertEqual(result.returncode,0,cancelled)
        self.assertEqual(cancelled['status'],'CANCELLED')
        self.assertEqual(self.call('workspace.read')[1]['experiments'][0]['state'],'CANCELLED')
