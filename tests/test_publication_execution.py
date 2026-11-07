"""Real authority/SQLite phases; only provider calls and native vault are fixtures."""
import json,time,unittest
from unittest.mock import patch
from types import SimpleNamespace
from mission_control.common import Invalid,canonical
from mission_control.db import connection
from mission_control import publication_execution as execution
from mission_control.publication_schedule import enqueue_approved,disable_db,finish_step
from tests import test_publication_authority as fixtures

APP=fixtures.APP

class Vault:
    def __init__(self):self.values={}
    def get(self,key):return self.values.get(key)
    def put(self,key,value):
        assert len(canonical(value).encode())<=2560
        self.values[key]=value
    def delete(self,key):self.values.pop(key,None)

class PublicationExecutionTests(unittest.TestCase):
    setUp=fixtures.PublicationAuthorityTests.setUp
    call=fixtures.PublicationAuthorityTests.call
    prepare=fixtures.PublicationAuthorityTests.prepare
    activate=fixtures.PublicationAuthorityTests.activate

    def leased(self,max_calls=40):
        execution.initialize(self.store)
        from datetime import datetime,timedelta,timezone
        item=self.prepare();self.activate(item,max_calls=max_calls,expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat())
        schedule=self.call('publication.execute',{'id':item['id']},lambda:enqueue_approved(self.store,APP,item['id']))
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?",(time.time()+60,schedule['job_id']))
            job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(schedule['job_id'],)).fetchone())
        job['data']=json.loads(job['data'])
        return item,job

    def context(self,store,app,draft,before,heartbeat):
        before();heartbeat()
        return SimpleNamespace(before_call=before,heartbeat=heartbeat)

    def state(self,status,remote=None):
        return dict(status=status,remote_id=remote,asset_id=None,session=None,observation={'public_visibility':'NOT_VERIFIED'})

    def run_step(self,job,adapter):
        with patch('mission_control.publication_credentials.context',side_effect=self.context):
            return execution.process_job(self.store,job,{'linkedin':adapter})

    def test_bare_published_cannot_complete_schedule(self):
        item,job=self.leased()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(Invalid):finish_step(db,self.store,job,{'status':'PUBLISHED'},None)
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'RUNNING')

    def test_off_between_setup_and_transport_blocks_outbound(self):
        item,job=self.leased();sent=[]
        def create(draft,artifact,ctx):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE');disable_db(db,APP,item['id'])
            ctx.before_call();sent.append(True)
            return self.state('READY_TO_PUBLISH')
        result=self.run_step(job,SimpleNamespace(create=create))
        self.assertEqual(sent,[]);self.assertTrue(result.result['requires_attention'])

    def test_charge_commits_before_effect_and_uncertain_effect_never_replays(self):
        item,job=self.leased();sent=[]
        def create(draft,artifact,ctx):return self.state('READY_TO_PUBLISH')
        first=self.run_step(job,SimpleNamespace(create=create))
        self.assertEqual(first.result['status'],'READY_TO_PUBLISH')
        def publish(draft,state,ctx):
            ctx.before_call()
            with connection(self.store.path) as db:
                sent.append(db.execute('SELECT calls_used FROM publication_authorities WHERE id=?',(item['id'],)).fetchone()[0])
            raise ConnectionError('Lost response with private token')
        held=self.run_step(job,SimpleNamespace(publish=publish))
        self.assertEqual(held.result['status'],'UNKNOWN');self.assertEqual(sent,[3])
        self.assertNotIn('private token',canonical(held.result))
        self.run_step(job,SimpleNamespace(publish=publish))
        self.assertEqual(sent,[3])

    def test_phase_regression_is_held_and_never_published(self):
        item,job=self.leased()
        self.run_step(job,SimpleNamespace(create=lambda *args:self.state('READY_TO_PUBLISH')))
        held=self.run_step(job,SimpleNamespace(publish=lambda *args:self.state('CREATED')))
        self.assertEqual(held.result['status'],'UNKNOWN')
        with connection(self.store.path) as db:
            self.assertEqual(execution._row(db,APP,item['id'])[1]['status'],'READY_TO_PUBLISH')

    def test_published_requires_read_receipt_and_monitoring_only_reads(self):
        item,job=self.leased();events=[]
        def publish(draft,state,ctx):ctx.before_call();events.append('publish');return self.state('PUBLISH_ACKNOWLEDGED','urn:li:share:123')
        def read(draft,state,ctx):ctx.before_call();events.append('read');return self.state('PUBLISHED','urn:li:share:123')
        adapter=SimpleNamespace(create=lambda *args:self.state('READY_TO_PUBLISH'),publish=publish,read=read)
        self.run_step(job,adapter);ack=self.run_step(job,adapter)
        self.assertEqual(ack.result['status'],'PUBLISH_ACKNOWLEDGED')
        published=self.run_step(job,adapter)
        self.assertTrue(published.result['monitoring'])
        self.run_step(job,adapter)
        self.assertEqual(events,['publish','read','read'])
        self.assertEqual(published.result['observation']['public_visibility'],'NOT_VERIFIED')
        with connection(self.store.path) as db:
            with self.assertRaises(Invalid):execution.verified_result(db,APP,item['id'],ack.result)

    def test_sealed_response_survives_crash_before_db_commit(self):
        item,job=self.leased();real_save=execution._save
        class Crash(BaseException):pass
        with patch('mission_control.publication_credentials.context',side_effect=self.context),patch.object(execution,'_save',side_effect=Crash):
            with self.assertRaises(Crash):execution.process_job(self.store,job,{'linkedin':SimpleNamespace(create=lambda *args:self.state('READY_TO_PUBLISH'))})
        with connection(self.store.path) as db:
            row,state=execution._row(db,APP,item['id']);self.assertEqual(row['status'],'NEW');self.assertIsNotNone(row['pending'])
            db.execute("UPDATE jobs SET status='BLOCKED',lease=0 WHERE id=?",(job['id'],))
        recovered=self.call('publication.reconcile',{'id':item['id']},lambda:execution.reconcile(self.store,APP,item['id']))
        self.assertEqual(recovered['status'],'READY_TO_PUBLISH')

    def test_concurrent_execution_cannot_send_the_same_phase_twice(self):
        import threading
        from mission_control.campaign_locks import CampaignLockBusy
        item,job=self.leased();entered=threading.Event();release=threading.Event();errors=[];sent=[]
        def create(draft,artifact,ctx):
            ctx.before_call();sent.append('create');entered.set()
            if not release.wait(5):raise TimeoutError('fixture wait')
            return self.state('READY_TO_PUBLISH')
        adapter=SimpleNamespace(create=create)
        def first():
            try:execution.process_job(self.store,job,{'linkedin':adapter})
            except BaseException as exc:errors.append(exc)
        with patch('mission_control.publication_credentials.context',side_effect=self.context):
            thread=threading.Thread(target=first);thread.start()
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(CampaignLockBusy):execution.process_job(self.store,job,{'linkedin':adapter})
            finally:release.set();thread.join(5)
        self.assertFalse(thread.is_alive());self.assertEqual(errors,[]);self.assertEqual(sent,['create'])

    def test_revocation_during_admitted_publish_retains_receipt_but_stops_continuation(self):
        item,job=self.leased()
        self.run_step(job,SimpleNamespace(create=lambda *args:self.state('READY_TO_PUBLISH')))
        def publish(draft,state,ctx):
            ctx.before_call()
            with connection(self.store.path) as db:version=db.execute('SELECT version FROM publication_authorities WHERE id=?',(item['id'],)).fetchone()[0]
            self.call('publication.revoke',{'id':item['id'],'version':version},lambda:self.svc.revoke(APP,item['id'],version))
            return self.state('PUBLISH_ACKNOWLEDGED','urn:li:share:123')
        result=self.run_step(job,SimpleNamespace(publish=publish))
        self.assertEqual(result.result['remote_id'],'urn:li:share:123');self.assertIsNone(result.reschedule_at)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');outcome=finish_step(db,self.store,job,result.result,None)
            self.assertEqual(outcome['job_status'],'CANCELLED')

    def test_owner_recovery_cannot_reset_the_total_call_allowance(self):
        item,job=self.leased(max_calls=5)
        self.run_step(job,SimpleNamespace(create=lambda *args:self.state('READY_TO_PUBLISH')))
        def publish(draft,state,ctx):ctx.before_call();return self.state('PUBLISH_ACKNOWLEDGED','urn:li:share:123')
        self.run_step(job,SimpleNamespace(publish=publish))
        with connection(self.store.path) as db:db.execute("UPDATE jobs SET status='BLOCKED',lease=0 WHERE id=?",(job['id'],))
        reads=[]
        def read(draft,state,ctx):ctx.before_call();reads.append(True);return self.state('PUBLISHED','urn:li:share:123')
        def recover():return self.call('publication.reconcile',{'id':item['id']},lambda:execution.reconcile(self.store,APP,item['id']))
        with patch('mission_control.publication_credentials.context',side_effect=self.context),patch('mission_control.publication_linkedin.read',side_effect=read):
            self.assertEqual(recover()['status'],'PUBLISHED')
            with self.assertRaises(PermissionError):recover()
        self.assertEqual(reads,[True])
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT calls_used FROM publication_authorities WHERE id=?',(item['id'],)).fetchone()[0],5)

    def test_forged_monitoring_flag_cannot_requeue_with_exhausted_allowance(self):
        item,job=self.leased(max_calls=5)
        self.run_step(job,SimpleNamespace(create=lambda *args:self.state('READY_TO_PUBLISH')))
        self.run_step(job,SimpleNamespace(publish=lambda d,s,c:self.state('PUBLISH_ACKNOWLEDGED','urn:li:share:123')))
        result=self.run_step(job,SimpleNamespace(read=lambda d,s,c:self.state('PUBLISHED','urn:li:share:123')))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            while db.execute('SELECT calls_used<max_calls FROM publication_authorities WHERE id=?',(item['id'],)).fetchone()[0]:
                db.execute('UPDATE publication_authorities SET calls_used=calls_used+1 WHERE id=?',(item['id'],))
            finished=finish_step(db,self.store,job,{**result.result,'monitoring':True},time.time()+10)
            self.assertEqual(finished['job_status'],'SUCCEEDED')
            saved=json.loads(db.execute('SELECT result FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
            self.assertFalse(saved['monitoring'])

    def test_provider_read_can_confirm_progress_after_a_lost_phase_response(self):
        item,job=self.leased()
        created=self.state('CREATED');created['asset_id']='provider-asset'
        self.run_step(job,SimpleNamespace(create=lambda *args:created))
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='BLOCKED',lease=0 WHERE id=?",(job['id'],))
        def read(draft,state,ctx):
            self.assertEqual(state['asset_id'],'provider-asset');ctx.before_call()
            return {**self.state('PUBLISHED','urn:li:share:123'),'asset_id':'provider-asset'}
        with patch('mission_control.publication_credentials.context',side_effect=self.context),patch('mission_control.publication_linkedin.read',side_effect=read):
            recovered=self.call('publication.reconcile',{'id':item['id']},lambda:execution.reconcile(self.store,APP,item['id']))
        self.assertEqual(recovered['status'],'PUBLISHED')
        self.assertFalse(execution._advance_allowed('PUBLISHED','CREATED','read'))
        self.assertFalse(execution._advance_allowed('CREATED','PUBLISHED','publish'))

    def setUp(self):
        fixtures.PublicationAuthorityTests.setUp(self)
        self.vault=Vault();self.patch=patch('mission_control.publication_sessions.Vault',return_value=self.vault)
        self.patch.start();self.addCleanup(self.patch.stop)
