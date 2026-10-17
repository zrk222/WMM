"""Actual isolated local lifecycle contracts; no real users or provider delivery."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import copy
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid, digest
from mission_control.store import Store
from mission_control.followup import Followup
from mission_control.followup_eligibility import calendar, eligibility
from mission_control.followup_policy import zone, validate
from mission_control.worker import Runner

AT = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=Store(self.root/'db.sqlite',seed=False)
        self.store.save_app('test-app',{'name':'Synthetic app','job':'Useful practice','audience':'Test','activation':'Saved practice','release':'1','locale':'en-US','currency':'USD'})
        self.at=AT;self.flow=Followup(self.store,lambda:self.at)

    def tearDown(self):
        self.temp.cleanup()

    def save(self,kind,value,identity=None,app='test-app'):
        row=next((r for r in self.flow.list(app)[kind] if r['id']==(identity or 'policy')),None)
        return self.flow.save(app,kind,{'id':identity,'manifest_version':self.store.app(app)['version'],'version':row['version'] if row else None,'data':value})

    def setup(self,identity='subject-a'):
        self.save('policy',{'enabled':True,'cadence':'After useful practice','prompt':'Ready for your optional checkpoint?'})
        self.save('subject',{'confirmed':True,'source':'Synthetic supplied consent receipt','granted_at':(AT-timedelta(days=1)).isoformat(),'expires_at':(AT+timedelta(days=30)).isoformat(),'timezone':'America/Toronto','quiet_start':'21:00','quiet_end':'09:00'},identity)
        self.task('task-a',identity)

    def task(self,identity,subject='subject-a'):
        return self.save('task',{'subject_id':subject,'action':'Review saved useful outcome','due_at':(AT-timedelta(hours=1)).isoformat(),'expires_at':(AT+timedelta(days=3)).isoformat(),'state':'OPEN'},identity)

    def prepare(self,identity='task-a'):
        return self.flow.prepare('test-app',{'id':identity,'manifest_version':self.store.app('test-app')['version'],'source_hash':self.flow.list('test-app')['eligibility'][identity].get('source_hash')})

    def test_setup_actual_handoff_and_no_effects(self):
        self.setup()
        with patch('socket.socket',side_effect=AssertionError('Network forbidden')):
            state=self.prepare();h=state['handoff'][0]
            self.assertEqual(self.flow.download('test-app',h['id'])['delivery'],'NOT_SENT')
        self.assertEqual(h['data']['delivery'],'MANUAL_HANDOFF_UNSENT')
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'ALREADY_PREPARED')
        self.assertFalse(self.store.records('test-app'))

    def test_consent_revoke_expire_and_missing_subject(self):
        self.setup();h=self.prepare()['handoff'][0];subject=self.flow.list('test-app')['subject'][0]['data']
        self.save('subject',{**subject,'confirmed':False},'subject-a')
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'CONSENT_UNAVAILABLE_OR_REVOKED')
        with self.assertRaises(Invalid):self.flow.download('test-app',h['id'])
        self.save('subject',{**subject,'expires_at':(AT-timedelta(hours=1)).isoformat()},'subject-a')
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'CONSENT_OUTSIDE_WINDOW')
        with self.assertRaises(Invalid):self.task('task-b','foreign-subject')

    def test_quiet_hours_boundaries_dst_and_travel(self):
        self.setup();subject=self.flow.list('test-app')['subject'][0]
        self.assertTrue(calendar(subject,datetime(2026,3,8,6,59,tzinfo=timezone.utc))[1])
        self.assertTrue(calendar(subject,datetime(2026,3,8,7,1,tzinfo=timezone.utc))[1])
        for hour in (5,6):self.assertTrue(calendar(subject,datetime(2026,11,1,hour,30,tzinfo=timezone.utc))[1])
        self.assertTrue(calendar(subject,datetime(2026,10,12,12,59,tzinfo=timezone.utc))[1])
        self.assertFalse(calendar(subject,datetime(2026,10,12,13,0,tzinfo=timezone.utc))[1])
        self.save('subject',{**subject['data'],'timezone':'Asia/Tokyo'},subject['id'])
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'QUIET_HOURS')
        self.save('subject',{**subject['data'],'quiet_start':'10:00','quiet_end':'12:00'},subject['id'])
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'QUIET_HOURS')

    def test_task_completion_cancellation_due_and_expiration(self):
        self.setup();value=self.flow.list('test-app')['task'][0]['data']
        for state in ('COMPLETED','CANCELLED'):
            self.save('task',{**value,'state':state},'task-a')
            self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],state)
        self.save('task',{**value,'due_at':(AT+timedelta(hours=1)).isoformat()},'task-a')
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'NOT_DUE')
        self.save('task',value,'task-a');self.at=AT+timedelta(days=4)
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-a']['status'],'CHECKPOINT_EXPIRED')

    def test_cap_across_tasks_and_next_day(self):
        self.setup();self.task('task-b');self.prepare()
        self.assertEqual(self.flow.list('test-app')['eligibility']['task-b']['status'],'DAILY_CAP')
        self.at=AT+timedelta(days=1);self.prepare('task-b')
        self.assertEqual(len(self.flow.list('test-app')['handoff']),2)

    def test_concurrent_reservation_is_atomic(self):
        self.setup();self.task('task-b')
        def attempt(identity):
            try:self.prepare(identity);return 'prepared'
            except Invalid:return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['task-a','task-b']))
        self.assertEqual(sorted(results),['blocked','prepared'])
        self.assertEqual(len(self.flow.list('test-app')['handoff']),1)

    def test_app_row_and_source_binding(self):
        self.setup();before=self.flow.list('test-app');h=self.prepare()['handoff'][0]
        app=self.store.app('test-app');self.store.save_app('test-app',{**app['data'],'release':'2'},app['version'])
        with self.assertRaises(Invalid):self.flow.download('test-app',h['id'])
        with self.assertRaises(Invalid):self.flow.save('test-app','policy',{'data':before['policy'][0]['data'],'version':1,'manifest_version':1})
        with self.assertRaises(Invalid):self.flow.save('test-app','policy',{'data':before['policy'][0]['data'],'version':1})
        self.save('policy',{**before['policy'][0]['data'],'prompt':'Revised neutral prompt'})
        with self.assertRaises(Invalid):self.flow.save('test-app','policy',{'data':before['policy'][0]['data'],'version':1,'manifest_version':2})
        with self.assertRaises(Invalid):self.flow.prepare('test-app',{'id':'task-a','manifest_version':2,'source_hash':before['eligibility']['task-a']['source_hash']})

    def test_foreign_inputs_and_download(self):
        self.setup();data=self.flow.list('test-app');self.store.save_app('other-app',{'name':'Other'})
        with self.assertRaises(Invalid):self.flow.prepare('other-app',{'id':'task-a','manifest_version':1,'source_hash':'x'})
        result=eligibility(self.store.app('other-app'),data['policy'][0],data['subject'][0],data['task'][0],[],AT)
        self.assertEqual(result['status'],'FOREIGN_SCOPE')
        h=self.prepare()['handoff'][0]
        with self.assertRaises(Invalid):self.flow.download('other-app',h['id'])

    def test_validation_closed_types_and_dates(self):
        self.setup();data=self.flow.list('test-app')['subject'][0]['data']
        for change in ({'confirmed':'true'},{'granted_at':(AT+timedelta(days=1)).isoformat()},{'timezone':'Mars/Invalid'},{'quiet_start':'25:00'},{'quiet_start':'09:00'},{'source':''},{'email':'private@example.com'},{'expires_at':data['granted_at']}):
            with self.subTest(change=change),self.assertRaises(Invalid):self.save('subject',{**data,**change},'subject-a')
        with self.assertRaises(Invalid):self.flow.save('test-app','handoff',{})
        with self.assertRaises(Invalid):self.save('policy',{'enabled':True,'cadence':'a','prompt':'x'*501})
        with self.assertRaises(Invalid):zone('')

    def test_restart_and_background_preparation(self):
        self.setup();flow=Followup(Store(self.store.path,seed=False),lambda:AT)
        flow.tick();flow.tick();self.assertEqual(len(flow.list('test-app')['handoff']),1)
        with patch('mission_control.worker.Followup',return_value=flow):
            runner=Runner(self.store);runner.poll();self.assertEqual(runner.health['status'],'RUNNING')

    def test_background_does_not_starve_later_due_tasks(self):
        self.setup();initial=self.flow.list('test-app')['task'][0]['data']
        for index in range(26):self.save('task',{**initial,'state':'COMPLETED'},'closed-'+str(index))
        self.flow.tick();self.assertEqual(len(self.flow.list('test-app')['handoff']),1)

    def test_portable_history_passive_reactivation_and_tamper(self):
        self.setup();self.prepare();export=self.store.export('test-app')
        target=Store(self.root/'restored.sqlite',seed=False);target.restore(export);restored=Followup(target,lambda:AT)
        restored.tick();state=restored.list('test-app');self.assertEqual(len(state['handoff']),1)
        self.assertEqual(state['eligibility']['task-a']['status'],'PREPARATION_DISABLED')
        with self.assertRaises(Invalid):restored.download('test-app',state['handoff'][0]['id'])
        for change in ('hash','scope','reference','duplicate'):
            bad=copy.deepcopy(export);rows=bad['payload']['followup']
            if change=='hash':rows['subject'][0]['hash']='x'
            if change=='scope':rows['subject'][0]['app_id']='other-app'
            if change=='reference':
                rows['task'][0]['data']['subject_id']='missing';rows['task'][0]['hash']=digest(rows['task'][0]['data'])
            if change=='duplicate':rows['policy'].append(rows['policy'][0])
            bad['sha256']=digest(bad['payload']);empty=Store(self.root/(change+'.sqlite'),seed=False)
            with self.assertRaises(Invalid):empty.restore(bad)
            self.assertFalse(empty.apps())
        legacy=copy.deepcopy(export);del legacy['payload']['followup'];legacy['sha256']=digest(legacy['payload'])
        old=Store(self.root/'old.sqlite',seed=False);old.restore(legacy);self.assertFalse(Followup(old).list('test-app')['task'])

    def test_readonly_disabled_and_performance(self):
        self.setup();data=self.flow.list('test-app');self.save('policy',{**data['policy'][0]['data'],'enabled':False})
        before=self.store.export('test-app')['sha256'];started=time.perf_counter()
        for _ in range(100):self.flow.list('test-app')
        self.assertLess(time.perf_counter()-started,5)
        self.flow.tick();self.assertEqual(self.store.export('test-app')['sha256'],before)

    def test_stale_hash_and_typed_checkpoint_validation(self):
        self.setup()
        with self.assertRaises(Invalid):self.flow.prepare('test-app',{'id':'task-a','manifest_version':1,'source_hash':'incorrect'})
        with self.assertRaises(Invalid):self.flow.prepare('missing',{'id':'task-a','manifest_version':1,'source_hash':'incorrect'})
        value=self.flow.list('test-app')['task'][0]['data']
        for change in ({'state':'SENT'},{'expires_at':value['due_at']}):
            with self.assertRaises(Invalid):self.save('task',{**value,**change},'task-a')
        with self.assertRaises(Invalid):validate('unknown',{},AT)
        with self.assertRaises(Invalid):self.save('policy',{'enabled':True,'cadence':'a','prompt':'b','unsupported':'c'})

    def test_restored_inputs_each_require_explicit_review(self):
        self.setup();snapshot=self.store.export('test-app');target=Store(self.root/'passive.sqlite',seed=False);target.restore(snapshot)
        flow=Followup(target,lambda:AT)
        for kind in ('policy','subject'):
            row=flow.list('test-app')[kind][0]
            flow.save('test-app',kind,{'id':row['id'],'data':row['data'],'version':row['version'],'manifest_version':1})
        self.assertEqual(flow.list('test-app')['eligibility']['task-a']['status'],'IMPORTED_CHECKPOINT_REQUIRES_REVIEW')
        row=flow.list('test-app')['task'][0];flow.save('test-app','task',{'id':row['id'],'data':row['data'],'version':1,'manifest_version':1})
        flow.tick();self.assertEqual(len(flow.list('test-app')['handoff']),1)

    def test_portable_metadata_and_handoff_validation(self):
        self.setup();self.prepare();original=self.store.export('test-app')
        def changed(kind,field,value):
            bad=copy.deepcopy(original);row=bad['payload']['followup'][kind][0];row[field]=value
            if field=='data':row['hash']=digest(value)
            bad['sha256']=digest(bad['payload']);return bad
        handoff=original['payload']['followup']['handoff'][0]['data']
        cases=[changed('policy','id','wrong'),changed('subject','version',0),changed('handoff','data',{**handoff,'delivery':'SENT'}),changed('handoff','data',{**handoff,'source_hash':'x'}),changed('handoff','data',{**handoff,'local_date':'bad'}),changed('handoff','data',{**handoff,'task_id':'missing'})]
        for index,bad in enumerate(cases):
            target=Store(self.root/('tamper-'+str(index)+'.sqlite'),seed=False)
            with self.assertRaises(Invalid):target.restore(bad)
            self.assertFalse(target.apps())
        from mission_control.followup_portable import restore_followup,validate_rows
        with self.assertRaises(Invalid):restore_followup(None,'test-app',{})
        with self.assertRaises(Invalid):validate_rows('test-app','subject',{})

    def test_failed_app_does_not_starve_another(self):
        self.setup();state=self.flow.list('test-app');self.store.save_app('other-app',{'name':'Other'})
        for kind in ('policy','subject','task'):
            row=state[kind][0];self.save(kind,row['data'],row['id'],app='other-app')
        original=self.flow.list
        def failing(app):
            if app=='test-app':raise Invalid('Synthetic failed app')
            return original(app)
        with patch.object(self.flow,'list',side_effect=failing),self.assertRaises(Invalid):self.flow.tick()
        self.assertEqual(len(original('other-app')['handoff']),1)


if __name__=='__main__':unittest.main()
