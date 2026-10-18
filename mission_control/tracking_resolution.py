"""Source-bound tracking actions reuse native receipts and parent approval authority."""
import uuid
from .common import Invalid,canonical,digest,now,uid
from .db import connection


def options(app,insights,experiments):
    """Recommend a bounded set from saved app-owned definitions, never model inputs."""
    from .tracking_contract import proposal
    result=[]
    for experiment in experiments[:3]:
        for source in insights['sources'][:3]:
            saved=dict(source)
            saved.setdefault('app_id',app['id']);saved.setdefault('hash',digest(source['data']))
            try:plan=proposal(app,experiment,saved)
            except (Invalid,KeyError,ValueError,TypeError):continue
            ready=source['status'] not in ('PERMISSION_REQUIRED',)
            target=(f"Experiment {plan['experiment_id']}; source {plan['source_id']}; "
                    f"PostHog {plan['region']} project {plan['project_id']}; release {plan['release']}; "
                    f"locale {plan['locale']}; window {plan['starts_at']} to {plan['ends_at']}")
            result.append(dict(tool='inspect_tracking',ready=ready,prerequisite='connections',
                parameters=dict(tracking_plan=plan,name=target),access=target,
                title='Check tracking: '+experiment['data']['name']))
            if len(result)==3:return result
    return result


def validate(store,app_id,parameters):
    """Recompute the exact setup; no caller may substitute a target or query."""
    from .experiment_tracking import Tracking
    saved=parameters['tracking_plan']
    current=Tracking(store).prepare(app_id,{k:saved[k] for k in ('experiment_id','source_id')})
    if saved!=current:raise Invalid('Tracking source or experiment changed; approve current setup')
    return current


def guard_child(store,saved,expected,job):
    """Revalidate inherited parent authority around each native remote request."""
    import json
    from .resolution_tools import guard
    from .sequence_jobs import guard_owned
    parent=saved['plan'].get('resolution_envelope')
    if parent is None:return
    if parent['parameters']['tracking_plan']!=expected or parent['expires_at']!=saved['expires']:
        raise Invalid('Tracking child differs from its parent approval')
    guard(store,saved['app_id'],parent)
    guard_owned(store,dict(job,data=json.loads(job['data'])))


def insert(db,app_id,frozen,key,proposed):
    """One native child per parent approval, retaining its original expiry."""
    request=dict(parent_request_key=key,parent_envelope_hash=digest(frozen))
    request_key=str(uuid.uuid5(uuid.UUID(key),'tracking'))
    old=db.execute('SELECT * FROM experiment_tracking_runs WHERE app_id=? AND request_key=?',(app_id,request_key)).fetchone()
    if old is not None:
        from .experiment_tracking import decode
        saved=decode(old)
        if saved['original_request']!=request:raise Invalid('Tracking parent approval identity conflicts')
        return saved['id'],saved['job_id'],False
    plan=dict(proposal=proposed,policy_hash=frozen['policy_hash'],approved_at=frozen['approved_at'],
              expires_at=frozen['expires_at'],resolution_envelope=frozen)
    identity,job_id,stamp=uid(),uid(),now()
    db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
        (job_id,app_id,'experiment_tracking',canonical(dict(tracking_run_id=identity)),'QUEUED',stamp,stamp,'tracking-'+request_key))
    db.execute('INSERT INTO experiment_tracking_runs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (identity,app_id,proposed['experiment_id'],proposed['source_id'],canonical(plan),digest(plan),canonical(request),
         request_key,'QUEUED',None,None,job_id,frozen['expires_at'],stamp,stamp))
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
        (app_id,'tracking.resolution_approved',canonical(dict(id=identity,plan_hash=digest(plan))),stamp))
    return identity,job_id,True

def dispatch(store, app_id, frozen, request_key, on_job) -> object:
    """Atomically register the exact-approved tracking child without renewing expiry."""
    from .resolution_tools import guard,result
    guard(store,app_id,frozen)
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        guard(store,app_id,frozen)
        proposed=validate(store,app_id,frozen['parameters'])
        identity,job_id,created=insert(db,app_id,frozen,request_key,proposed)
        if on_job is not None:on_job(db,app_id,job_id,created)
    return dict(result('Tracking read queued under the original approval; inspect its native receipt',
        [dict(kind='experiment_tracking',id=identity,job_id=job_id)],
        ['Wait for the scoped tracking read; inspect setup or permission recovery if needed',
         'Tracking aggregates do not prove rendered exposure or campaign lift'],'WAITING_FOR_SOURCES'),children=[job_id])
