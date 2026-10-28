"""Source-bound approved inference; draft text has no publication authority."""
import time,uuid
from datetime import timedelta
from .common import Invalid,canonical,digest,now,iso_time,uid
from .db import connection
from .agent_access import AgentAccess
from .agent_registry import REGISTRY,TASKS,NATIVE
from .agent_contract import exact,prompt,bounded_text,draft
from .agent_native import run as native_run
from .agent_api import request as api_run
from .worker import json_job
from .agent_context import snapshot
from .agent_usage import observation as usage_observation

SCHEMA='growth.agent-draft-job.v2'


def request_key(value):
    """Require canonical identities, never command fragments."""
    try:
        if str(uuid.UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise Invalid('Use a canonical agent request identity') from None
    return value


def selected(store,app_id,task,connection_id):
    """Select an app-owned route without a hidden paid-provider fallback."""
    access=AgentAccess(store);view=access.view(app_id);mode=view['routing']['data']['mode']
    chosen=connection_id or view['routing']['data']['routes'].get(task)
    if not chosen:
        rows=[p for p in view['profiles'] if permitted(p,mode)]
        if not rows:raise Invalid('Test an agent connection in this access mode, or approve another route')
        chosen=rows[0]['id']
    row=access.get(app_id,chosen)
    if row['status']=='DISCONNECTED':raise Invalid('This app connection is disconnected')
    if task!='connection_test':
        if row['status']!='TESTED':raise Invalid('Test this connection before approving campaign work')
        if mode!='mixed' and REGISTRY[row['data']['provider']]['mode']!=mode:raise Invalid('Connection is outside this app access mode')
    return row,view['routing']


def permitted(row,mode):
    """An automatic recommendation is limited to tested providers in the chosen mode."""
    return row['status']=='TESTED' and (mode=='mixed' or REGISTRY[row['data']['provider']]['mode']==mode)


def proposal(store,app_id,body):
    """Derive the exact reviewed app-fact transmission rather than accept a prompt."""
    exact(body,('task','focus','connection_id'));task=body['task']
    if not isinstance(task,str) or (task not in TASKS and task!='connection_test'):raise Invalid('Choose a supported agent task')
    bounded_text(body['focus'],'Task focus',1000)
    if body['connection_id'] is not None:request_key(body['connection_id'])
    app=store.app(app_id);row,routing=selected(store,app_id,task,body['connection_id'])
    context=snapshot(store,app_id) if task!='connection_test' else None
    text=prompt(app,task,body['focus'],context) if task!='connection_test' else (
        'Return only this JSON, without tools: '+canonical(dict(summary='Connection test completed',items=[],unknowns=['Quota and price are not independently verified'])))
    frozen=dict(schema=SCHEMA,app_id=app_id,app_version=app['version'],app_hash=digest(app['data']),
        connection_id=row['id'],connection_version=row['version'],connection_hash=digest(row['data']),
        routing_hash=digest(routing),task=task,focus=body['focus'],prompt=text,provider=row['data']['provider'],
        model=row['data']['model'],max_output_tokens=256 if task=='connection_test' else 2048,
        external_effect='MODEL_REQUEST_ONLY_NO_PUBLICATION',fallback='REQUIRES_ANOTHER_APPROVAL')
    frozen.update(context=context,context_hash=digest(context),
                  source_ids=[s['id'] for s in context['sources']] if context else [])
    return dict(proposal=frozen,source_hash=digest(frozen),cost='Existing provider allowance or approved API charges; exact cost/quota unknown',
        recommendation='Selected app-owned route; comparative quality and cost are not yet measured',automatically_verified=False)


class AgentWork:
    def __init__(self,store,on_start=None):self.store=store;self.on_start=on_start

    def start(self,app_id,body):
        """Freeze one exact app/connection approval and idempotent durable job."""
        exact(body,('task','focus','connection_id','source_hash','request_key'))
        key='agent-'+request_key(body['request_key']);self.store.app(app_id)
        with connection(self.store.path) as db:
            old=db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',(app_id,key)).fetchone()
        if old:return replay(old,body)
        current=proposal(self.store,app_id,{k:body[k] for k in ('task','focus','connection_id')})
        if current['source_hash']!=body['source_hash']:raise Invalid('App, route or connection changed; review a new proposal')
        frozen=current['proposal'];frozen['expires_at']=(iso_time(now())+timedelta(seconds=1800)).isoformat()
        data=dict(envelope=frozen,envelope_hash=digest(frozen),original_request=body)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',(app_id,key)).fetchone()
            if old:return replay(old,body)
            guard(self.store,app_id,frozen)
            if db.execute("SELECT 1 FROM jobs WHERE app_id=? AND action='agent_run' AND status IN ('QUEUED','RUNNING')",(app_id,)).fetchone():
                raise Invalid('Finish or cancel this app current agent work before approving another request')
            db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                (uid(),app_id,'agent_run',canonical(data),'QUEUED',now(),now(),key))
            job=json_job(db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',(app_id,key)).fetchone())
            if self.on_start is not None:self.on_start(db,job)
            return job


def replay(row,body):
    """A repeated request reads its original receipt instead of repeating inference."""
    saved=json_job(row)
    if saved['action']!='agent_run' or saved['data']['original_request']!=body:raise Invalid('Agent request identity was reused for different work')
    return saved


def guard(store,app_id,frozen):
    """Reject changed sources, routes, access or approval expiry before and after IO."""
    app=store.app(app_id)
    if frozen['schema']!=SCHEMA or frozen['app_id']!=app_id or frozen['app_version']!=app['version'] or frozen['app_hash']!=digest(app['data']):
        raise Invalid('Agent app facts changed; approve the current task')
    if iso_time(now())>iso_time(frozen['expires_at']):raise Invalid('Agent task approval expired')
    guard_context(store,app_id,frozen)
    row,routing=selected(store,app_id,frozen['task'],frozen['connection_id'])
    if row['version']!=frozen['connection_version'] or digest(row['data'])!=frozen['connection_hash'] or digest(routing)!=frozen['routing_hash']:
        raise Invalid('Agent route or connection changed; approve a new task')
    return row


def guard_context(store,app_id,frozen):
    """Rebuild bounded campaign sources without consulting protected credentials."""
    current=snapshot(store,app_id) if frozen['task']!='connection_test' else None
    if frozen.get('context')!=current or frozen.get('context_hash')!=digest(current):
        raise Invalid('Agent evidence changed or approved context is absent; review a new proposal')
    expected=[s['id'] for s in current['sources']] if current else []
    if frozen.get('source_ids')!=expected:raise Invalid('Approved agent source index changed')


def live_guard(store,job,stop=None):
    """Maintain only the current owned lease and stop cancelled native work."""
    last=[0]
    def alive():
        if stop is not None and stop.is_set():raise Invalid('Agent worker is stopping; review before another inference')
        if time.monotonic()-last[0]<.25:return
        last[0]=time.monotonic()
        with connection(store.path) as db:
            row=db.execute('SELECT status,attempts FROM jobs WHERE app_id=? AND id=?',(job['app_id'],job['id'])).fetchone()
            if row is None or row['status']!='RUNNING' or row['attempts']!=job['attempts']:raise Invalid('Agent job was cancelled or its lease changed')
            db.execute('UPDATE jobs SET lease=? WHERE id=? AND attempts=?',(time.time()+60,job['id'],job['attempts']))
        guard(store,job['app_id'],job['data']['envelope'])
    return alive


def execute(store,job,stop=None,access=None,transport=None):
    """Interrupted inference is not replayed because allowance may already be consumed."""
    if job['attempts']!=1:raise Invalid('Interrupted inference may have consumed allowance; approve a new request instead of replay')
    data=job['data']
    if set(data)!={'envelope','envelope_hash','original_request'} or digest(data['envelope'])!=data['envelope_hash']:
        raise Invalid('Agent approval envelope integrity failed')
    frozen=data['envelope'];access=access or AgentAccess(store);row=guard(store,job['app_id'],frozen)
    alive=live_guard(store,job,stop);alive();secret=access.secret(job['app_id'],row)
    if frozen['provider'] in NATIVE:
        result,usage=native_run(frozen['provider'],row['data']['tool'],frozen['prompt'],frozen['model'],secret,alive)
    else:result,usage=(transport or api_run)(row['data'],secret,frozen['prompt'],frozen['max_output_tokens'],alive)
    alive();guard(store,job['app_id'],frozen)
    result=draft(result,frozen['source_ids'])
    if secret and secret in canonical(result):raise Invalid('Agent result exposed a protected key and was rejected')
    measured=usage_observation(usage)
    return dict(status='DRAFT_READY',draft=result,sha256=digest(result),**measured,quota='UNKNOWN',cost='UNKNOWN',
        publication='NOT_RUN',automatically_verified=False,next_actions=['Review this draft and its unknowns before preparing any external action'])


def complete(db,job,result,status):
    """Only an accepted worker completion can update the connection test state."""
    data=job.get('data',{});frozen=data.get('envelope')
    if not isinstance(frozen,dict) or digest(frozen)!=data.get('envelope_hash'):return
    if frozen.get('app_id')!=job['app_id'] or frozen.get('schema')!=SCHEMA:return
    if not all(k in frozen for k in ('task','connection_id','connection_version')):return
    if status=='SUCCEEDED' and frozen['task']=='connection_test':
        db.execute("UPDATE agent_connections SET status='TESTED',last_test=?,updated=? WHERE app_id=? AND id=? AND version=? AND status!='DISCONNECTED'",
            (now(),now(),job['app_id'],frozen['connection_id'],frozen['connection_version']))
    if status=='BLOCKED':
        db.execute("UPDATE agent_connections SET status='NEEDS_ATTENTION',updated=? WHERE app_id=? AND id=? AND version=? AND status!='DISCONNECTED'",
            (now(),job['app_id'],frozen['connection_id'],frozen['connection_version']))
