"""Durable exact approvals and visible checkpoints, separate from campaign proof."""
import json,uuid
from .common import Invalid,canonical,digest,now,uid
from .db import connection
from .sequence_plan import prepare,freeze

ACTIVE=('QUEUED','WAITING')
STATES=(*ACTIVE,'CANCELLED','APPROVAL_REQUIRED','EVIDENCE_REVIEW_REQUIRED')


def decode(row):
    """Decode private durable fields without interpreting them as authority."""
    value=dict(row)
    try:
        for key in ('plan','original_request','result'):
            value[key]=json.loads(value[key])
            if not isinstance(value[key],dict):raise ValueError()
        if not isinstance(value['plan'].get('steps'),list) or not value['plan']['steps']:raise ValueError()
        if value['state'] not in STATES or digest(value['plan'])!=value['plan_hash']:raise ValueError()
    except (ValueError,TypeError) as exc:
        raise Invalid('Saved sequence needs integrity review; receipts are retained') from exc
    return value


def body_valid(body):
    """The browser submits selections and hashes, never tool commands or envelopes."""
    if not isinstance(body,dict) or set(body)!={'proposal_hash','selected_steps','request_key'}:
        raise Invalid('Review the exact current sequence proposal')
    try:valid=str(uuid.UUID(body['request_key']))==body['request_key']
    except (ValueError,TypeError,AttributeError):valid=False
    if not valid:raise Invalid('Use a canonical sequence request identity')


def public(run):
    """Expose readable progress without raw diagnostics or private approved envelopes."""
    result=run['result']
    return dict(id=run['id'],state=run['state'],created=run['created'],updated=run['updated'],
        approved_at=run['plan']['approved_at'],expires_at=run['plan']['expires_at'],
        steps=[{k:s[k] for k in ('id','title','tool')} for s in run['plan']['steps']],
        checkpoint=result.get('checkpoint',0),step_outcomes=result.get('step_outcomes',[]),
        summary=result.get('summary','Approved work is saved and waiting for the local worker'),
        next_actions=result.get('next_actions',['Keep the local service open; inspect the saved progress']),
        execution_mode='LOCAL_SERVICE_REQUIRED',automatically_verified=False,spend_minor=0)


def feedback(store,app_id):
    """Only typed latest-run state and integrity hashes enter model context."""
    with connection(store.path) as db:
        row=db.execute('SELECT * FROM campaign_sequences WHERE app_id=? ORDER BY created DESC,id DESC LIMIT 1',(app_id,)).fetchone()
    if row is None:return None
    try:run=decode(row)
    except Invalid:
        return dict(run_id=row['id'],state='INVALID',source_sha256=digest(dict(row)),proof='NOT_VERIFIED')
    return dict(run_id=run['id'],state=run['state'],checkpoint=run['result'].get('checkpoint',0),
                steps=len(run['plan']['steps']),source_sha256=digest(dict(plan_hash=run['plan_hash'],result=run['result'])),
                proof='NOT_AUTOMATICALLY_VERIFIED')


def safe_public(row):
    """A damaged saved run is an explicit recovery state, never fake empty history."""
    try:return public(decode(row))
    except (Invalid,KeyError,TypeError):
        return dict(id=row['id'],state='APPROVAL_REQUIRED',steps=[],checkpoint=0,step_outcomes=[],
            summary='Saved run needs integrity review; its receipts are retained',
            next_actions=['Review current work to approve a new plan; retain the damaged run for recovery'],
            execution_mode='LOCAL_SERVICE_REQUIRED',automatically_verified=False,spend_minor=0)


class Sequences:
    def __init__(self,store,operator='local-operator'):
        self.store,self.operator=store,operator

    def proposal(self,app_id):
        """Read current native app sources without performing a provider request."""
        from .service import Service
        w=Service(self.store,self.operator).workspace(app_id)
        return w,prepare(w['app'],w['resolutions'],w['preparation']['collection'])

    def approve(self,app_id,body):
        """Freeze an exact finite plan once; replay cannot extend its approval."""
        body_valid(body);self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            saved=db.execute('SELECT * FROM campaign_sequences WHERE app_id=? AND request_key=?',(app_id,body['request_key'])).fetchone()
            if saved is not None:
                run=decode(saved)
                if run['original_request']!=body:raise Invalid('Sequence request identity was reused for different input')
                return public(run)
            w,proposal=self.proposal(app_id)
            if body['proposal_hash']!=proposal['proposal_hash']:raise Invalid('App or sources changed; review the current sequence')
            identity=uid();plan=freeze(w['app'],w['resolutions'],proposal,body,identity,self.operator)
            result=dict(checkpoint=0,step_outcomes=[],summary='Approved sequence saved for the local worker')
            stamp=now()
            db.execute('INSERT INTO campaign_sequences VALUES(?,?,?,?,?,?,?,?,?,?)',
                (identity,app_id,canonical(plan),digest(plan),canonical(body),body['request_key'],'QUEUED',canonical(result),stamp,stamp))
            db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                (app_id,'sequence.approved',canonical(dict(run_id=identity,plan_hash=digest(plan))),stamp))
            return public(decode(db.execute('SELECT * FROM campaign_sequences WHERE id=?',(identity,)).fetchone()))

    def history(self,app_id):
        """Keep app-scoped saved progress inspectable after browser and service restart."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            return [safe_public(r) for r in db.execute('SELECT * FROM campaign_sequences WHERE app_id=? ORDER BY created DESC,id DESC LIMIT 100',(app_id,))]

    def cancel(self,app_id,identity,body):
        """Stop only this run and its owned active jobs, retaining shared reads and receipts."""
        if not isinstance(body,dict) or set(body)!={'confirm_cancel'} or body['confirm_cancel'] is not True:
            raise Invalid('Confirm stopping this saved sequence')
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM campaign_sequences WHERE app_id=? AND id=?',(app_id,identity)).fetchone()
            if row is None:raise Invalid('Sequence is unavailable in this app')
            run=decode(row)
            if run['state']=='CANCELLED':return public(run)
            if run['state'] not in ACTIVE:raise Invalid('This saved sequence is already finished; inspect its results')
            result=dict(run['result'],summary='Stopped. Existing evidence and preexisting shared reads are retained',
                next_actions=['Review retained results or approve a new current sequence'])
            db.execute("UPDATE campaign_sequences SET state='CANCELLED',result=?,updated=? WHERE id=?",(canonical(result),now(),identity))
            changed=db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND status IN ('QUEUED','RUNNING') AND id IN (SELECT job_id FROM sequence_jobs WHERE run_id=? AND owned=1)",(now(),app_id,identity)).rowcount
            db.execute("UPDATE experiment_tracking_runs SET status='CANCELLED',updated=? WHERE app_id=? AND status IN ('QUEUED','READING') AND job_id IN (SELECT job_id FROM sequence_jobs WHERE run_id=? AND owned=1)",(now(),app_id,identity))
            db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                (app_id,'sequence.cancelled',canonical(dict(run_id=identity,owned_jobs_stopped=changed)),now()))
            return public(decode(db.execute('SELECT * FROM campaign_sequences WHERE id=?',(identity,)).fetchone()))
