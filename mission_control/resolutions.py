"""Typed human approval of agent-proposed evidence work using durable local jobs."""
from datetime import timedelta
import json
import uuid
from .common import Invalid,canonical,digest,iso_time,now,uid
from .db import connection
from .aeo_transport import public_url,origin
from .marketing_agent_manifest import operating_manifest
from .resolution_plan import prepare
from .worker import json_job
from .source_progress import children as source_children, state as child_state, explanation


def request_body(body):
    """No client can supply an executable command, source record or proof result."""
    fields={'issue_id','option_id','source_hash','target_url','request_key'}
    if not isinstance(body,dict) or set(body)!=fields:
        raise Invalid('Use the exact current resolution proposal')
    try:
        if str(uuid.UUID(body['request_key']))!=body['request_key']:raise ValueError()
    except (ValueError,TypeError,AttributeError) as exc:
        raise Invalid('Use a canonical resolution request identity') from exc
    return body


def choose(plan,body):
    """Bind the approved issue and specific ready option; prerequisite setup stays distinct."""
    issue=next((r for r in plan['issues'] if r['id']==body['issue_id']),None)
    if issue is None or issue['source_hash']!=body['source_hash']:
        raise Invalid('Evidence needs or sources changed; review current resolution options')
    option=next((r for r in issue['options'] if r['id']==body['option_id']),None)
    if option is None or not option['ready']:
        raise Invalid('Resolve this option source access or target prerequisite first')
    return issue,option


def parameters(app,option,target):
    """Only an optional same-origin public URL is editable at action approval."""
    p=dict(option['parameters'])
    if option['tool']=='inspect_site':
        p['url']=public_url(target if target is not None else p['url'])
        if origin(p['url'])!=origin(app['data']['website']):
            raise Invalid('Resolution target must stay on this app website origin')
    elif target is not None:
        raise Invalid('This resolution has no editable URL target')
    return p


def envelope(app,plan,issue,option,body,operator):
    """Freeze exact authority, source, optional edit and expiry before enqueue."""
    stamp=now();policy=operating_manifest(app)
    return dict(app_id=app['id'],manifest_version=app['version'],app_hash=digest(app['data']),
        policy_hash=digest(policy),issue_id=issue['id'],kind=issue['kind'],stages=issue['stages'],
        gap=issue['gap'],tool=option['tool'],parameters=parameters(app,option,body['target_url']),
        source_hash=issue['source_hash'],approved_by=operator,approved_at=stamp,
        record_sources=plan['record_sources'],
        expires_at=(iso_time(stamp)+timedelta(seconds=policy['resolution_approval_seconds'])).isoformat())


def summary(job,children=()):
    """Distinguish execution, child progress, partial artifacts and outstanding proof."""
    value=job['result'] or {};frozen=job['data']['envelope']
    state=job['status']
    if state=='SUCCEEDED':state=value['status']
    if state=='WAITING_FOR_SOURCES':
        states=[c['status'] for c in children]
        state=child_state(states)
        message,next_actions=explanation(state,children)
    else:
        message=value.get('summary') or 'Approved evidence work: '+job['status']
        next_actions=value.get('next_actions') or ['Review source access or choose the next permitted resolution']
    return dict(job_id=job['id'],issue_id=frozen['issue_id'],tool=frozen['tool'],status=state,
        job_status=job['status'],
        summary=message,
        artifacts=value.get('artifacts',[]),children=list(children),
        next_actions=next_actions,
        proof_status='PARTIAL' if state=='EVIDENCE_GATHERED' else 'NOT_VERIFIED',automatically_verified=False)


class Resolutions:
    def __init__(self,store,operator='local-operator'):
        self.store,self.operator=store,operator

    def proposal(self,app_id):
        """Recompute the authoritative proposal; never accept client-supplied options."""
        from .service import Service
        w=Service(self.store,self.operator).workspace(app_id)
        return w['app'],w['resolutions']

    def start(self,app_id,body):
        """Record one exact approval and idempotent job with no network in the transaction."""
        request_body(body);self.store.app(app_id)
        existing=self.replay(app_id,body)
        if existing:return existing
        app,plan=self.proposal(app_id);issue,option=choose(plan,body)
        frozen=envelope(app,plan,issue,option,body,self.operator)
        data=dict(envelope=frozen,envelope_hash=digest(frozen),original_request=body)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            current=db.execute('SELECT version,data FROM apps WHERE id=?',(app_id,)).fetchone()
            if current['version']!=app['version'] or digest(json.loads(current['data']))!=frozen['app_hash']:
                raise Invalid('App changed before approval; review current resolution')
            inserted=db.execute('INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                (uid(),app_id,'resolution',canonical(data),'QUEUED',now(),now(),'resolution-'+body['request_key'])).rowcount
            row=db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',(app_id,'resolution-'+body['request_key'])).fetchone()
            job=json_job(row)
            if job['data']['original_request']!=body:raise Invalid('Resolution request identity was reused for different input')
            if inserted:
                db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                    (app_id,'resolution.approved',canonical(dict(job_id=job['id'],envelope_hash=job['data']['envelope_hash'])),now()))
        return job

    def replay(self,app_id,body):
        """A replay reads the prior receipt; it cannot extend or alter its approval."""
        with connection(self.store.path) as db:
            row=db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',(app_id,'resolution-'+body['request_key'])).fetchone()
        if row is None:return None
        job=json_job(row)
        if job['action']!='resolution' or job['data']['original_request']!=body:
            raise Invalid('Resolution request identity was reused for different input')
        return job

    def history(self,app_id):
        """App-scoped durable progress remains inspectable after browser/server restart."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            jobs=[json_job(r) for r in db.execute("SELECT * FROM jobs WHERE app_id=? AND action='resolution' ORDER BY created DESC LIMIT 100",(app_id,))]
            result=[]
            for job in jobs:
                identities=(job['result'] or {}).get('children',[])
                children=source_children(db,app_id,identities) if identities or (job['result'] or {}).get('status')=='WAITING_FOR_SOURCES' else []
                result.append(summary(job,children))
            return result
