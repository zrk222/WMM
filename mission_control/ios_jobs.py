"""Native foreground job leases over the shared queue and pipeline processor.

Only local preparation executes here. Provider/media adapters have separate
execution contracts. iOS may suspend this host; no always-on claim is made.
"""
import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from .common import Invalid, canonical, digest, now
from .db import connection
from .ios_bridge import decode_document, encode_response

PIPELINE_HOST = ContextVar('wmm_native_pipeline_host', default=None)


def source_hash(db, app_id):
    """Bind every current source row without exposing its contents in a job."""
    rows = [dict(row) for row in db.execute('SELECT * FROM records WHERE app_id=? ORDER BY id', (app_id,))]
    return digest(rows)


def require_native_sources(db, app_id):
    """Validate source records without assuming desktop credentials migrated."""
    for row in db.execute("SELECT data FROM records WHERE app_id=? AND kind='connection'", (app_id,)):
        if not isinstance(json.loads(row['data']), dict):
            raise Invalid('Connection metadata needs repair')


@contextmanager
def native_pipeline_context(service, identities, session):
    """Trusted host binding; no native owner or callback is accepted from JSON."""
    user = identities.fresh(session)
    value = dict(store=str(Path(service.store.path).resolve()), identities=identities,
                 session=session, user=user)
    token = PIPELINE_HOST.set(value)
    try:
        yield
    finally:
        PIPELINE_HOST.reset(token)


def queue_scoped_pipeline(service, envelope):
    """Translate only an admitted pipeline intent to native-owned durable work."""
    from .automation_execution import ACTIVE
    from .operation_authority import REQUEST
    from .operation_catalog import request_data
    context = PIPELINE_HOST.get()
    if context is None or context['store'] != str(Path(service.store.path).resolve()):
        raise PermissionError('Trusted native pipeline host is unavailable')
    request_data(envelope)
    if envelope['operation'] != 'pipeline.prepare' or ACTIVE.get() is None:
        raise PermissionError('Native pipeline requires standing scoped admission')
    bound = REQUEST.get()
    user = context['user']
    context['identities'].local(context['session'], user['principal'], user['session_generation'])
    with connection(service.store.path) as db:
        grant = db.execute('SELECT owner,app_id FROM agent_grants WHERE id=?', (bound['grant_id'],)).fetchone()
        if grant is None or grant['owner'] != user['principal'] or grant['app_id'] != envelope['app_id']:
            raise PermissionError('Standing pipeline must belong to this native owner')
    data = envelope['input']['data']
    if set(data) - {'stage'}:
        raise Invalid('Native pipeline accepts only a stage')
    stage = data.get('stage', 0)
    return NativeJobs(service, context['identities']).queue(envelope['app_id'], user,
        dict(stage=stage, request_key=envelope['input']['request_key']))


def cancel_scoped_pipeline(service, envelope):
    """Only this standing policy's native jobs can be cancelled by its agent."""
    from .automation_execution import ACTIVE, execution_row
    context = PIPELINE_HOST.get()
    if context is None or context['store'] != str(Path(service.store.path).resolve()):
        raise PermissionError('Trusted native pipeline host is unavailable')
    user = context['user']
    context['identities'].local(context['session'], user['principal'], user['session_generation'])
    with connection(service.store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        execution = execution_row(db, ACTIVE.get()['id'])
        row = db.execute('SELECT j.* FROM jobs j JOIN automation_job_scopes s ON s.job_id=j.id JOIN automation_executions e ON e.id=s.execution_id WHERE j.id=? AND j.app_id=? AND e.policy_id=?',
                         (envelope['resource_id'], envelope['app_id'], execution['policy_id'])).fetchone()
        if row is None:
            raise PermissionError('Standing agent may cancel only its own native job')
        data = json.loads(row['data'])
        if row['action'] != 'pipeline' or data.get('native_runtime') != 'IOS_LOCAL_V1' or data.get('native_owner') != user['principal']:
            raise PermissionError('Standing agent may cancel only its own native job')
        changed = db.execute("UPDATE jobs SET status='CANCELLED',lease=0,updated=? WHERE id=? AND status IN ('QUEUED','RUNNING')", (now(), row['id'])).rowcount
        if not changed:raise Invalid('This job cannot be cancelled; reload its current state')
        return dict(status='CANCELLED')


class NativeJobs:
    def __init__(self, service, identities, clock=time.time, vault_callback=None):
        self.service = service
        self.identities = identities
        self.clock = clock
        self.vault_callback = vault_callback

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
                elif action == 'run':result = self.run(app_id,user,body['id'],session)
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
        with connection(self.service.store.path) as db:
            require_native_sources(db, app_id)
            sources = source_hash(db, app_id)
        data = dict(stage=stage,native_owner=user['principal'],native_runtime='IOS_LOCAL_V1',
                    manifest_version=app['version'],manifest_hash=digest(app['data']), source_hash=sources)
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
        if data.get('source_hash') is not None and data['source_hash'] != source_hash(db, app_id):
            raise Invalid('Source evidence changed; queue preparation for current sources')
        require_native_sources(db, app_id)
        return row

    def run(self, app_id, user, identity, session):
        from .automation_execution import job_execution
        from .complete_automation import ACCESS_VERIFIER, checked_policy, utc
        from .worker import json_job, process
        from .workflow_telemetry import append
        store = self.service.store
        with connection(store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.owned(db,app_id,user,identity)
            scope = db.execute('SELECT e.policy_id FROM automation_job_scopes s JOIN automation_executions e ON e.id=s.execution_id WHERE s.job_id=?', (identity,)).fetchone()
            if scope:
                if ACCESS_VERIFIER.get() is None:raise PermissionError('Native standing verifier is unavailable')
                checked_policy(db, scope['policy_id'], utc())
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
            from .ios_connection_status import native_connection_status
            from .connection_setup import Connections
            with native_connection_status(self.service, self.identities, session, self.vault_callback):
                with job_execution(store,job):
                    result = process(store,job)
                    result['native_connection_status'] = Connections(store).statuses(app_id)
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
            if current['lease'] <= self.clock():
                raise PermissionError('Job lease expired; inspect and resume with current authority')
            if scope:
                from .automation_execution import check_job, execution_row
                execution_id = db.execute('SELECT execution_id FROM automation_job_scopes WHERE job_id=?', (identity,)).fetchone()
                if execution_id is None:raise PermissionError('Standing job scope is unavailable')
                execution = execution_row(db, execution_id['execution_id'])
                checked_policy(db, execution['policy_id'], utc())
                check_job(db, dict(job_id=identity, attempt=job['attempts']), execution)
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
