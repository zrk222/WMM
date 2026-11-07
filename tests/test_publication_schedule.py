"""Schedules share the existing jobs queue and bind leased work to approval."""
from datetime import datetime,timedelta,timezone
import time,unittest
from mission_control.common import Invalid,now,uid
from mission_control.db import connection
from mission_control.publication_schedule import enqueue_approved,advance,check_job,disable_db,ready_job,finish_step
from tests import test_publication_authority as fixtures
APP=fixtures.APP


class PublicationScheduleTests(unittest.TestCase):
    setUp=fixtures.PublicationAuthorityTests.setUp
    call=fixtures.PublicationAuthorityTests.call
    prepare=fixtures.PublicationAuthorityTests.prepare
    activate=fixtures.PublicationAuthorityTests.activate
    def enqueue(self,identity):
        return self.call('publication.execute',{'id':identity},lambda:enqueue_approved(self.store,APP,identity))

    def test_future_due_never_queues_early_and_then_queues_once(self):
        item=self.prepare(); due=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
        self.activate(item,due_at=due); scheduled=self.enqueue(item['id'])
        self.assertEqual(scheduled['status'],'READY')
        self.assertEqual(self.enqueue(item['id'])['id'],scheduled['id'])
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); self.assertEqual(advance(db,self.store),0)
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)
        from unittest.mock import patch
        with patch('mission_control.publication_schedule.time.time',return_value=time.time()+61):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE'); self.assertEqual(advance(db,self.store),1)
                self.assertEqual(advance(db,self.store),0)
                self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_job_fences_lease_and_revocation(self):
        item=self.prepare(); approval=self.activate(item); scheduled=self.enqueue(item['id'])
        with connection(self.store.path) as db:
            job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(scheduled['job_id'],)).fetchone())
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?",(time.time()+60,job['id']))
            import json
            job['data']=json.loads(job['data']); job['attempts']=1
            owner=check_job(db,self.store,job)
        self.assertEqual(owner,'github:1')
        with connection(self.store.path) as db:
            with self.assertRaises(PermissionError):check_job(db,self.store,{**job,'attempts':2})
            with self.assertRaises(PermissionError):check_job(db,self.store,{**job,'data':{'publication_id':uid()}})
            db.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()-1,job['id']))
            with self.assertRaises(PermissionError):check_job(db,self.store,job)
            db.execute('UPDATE jobs SET lease=? WHERE id=?',(time.time()+60,job['id']))
        self.call('publication.revoke',{'id':item['id'],'version':approval['version']},lambda:self.svc.revoke(APP,item['id'],approval['version']))
        with connection(self.store.path) as db:
            with self.assertRaises((Invalid,PermissionError)):check_job(db,self.store,job)

    def test_disabled_schedule_never_dispatches(self):
        item=self.prepare(); due=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(); self.activate(item,due_at=due)
        self.enqueue(item['id'])
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); disable_db(db,APP,item['id'])
        from unittest.mock import patch
        with patch('mission_control.publication_schedule.time.time',return_value=time.time()+61):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE'); self.assertEqual(advance(db,self.store),0)

    def test_expired_or_changed_authority_blocks_due_job(self):
        item=self.prepare(); due=(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat()
        self.activate(item,due_at=due); scheduled=self.enqueue(item['id'])
        with connection(self.store.path) as db:
            db.execute('UPDATE social_connections SET version=version+1 WHERE id=?',(self.connection,))
        from unittest.mock import patch
        with patch('mission_control.publication_schedule.time.time',return_value=time.time()+61):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE'); self.assertEqual(advance(db,self.store),0)
                self.assertEqual(db.execute('SELECT status FROM publication_schedules WHERE id=?',(scheduled['id'],)).fetchone()[0],'BLOCKED')
                self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_due_after_approval_expires_is_blocked(self):
        item=self.prepare(); clock=datetime.now(timezone.utc)
        self.activate(item,due_at=(clock+timedelta(seconds=60)).isoformat(),expires_at=(clock+timedelta(seconds=120)).isoformat())
        scheduled=self.enqueue(item['id'])
        from unittest.mock import patch
        with patch('mission_control.publication_schedule.time.time',return_value=time.time()+121):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE'); self.assertEqual(advance(db,self.store),0)
                self.assertEqual(db.execute('SELECT status FROM publication_schedules WHERE id=?',(scheduled['id'],)).fetchone()[0],'BLOCKED')
                self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def leased(self):
        import json
        from mission_control.publication_execution import initialize
        initialize(self.store)
        item=self.prepare(); self.activate(item,expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()); schedule=self.enqueue(item['id'])
        with connection(self.store.path) as db:
            db.execute("UPDATE jobs SET status='RUNNING',attempts=1,lease=? WHERE id=?",(time.time()+60,schedule['job_id']))
            row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(schedule['job_id'],)).fetchone())
        row['data']=json.loads(row['data'])
        return item,schedule,row

    def receipt(self,db,job,status,attention=False):
        from mission_control.publication_authority import current
        from mission_control import publication_execution as ex
        value=current(db,self.store,APP,job['data']['publication_id'],owner='github:1')
        row,state=ex._ensure(db,APP,value)
        paths={'UPLOADED':['CREATED','UPLOADED'], 'PROCESSING':['CREATED','UPLOADED','PROCESSING'],
               'PUBLISHED':['READY_TO_PUBLISH','PUBLISH_ACKNOWLEDGED','PUBLISHED'], 'UNKNOWN':['UNKNOWN']}
        route=['PROCESSING'] if state['status']=='UPLOADED' and status=='PROCESSING' else [] if state['status']==status else paths[status]
        for phase in route:
            full=dict(status=phase,remote_id='urn:li:share:123' if phase in ('PUBLISH_ACKNOWLEDGED','PUBLISHED') else None,
                      asset_id=None,session=None,observation={'public_visibility':'NOT_VERIFIED'})
            row=ex._save(db,row,full,None,'read' if phase=='PUBLISHED' else 'fixture',job['attempts'])
        if attention:row=ex._hold(db,row,'READ_UNAVAILABLE',job['attempts'])
        return ex._view(db,row)

    def test_known_step_requeues_same_job_after_due_and_keeps_attempts(self):
        item,schedule,job=self.leased(); due=time.time()+60
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); finish_step(db,self.store,job,self.receipt(db,job,'UPLOADED'),due)
            row=dict(db.execute('SELECT * FROM jobs WHERE id=?',(job['id'],)).fetchone())
            self.assertEqual((row['id'],row['status'],row['attempts']),(job['id'],'QUEUED',1))
            self.assertFalse(ready_job(db,row))
        from unittest.mock import patch
        with patch('mission_control.publication_schedule.time.time',return_value=due+1):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE'); self.assertTrue(ready_job(db,row))
                db.execute("UPDATE jobs SET status='RUNNING',attempts=2,lease=? WHERE id=?",(due+61,job['id']))
                finish_step(db,self.store,{**job,'attempts':2},self.receipt(db,job,'PROCESSING'),due+10)
                saved=db.execute('SELECT id,status,attempts FROM jobs WHERE id=?',(job['id'],)).fetchone()
                self.assertEqual(tuple(saved),(job['id'],'QUEUED',2))

    def test_stale_lease_off_and_unknown_never_requeue(self):
        item,schedule,job=self.leased()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(PermissionError):finish_step(db,self.store,{**job,'attempts':2},self.receipt(db,job,'UPLOADED'),time.time()+5)
            finish_step(db,self.store,job,self.receipt(db,job,'UNKNOWN'),time.time()+5)
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'BLOCKED')
        self.draft={**self.draft,'request_id':uid()}
        item,schedule,job=self.leased()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); disable_db(db,APP,item['id'])
            finish_step(db,self.store,job,self.receipt(db,job,'UPLOADED'),time.time()+5)
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'CANCELLED')

    def test_terminal_published_succeeds_and_invalid_next_time_blocks(self):
        item,schedule,job=self.leased()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            for _ in range(3):db.execute('UPDATE publication_authorities SET calls_used=calls_used+1 WHERE id=?',(item['id'],))
            finish_step(db,self.store,job,self.receipt(db,job,'PUBLISHED'),None)
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'SUCCEEDED')
            self.assertEqual(db.execute('SELECT status FROM publication_schedules WHERE id=?',(schedule['id'],)).fetchone()[0],'COMPLETE')
        self.draft={**self.draft,'request_id':uid()}; item,schedule,job=self.leased()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); finish_step(db,self.store,job,self.receipt(db,job,'PROCESSING'),float('inf'))
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'BLOCKED')

    def test_published_monitor_continues_same_job_and_attention_halts(self):
        item,schedule,job=self.leased(); due=time.time()+20
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); finish_step(db,self.store,job,{**self.receipt(db,job,'PUBLISHED'),'monitoring':True},due)
            saved=db.execute('SELECT id,status,attempts FROM jobs WHERE id=?',(job['id'],)).fetchone()
            self.assertEqual(tuple(saved),(job['id'],'QUEUED',1))
            due=db.execute('SELECT next_due FROM publication_schedules WHERE id=?',(schedule['id'],)).fetchone()[0]
        from unittest.mock import patch
        with patch('mission_control.publication_schedule.time.time',return_value=due+1):
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE'); db.execute("UPDATE jobs SET status='RUNNING',attempts=2,lease=? WHERE id=?",(due+60,job['id']))
                finish_step(db,self.store,{**job,'attempts':2},{**self.receipt(db,job,'PUBLISHED',True),'monitoring':True},due+10)
                self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0],'BLOCKED')
