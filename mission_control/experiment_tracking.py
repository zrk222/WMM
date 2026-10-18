"""Durable exact-approved tracking reads with app/source authority and recovery."""
from datetime import timedelta
import json,re,uuid
from .common import Invalid,canonical,digest,iso_time,now,uid
from .db import connection
from .experiments import lookup
from .insights import Insights
from .credential_vault import Vault
from .marketing_agent_manifest import operating_manifest
from .tracking_contract import proposal,SCOPE
from . import tracking_posthog

ACTIVE=('QUEUED','READING')
STATES=(*ACTIVE,'OBSERVED','NO_OBSERVATIONS','NEEDS_SETUP','NEEDS_REVIEW','CANCELLED')


def failure_result(error):
    """Expose closed recovery hints without retaining raw provider or key-store diagnostics."""
    from .insights_transport import ProviderFailure
    code='SOURCE_OR_TRACKING_CHANGED'
    if isinstance(error,ProviderFailure):
        allowed={'PERMISSION_REQUIRED','RATE_LIMITED','PROVIDER_ERROR','NETWORK_ERROR','RESPONSE_TOO_LARGE','INVALID_RESPONSE'}
        code=error.code if error.code in allowed else 'PROVIDER_ERROR'
    elif isinstance(error,PermissionError):code='PROTECTED_ACCESS_REQUIRED'
    elif isinstance(error,OSError):code='KEY_STORAGE_UNAVAILABLE'
    return dict(status='NEEDS_REVIEW',failure_code=code,scope=SCOPE,observed_counts=None,
        next_actions=['Inspect the current app, experiment and PostHog connection',
                      'Confirm project, feature-flag and query read permissions; reconnect if necessary',
                      'Review the expected setup and approve a new read; previous receipts are retained'])


def decoded_fields(value):
    """Decode only the persisted structured fields and reject wrong JSON container types."""
    value['plan']=json.loads(value['plan']);value['original_request']=json.loads(value['original_request'])
    value['result']=json.loads(value['result']) if value['result'] is not None else None
    if not isinstance(value['plan'],dict) or not isinstance(value['original_request'],dict):raise ValueError()
    if value['result'] is not None and not isinstance(value['result'],dict):raise ValueError()
    return value


def decode(row):
    """Verify saved approval and result integrity before exposing their contents."""
    try:
        value=decoded_fields(dict(row))
        if value['status'] not in STATES:raise ValueError()
        if value['plan'].get('expires_at')!=value['expires']:raise ValueError()
        if digest(value['plan'])!=value['hash']:raise ValueError()
        if value['result'] is not None and digest(value['result'])!=value['result_hash']:raise ValueError()
    except (ValueError,TypeError) as exc:raise Invalid('Tracking receipt integrity differs; retain it for review') from exc
    return value


def public(row):
    """Return approved public scope and typed outcomes without protected key references."""
    value=decode(row)
    result={k:value[k] for k in ('id','app_id','experiment_id','source_id','status','plan','result','job_id','expires','created','updated')}
    if value['status'] in ACTIVE and 'job_status' in value and value['job_status'] not in ('QUEUED','RUNNING'):
        result.update(status='READ_RECOVERY_REQUIRED',next_actions=['Inspect the saved worker job','Review current setup and approve a new read; this receipt is retained'])
    return result


def feedback(store,app_id):
    """Ground agent context in typed tracking state and hashes, never raw provider data."""
    rows=Tracking(store).list(app_id)
    if not rows:return None
    row=rows[0]
    return dict(run_id=row['id'],state=row['status'],source_sha256=digest(row),proof='TRACKING_ONLY_NOT_CAUSAL')


