"""Event-driven durable progression through exact approved evidence actions."""
from .common import Invalid,canonical,digest,now,uid
from .db import connection
from .sequence_store import decode
from .sequence_jobs import authority,link

WAITING={'QUEUED','RUNNING'}
OUTCOMES={'EVIDENCE_GATHERED','NEEDS_RESOLUTION','WAITING_FOR_MATURITY','WAITING_FOR_SOURCES'}


def outcome(db, run, job):
    """Only typed native outcomes are adopted; raw provider errors stay outside the plan."""
    from .source_progress import children,state
    if job['status'] in WAITING:return None
    result=job['result'];status='NEEDS_RESOLUTION'
    if job['status']=='SUCCEEDED' and isinstance(result,dict) and result.get('status') in OUTCOMES:
        status=result['status']
        if status=='WAITING_FOR_SOURCES':
            status=state([r['status'] for r in children(db,run['app_id'],result.get('children'))])
            if status=='COLLECTING_SOURCES':return None
    return dict(job_id=job['id'],state=status,result_sha256=digest(result))


def enqueue_child(db,run,step):
    """Deterministic exact child identity closes the crash window before checkpoint commit."""
    from .worker import json_job
    data=step['data'];key='resolution-'+data['original_request']['request_key'];stamp=now()
    db.execute('INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
        (uid(),run['app_id'],'resolution',canonical(data),'QUEUED',stamp,stamp,key))
    job=json_job(db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',(run['app_id'],key)).fetchone())
    if job['action']!='resolution' or job['data']!=data:raise Invalid('Saved sequence child identity conflicts with approved work')
    link(db,run['app_id'],run['id'],job['id'],True)
    return job['id']


def settle_child(db,run,result,step):
    """Missing or changed child receipts cannot produce a verified outcome."""
    from .worker import json_job
    row=db.execute('SELECT * FROM jobs WHERE id=? AND app_id=?',(result['active_job_id'],run['app_id'])).fetchone()
    if row is None:
        value=dict(job_id=result['active_job_id'],state='NEEDS_RESOLUTION',result_sha256=digest(None))
    else:
        job=json_job(row)
        if job['data']!=step['data'] or job['action']!='resolution':raise Invalid('Approved sequence child changed')
        value=outcome(db,run,job)
    if value is None:return False
    result['step_outcomes'].append(dict(value,position=result['checkpoint'],tool=step['tool']))
    result['checkpoint']+=1;result.pop('active_job_id',None)
    return True


def advance_run(db,run):
    """Record one terminal outcome before advancing; no provider is called here."""
    result=run['result'];index=result['checkpoint'];steps=run['plan']['steps']
    if type(index) is not int or not 0<=index<len(steps) or len(result['step_outcomes'])!=index:
        raise Invalid('Saved sequence checkpoint differs; review retained receipts')
    if result.get('active_job_id') and not settle_child(db,run,result,steps[index]):return False
    state='WAITING'
    if result['checkpoint']==len(steps):
        state='EVIDENCE_REVIEW_REQUIRED'
        result.update(summary='Approved actions finished; review their evidence and remaining gaps',
                      next_actions=['Inspect each action result and the current workflow','Prepare the next missing work for approval'])
    else:
        step=steps[result['checkpoint']]
        result['active_job_id']=enqueue_child(db,run,step)
        result.update(summary='Following the approved plan; waiting for '+step['title'],
                      next_actions=['Keep the local service open or inspect saved progress','Cancel to stop remaining owned work'])
    db.execute('UPDATE campaign_sequences SET state=?,result=?,updated=? WHERE id=?',(state,canonical(result),now(),run['id']))
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
        (run['app_id'],'sequence.progress',canonical(dict(run_id=run['id'],state=state,result_hash=digest(result))),now()))
    return True


def stop(db,row,run,error):
    """Retain damaged state and outcomes; expose a new-approval recovery path."""
    if run is not None:
        result=dict(run['result'],summary='Current approval is required before this sequence can continue',
                    next_actions=[str(error),'Review the current execution plan; previous results are retained'])
        db.execute("UPDATE campaign_sequences SET state='APPROVAL_REQUIRED',result=?,updated=? WHERE id=?",(canonical(result),now(),row['id']))
    else:
        db.execute("UPDATE campaign_sequences SET state='APPROVAL_REQUIRED',updated=? WHERE id=?",(now(),row['id']))
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
        (row['app_id'],'sequence.approval_required',canonical(dict(run_id=row['id'],failure_class=type(error).__name__)),now()))
    return True

def advance(store) -> bool:
    """Advance one eligible persisted sequence without performing provider calls."""
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute("SELECT r.* FROM campaign_sequences r WHERE r.state='QUEUED' OR (r.state='WAITING' AND NOT EXISTS (SELECT 1 FROM sequence_jobs l JOIN jobs j ON j.id=l.job_id WHERE l.run_id=r.id AND j.status IN ('QUEUED','RUNNING'))) ORDER BY r.updated,r.id LIMIT 1").fetchone()
        if row is None:return False
        run=None
        try:
            run=decode(row);authority(store,run)
            return advance_run(db,run)
        except (Invalid,KeyError,ValueError,TypeError) as exc:
            return stop(db,row,run,exc)
