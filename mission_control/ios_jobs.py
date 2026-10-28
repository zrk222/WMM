"""Native foreground job leases over the shared queue and pipeline processor.

Only local preparation executes here. Provider/media adapters have separate
execution contracts. iOS may suspend this host; no always-on claim is made.
"""
import json
import time
from .common import Invalid, canonical, digest, now
from .db import connection
from .ios_bridge import decode_document, encode_response


class NativeJobs:
    def __init__(self, service, identities, clock=time.time):
        self.service = service
        self.identities = identities
        self.clock = clock

    def call(self, session, app_id, action, payload):
        from .operation_authority import bound_owner, protected
        body = decode_document(payload)
        fields = {'queue': {'stage','request_key'}, 'run': {'id'}, 'monitor': set(), 'cancel': {'id'}}
        if action not in fields or not isinstance(body,dict) or set(body) != fields[action]:
            raise Invalid('Use an exact native job control')
        user = self.identities.fresh(session)
        envelope = dict(app_id=app_id,operation='native.jobs.'+action,input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                if action == 'queue':result = self.queue(app_id,user,body)
                elif action == 'run':result = self.run(app_id,user,body['id'])
                elif action == 'cancel':result = self.cancel(app_id,user,body['id'])
                else:
                    from .workflow_telemetry import monitor
                    result = monitor(self.service.store,app_id)
        return encode_response(result)

    def queue(self, app_id, user, body):
        from .worker import enqueue
        stage = body['stage']
        if type(stage) is not int or not 0 <= stage <= 12:
            raise Invalid('Choose all twelve stages or one stage from 1 through 12')
        app = self.service.store.app(app_id)
        data = dict(stage=stage,native_owner=user['principal'],native_runtime='IOS_LOCAL_V1',
                    manifest_version=app['version'],manifest_hash=digest(app['data']))
        return enqueue(self.service.store,app_id,'pipeline',data,body['request_key'])

    def owned(self, db, app_id, user, identity):
        row = db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
        if row is None:raise Invalid('Job does not belong to this app')
        data = json.loads(row['data'])
        if row['action'] != 'pipeline' or data.get('native_runtime') != 'IOS_LOCAL_V1' or data.get('native_owner') != user['principal']:
            raise PermissionError('Use this native owner\'s local preparation job')
        app = db.execute('SELECT version,data FROM apps WHERE id=?',(app_id,)).fetchone()
        if app['version'] != data['manifest_version'] or digest(json.loads(app['data'])) != data['manifest_hash']:
            raise Invalid('App setup changed; queue preparation for the current app')
        return row

    def run(self, app_id, user, identity):
        from .worker import json_job, process
        from .workflow_telemetry import append
        store = self.service.store
        with connection(store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.owned(db,app_id,user,identity)
            if row['status'] in ('SUCCEEDED','FAILED','CANCELLED'):return json_job(row)
            if row['status'] == 'RUNNING' and row['lease'] > self.clock():
                raise Invalid('Job still has a live lease; inspect progress before resuming')
            if row['attempts'] >= 3:
                db.execute("UPDATE jobs SET status='FAILED',lease=0,result=?,updated=? WHERE id=?",
                           (canonical(dict(error='Recovery attempt limit reached; review before queueing new work')),now(),identity))
                return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
            db.execute("UPDATE jobs SET status='RUNNING',attempts=attempts+1,lease=?,updated=? WHERE id=?",
                       (self.clock()+60,now(),identity))
            job = json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
            append(db,job,'STARTED')
        try:
            # Same shared processor and durable stage events as the desktop host.
            # No global claim/advance loop: never execute another app or job type.
            result = process(store,job)
            status = 'SUCCEEDED'
        except (PermissionError, Invalid):
            raise  # Lost authority retains lease/checkpoints for explicit recovery.
        except Exception:
            result = dict(error='Local preparation failed; inspect evidence before retrying')
            status = 'FAILED'
        with connection(store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current = self.owned(db,app_id,user,identity)
            if current['status'] != 'RUNNING' or current['attempts'] != job['attempts']:
                raise Invalid('Job was cancelled or its attempt changed')
            db.execute('UPDATE jobs SET status=?,result=?,lease=0,updated=? WHERE id=?',
                       (status,canonical(result),now(),identity))
            append(db,job,status)
            return json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())

    def cancel(self, app_id, user, identity):
        from .worker import json_job
        from .workflow_telemetry import append
        with connection(self.service.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.owned(db,app_id,user,identity)
            if row['status'] == 'CANCELLED':return json_job(row)
            if row['status'] not in ('QUEUED','RUNNING'):raise Invalid('Only active jobs can be cancelled')
            db.execute("UPDATE jobs SET status='CANCELLED',lease=0,updated=? WHERE id=?",(now(),identity))
            job = json_job(db.execute('SELECT * FROM jobs WHERE id=?',(identity,)).fetchone())
            append(db,job,'CANCELLED')
            return job