def current(store,row):
    """Recheck source, app, experiment, policy, job and expiry around every remote read."""
    saved=decode(row)
    if saved['status'] not in ACTIVE:raise Invalid('This tracking run has stopped or finished')
    if iso_time(now())>iso_time(saved['expires']):raise Invalid('Tracking approval expired; review current work')
    app=store.app(saved['app_id']);api=Insights(store)
    with connection(store.path) as db:
        experiment=lookup(db,saved['app_id'],saved['experiment_id'])
        source=api.row(db,saved['app_id'],saved['source_id'])
        job=db.execute('SELECT action,data,status FROM jobs WHERE id=? AND app_id=?',(saved['job_id'],saved['app_id'])).fetchone()
    data=dict(tracking_run_id=saved['id'])
    if job is None or job['action']!='experiment_tracking' or json.loads(job['data'])!=data or job['status'] not in ('QUEUED','RUNNING'):
        raise Invalid('Tracking job identity or cancellation changed')
    expected=proposal(app,experiment,source)
    if expected!=saved['plan']['proposal'] or digest(operating_manifest(app))!=saved['plan']['policy_hash']:
        raise Invalid('App, experiment, policy or source changed; approve a current read')
    return source


def identifier_fields(body):
    """Reject structured or oversized identifiers before they reach a database binding."""
    for name in ('experiment_id','source_id'):
        value=body.get(name)
        if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}',value):
            raise Invalid('Choose a valid registered experiment and source identity')


def require_body(body):
    """Require only exact current identifiers, hash, canonical replay key and read consent."""
    fields={'experiment_id','source_id','proposal_hash','request_key','confirm_read'}
    if not isinstance(body,dict) or set(body)!=fields or body['confirm_read'] is not True:raise Invalid('Review the exact tracking read and confirm permitted access')
    identifier_fields(body)
    if not isinstance(body['proposal_hash'],str) or not re.fullmatch(r'[a-f0-9]{64}',body['proposal_hash']):raise Invalid('Review the current tracking proposal hash')
    try:valid=str(uuid.UUID(body['request_key']))==body['request_key']
    except (ValueError,TypeError,AttributeError):valid=False
    if not valid:raise Invalid('Use a canonical tracking request identity')


