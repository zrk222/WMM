"""Derived read-only collection uses isolated data and synthetic provider responses."""
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from mission_control.campaign_inputs import CampaignInputs, build_plan
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.service import Service
from mission_control.store import Store
from mission_control.worker import jobs, run_once, transient_read_error
from mission_control.marketing_agent_manifest import authorize_read, operating_manifest
from mission_control.common import digest


class CampaignInputTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.store = Store(Path(self.folder.name)/'test.sqlite3')
        app = self.store.app('sample-one')
        self.store.save_app('sample-one', {**app['data'], 'store_app_id':'123', 'release':'test-release', 'locale':'en-US'}, app['version'])
        self.binding = self.store.save_record('sample-one', dict(kind='connection', title='Synthetic only',
            source='Synthetic test binding', data=dict(provider='app_store', env_ref='SYNTHETIC_TOKEN', store_app_id='123', account_id='0')))
        self.collector = CampaignInputs(self.store)

    def body(self, plan=None):
        plan = plan or self.collector.preview('sample-one')
        return {k:plan[k] for k in ('manifest_version', 'source_hash')}

    def test_preview_is_read_only_and_derives_fixed_sources(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('Preview cannot use network')):
            a = self.collector.preview('sample-one')
            b = self.collector.preview('sample-one')
        self.assertEqual(a,b)
        self.assertEqual([t['operation'] for t in a['tasks']], ['identity_inventory','reviews','subscription_catalog'])
        self.assertEqual(jobs(self.store,'sample-one'), [])
        self.assertFalse(a['external_writes'])
        self.assertEqual(a['spend_minor'],0)
        self.assertNotIn('SYNTHETIC_TOKEN',str(a))

    def test_atomic_replay_preserves_failed_and_cancelled_jobs(self):
        body = self.body()
        a = self.collector.start('sample-one',body)
        self.assertEqual(len(a['tasks']),3)
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='BLOCKED' WHERE id=?",(a['tasks'][0]['job']['id'],))
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE id=?",(a['tasks'][1]['job']['id'],))
        b = self.collector.start('sample-one',body)
        self.assertEqual(len(jobs(self.store,'sample-one')),3)
        self.assertEqual([t['job']['status'] for t in b['tasks']],['BLOCKED','CANCELLED','QUEUED'])

    def test_stale_extra_and_foreign_requests_rejected(self):
        body = self.body()
        for invalid in ({**body,'extra':True},{**body,'manifest_version':True},{**body,'source_hash':'foreign'}):
            with self.assertRaises(Invalid):self.collector.start('sample-one',invalid)
        with self.assertRaises(Invalid):self.collector.start('sample-two',body)
        app = self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'release':'changed'},app['version'])
        with self.assertRaises(Invalid):self.collector.start('sample-one',body)
        self.assertEqual(jobs(self.store,'sample-one'),[])

    def test_mismatched_disconnected_and_unsupported_sources_excluded(self):
        app = self.store.app('sample-one')
        for changes in ({'store_app_id':'999'},{'auth_mode':'disconnected'},{'provider':'unsupported'}):
            row = deepcopy(self.binding);row['data'].update(changes)
            plan = build_plan(app,[row],'fixed-hour')
            self.assertEqual(plan['tasks'],[])
            self.assertTrue(plan['excluded'])
        row = deepcopy(self.binding);row['app_id']='sample-two'
        with self.assertRaises(Invalid):build_plan(app,[row],'fixed-hour')

    def test_selected_release_requires_exact_saved_intent(self):
        app = deepcopy(self.store.app('sample-one'))
        selected = dict(connection_id=self.binding['id'],connection_version=self.binding['version'],
                        local_release=app['data']['release'],locale='en-US',version_id='version-123')
        app['data']['promotion_release']=selected
        plan=build_plan(app,[self.binding],'fixed-hour')
        self.assertEqual(plan['tasks'][-1]['data']['options']['version_id'],'version-123')
        selected['connection_version']+=1
        self.assertEqual(len(build_plan(app,[self.binding],'fixed-hour')['tasks']),3)

    def test_worker_reads_and_rejects_manifest_change_before_network(self):
        self.collector.start('sample-one',self.body())
        with patch('mission_control.worker.sync',return_value={'operation':'synthetic-identity','external_writes':False}) as read:
            self.assertTrue(run_once(self.store));self.assertEqual(read.call_count,1)
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'release':'changed'},app['version'])
        with patch('mission_control.worker.read_report',side_effect=AssertionError('Stale source must not read')) as read:
            self.assertTrue(run_once(self.store));read.assert_not_called()
        self.assertEqual(sum(j['status']=='BLOCKED' for j in jobs(self.store,'sample-one')),1)

    def test_rechecks_manifest_after_provider_response(self):
        self.collector.start('sample-one',self.body())
        def changed(*args):
            app=self.store.app('sample-one')
            self.store.save_app('sample-one',{**app['data'],'release':'changed'},app['version'])
            return {'operation':'synthetic-identity'}
        with patch('mission_control.worker.sync',side_effect=changed):run_once(self.store)
        row=next(j for j in jobs(self.store,'sample-one') if j['status']=='BLOCKED')
        self.assertNotIn('synthetic-identity',str(row['result']))

    def test_scope_cap_and_hourly_reuse_boundary(self):
        app=self.store.app('sample-one')
        rows=[{**self.binding,'id':str(n)} for n in range(10)]
        a=build_plan(app,rows,'hour-one');b=build_plan(app,rows,'hour-two')
        self.assertEqual(len(a['tasks']),12)
        self.assertTrue(a['excluded'])
        self.assertNotEqual(a['source_hash'],b['source_hash'])
        self.assertEqual(Service(self.store).workspace('sample-one')['preparation']['collection']['app_id'],'sample-one')

    def test_operating_manifest_rejects_tool_scope_and_policy_drift(self):
        app=self.store.app('sample-one');plan=self.collector.preview('sample-one')
        task=plan['tasks'][0]['data']
        authorize_read(app,self.binding['data'],task)
        for change in ({'agent_policy_sha256':'stale'}, {'options':{'operation':'publish'}}, {'shell':'anything'}):
            with self.assertRaises(Invalid):authorize_read(app,self.binding['data'],{**task,**change})
        policy=operating_manifest(app)
        self.assertEqual(policy['human_role'],'APPROVE_OR_EDIT')
        self.assertEqual(policy['supported_execution']['provider_writes'],[])
        self.assertEqual(policy['supported_execution']['spend_minor'],0)
        self.assertEqual(plan['policy_sha256'],digest(policy))

    def test_changed_operating_policy_blocks_actual_worker_read(self):
        self.collector.start('sample-one',self.body())
        # Lazy imports must not retain the temporary policy mock after this test.
        importlib.import_module('mission_control.sequence_plan')
        with patch('mission_control.marketing_agent_manifest.operating_manifest',return_value={'policy_version':'changed'}), \
             patch('mission_control.worker.sync',side_effect=AssertionError('Policy mismatch cannot read')) as read:
            run_once(self.store);read.assert_not_called()
        self.assertEqual(sum(j['status']=='BLOCKED' for j in jobs(self.store,'sample-one')),1)

    def test_transient_reads_back_off_resume_and_stop_at_manifest_limit(self):
        plan=self.collector.start('sample-one',self.body())
        identity=plan['tasks'][0]['job']['id']
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='CANCELLED' WHERE id<>?",(identity,))
        def unavailable(*args):
            raise Invalid('Synthetic read unavailable') from HTTPError('https://fixture.invalid',503,'busy',{},None)
        with patch('mission_control.worker.sync',side_effect=unavailable) as read:
            for attempt in (1,2,3):
                self.assertTrue(run_once(self.store))
                row=next(j for j in jobs(self.store,'sample-one') if j['id']==identity)
                self.assertEqual(row['attempts'],attempt)
                self.assertEqual(row['status'],'RUNNING' if attempt<3 else 'BLOCKED')
                self.assertFalse(run_once(self.store))
                if attempt<3:
                    with connection(self.store.path) as db:db.execute('UPDATE jobs SET lease=0 WHERE id=?',(identity,))
            self.assertEqual(read.call_count,3)

    def test_permission_and_validation_errors_never_trigger_automatic_retry(self):
        self.assertFalse(transient_read_error(HTTPError('https://fixture.invalid',403,'denied',{},None)))
        self.assertFalse(transient_read_error(Invalid('HTTP 503 in text is not transport evidence')))
        self.assertTrue(transient_read_error(TimeoutError()))
        self.collector.start('sample-one',self.body())
        with patch('mission_control.worker.sync',side_effect=HTTPError('https://fixture.invalid',403,'denied',{},None)):
            run_once(self.store)
        row=next(j for j in jobs(self.store,'sample-one') if j['attempts']==1)
        self.assertEqual(row['status'],'BLOCKED')

    def test_connection_rotation_and_conflicting_job_roll_back_collection(self):
        frozen=self.collector.preview('sample-one');body=self.body(frozen)
        row=self.binding
        self.store.save_record('sample-one',{**row,'data':{**row['data'],'account_id':'1'}})
        with patch.object(self.collector,'preview',return_value=frozen):
            with self.assertRaises(Invalid):self.collector.start('sample-one',body)
        self.assertEqual(jobs(self.store,'sample-one'),[])
        fresh=self.collector.preview('sample-one')
        from mission_control.worker import enqueue
        enqueue(self.store,'sample-one','sync',{'different':'input'},fresh['tasks'][1]['request_key'])
        with self.assertRaises(Invalid):self.collector.start('sample-one',self.body(fresh))
        self.assertEqual(len(jobs(self.store,'sample-one')),1)

    def test_read_manifest_rejects_foreign_binding_and_changed_release(self):
        app=self.store.app('sample-one');task=self.collector.preview('sample-one')['tasks'][0]['data']
        with self.assertRaises(Invalid):authorize_read(app,{**self.binding['data'],'store_app_id':'999'},task)
        with self.assertRaises(Invalid):authorize_read(app,self.binding['data'],{**task,'manifest_version':True})
        release={**task,'options':{'operation':'release_inventory','version_id':'not-selected'}}
        with self.assertRaises(Invalid):authorize_read(app,self.binding['data'],release)


if __name__=='__main__':unittest.main()