class Tracking:
    def __init__(self,store):self.store=store

    def prepare(self,app_id,body):
        """Recommend exact setup from existing app-owned sources without making requests."""
        if not isinstance(body,dict) or set(body)!={'experiment_id','source_id'}:raise Invalid('Choose the registered experiment and PostHog source')
        identifier_fields(body)
        app=self.store.app(app_id)
        with connection(self.store.path) as db:
            experiment=lookup(db,app_id,body['experiment_id'])
            source=Insights(self.store).row(db,app_id,body['source_id'])
        return proposal(app,experiment,source)

    def get(self,app_id,identity):
        """Resolve an exact app-owned receipt without relying on bounded history position."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            row=db.execute('SELECT r.*,j.status AS job_status FROM experiment_tracking_runs r LEFT JOIN jobs j ON j.id=r.job_id WHERE r.id=? AND r.app_id=?',(identity,app_id)).fetchone()
        if row is None:raise Invalid('Tracking run is not in this app')
        return public(row)

    def list(self,app_id):
        """Retain bounded history and explicit damaged receipts rather than fake emptiness."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows=db.execute('SELECT r.*,j.status AS job_status FROM experiment_tracking_runs r LEFT JOIN jobs j ON j.id=r.job_id WHERE r.app_id=? ORDER BY r.created DESC,r.id DESC LIMIT 100',(app_id,)).fetchall()
        result=[]
        for row in rows:
            try:result.append(public(row))
            except Invalid:result.append(dict(id=row['id'],status='INTEGRITY_REVIEW_REQUIRED',result=None,
                 next_actions=['Retain this receipt and review current tracking setup']))
        return result

    def approve(self,app_id,body):
        """Atomically create one exact-approved read and its durable owned job."""
        require_body(body);app=self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM experiment_tracking_runs WHERE app_id=? AND request_key=?',(app_id,body['request_key'])).fetchone()
            if old is not None:
                saved=decode(old)
                if saved['original_request']!=body:raise Invalid('Tracking request key was reused for other input')
                return self.get(app_id,old['id'])
            proposed=self.prepare(app_id,{k:body[k] for k in ('experiment_id','source_id')})
            if proposed['proposal_hash']!=body['proposal_hash']:raise Invalid('Tracking proposal changed; inspect current setup')
            stamp=now();expires=(iso_time(stamp)+timedelta(seconds=operating_manifest(app)['resolution_approval_seconds'])).isoformat()
            plan=dict(proposal=proposed,policy_hash=digest(operating_manifest(app)),approved_at=stamp,expires_at=expires)
            identity,job_id=uid(),uid();data=dict(tracking_run_id=identity)
            db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                (job_id,app_id,'experiment_tracking',canonical(data),'QUEUED',stamp,stamp,'tracking-'+body['request_key']))
            db.execute('INSERT INTO experiment_tracking_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,app_id,body['experiment_id'],body['source_id'],canonical(plan),digest(plan),canonical(body),
                 body['request_key'],'QUEUED',None,None,job_id,expires,stamp,stamp))
            db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                (app_id,'tracking.approved',canonical(dict(id=identity,plan_hash=digest(plan))),stamp))
        return self.get(app_id,identity)

    def guard(self,app_id,identity):
        """Read fresh durable state so in-flight cancellation cannot adopt a later result."""
        with connection(self.store.path) as db:
            row=db.execute('SELECT * FROM experiment_tracking_runs WHERE id=? AND app_id=?',(identity,app_id)).fetchone()
        if row is None:raise Invalid('Tracking receipt is unavailable')
        return current(self.store,row)

    def save_result(self,app_id,identity,result,status,require_current=False):
        """Preserve cancellation and prior terminal receipts when a remote call finishes."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if require_current:self.guard(app_id,identity)
            changed=db.execute("UPDATE experiment_tracking_runs SET status=?,result=?,result_hash=?,updated=? WHERE id=? AND app_id=? AND status IN ('QUEUED','READING')",
                (status,canonical(result),digest(result),now(),identity,app_id)).rowcount
            if changed:db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                (app_id,'tracking.result',canonical(dict(id=identity,status=status,result_hash=digest(result))),now()))
        return self.get(app_id,identity)

    def execute(self,job):
        """Run fixed guarded reads; retries cannot become provider writes or extend authority."""
        if set(job['data'])!={'tracking_run_id'}:raise Invalid('Tracking job accepts only its owned run identity')
        app_id=job['app_id'];identity=job['data']['tracking_run_id'];saved=self.get(app_id,identity)
        if saved['job_id']!=job['id']:raise Invalid('Tracking job belongs to another approval')
        if saved['status'] not in ACTIVE:return saved
        try:
            source=self.guard(app_id,identity);api=Insights(self.store)
            secret=Vault().get(api.name(app_id,source['credential_ref']))
            binding=dict(app_id=app_id,id=source['id'],hash=source['hash'])
            if not secret or secret.get('binding')!=binding:raise PermissionError('Protected source binding is unavailable')
            with connection(self.store.path) as db:
                db.execute("UPDATE experiment_tracking_runs SET status='READING',updated=? WHERE id=? AND status='QUEUED'",(now(),identity))
            guard=lambda:self.guard(app_id,identity)
            result=tracking_posthog.read(saved['plan']['proposal'],secret['api_key'],guard)
            guard()
            return self.save_result(app_id,identity,result,result['status'],require_current=True)
        except (Invalid,PermissionError,ValueError,TypeError,KeyError,OSError) as exc:
            return self.save_result(app_id,identity,failure_result(exc),'NEEDS_REVIEW')

    def cancel(self,app_id,identity,body):
        """Stop only the named owned read; never discard an already recorded result."""
        if not isinstance(body,dict) or set(body)!={'cancel_run'} or body['cancel_run'] is not True:raise Invalid('Confirm stopping this tracking run')
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM experiment_tracking_runs WHERE id=? AND app_id=?',(identity,app_id)).fetchone()
            if row is None:raise Invalid('Tracking run is not in this app')
            saved=decode(row)
            if saved['status']=='CANCELLED':return public(row)
            if saved['status'] not in ACTIVE:raise Invalid('Tracking run already finished; inspect its retained result')
            db.execute("UPDATE experiment_tracking_runs SET status='CANCELLED',updated=? WHERE id=?",(now(),identity))
            db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE id=? AND app_id=? AND status IN ('QUEUED','RUNNING')",(now(),saved['job_id'],app_id))
        return self.get(app_id,identity)
