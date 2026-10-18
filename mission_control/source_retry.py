"""Explicit, bounded replacement reads; failed source receipts remain immutable."""
from .common import Invalid, digest
from .worker import json_job

TERMINAL = {'BLOCKED', 'FAILED', 'CANCELLED'}


def fingerprint(job):
    """Bind the selected result and attempts, without exporting raw diagnostics."""
    return digest({key: job[key] for key in ('id', 'action', 'data', 'status', 'result', 'attempts')})


def prefix(base_id):
    """Keep each retry chain separate from every other source and approval."""
    return 'source-retry-' + base_id + '-'


def identity(base_id, parameters, request_key):
    """Bind durable idempotency to the whole approved target set and request."""
    return prefix(base_id)+digest(dict(parameters=parameters,request_key=request_key))


def retry_rows(db, app_id, root, expected, limit):
    """Reject corrupted or excessive chains without widening the local read bound."""
    start=prefix(root['id'])
    rows=db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key>=? AND request_key<? ORDER BY created DESC,id DESC LIMIT ?',
                    (app_id,start,start+'\uffff',limit+1)).fetchall()
    history=[json_job(row) for row in rows]
    if len(history)>limit or any(j['action']!='sync' or j['data']!=expected for j in history):
        raise Invalid('Source retry history differs; inspect its saved receipts')
    return history

def project(db, app_id, task, limit) -> object:
    """Project bounded latest retry history for an existing source read."""
    root = task['job']
    task.update(retry_history=[], retry_request_key=None, retry_limit_reached=False)
    if root is None:
        return None
    if root['action'] != 'sync' or root['data'] != task['data']:
        raise Invalid('Original source read differs from the current collection')
    history = retry_rows(db,app_id,root,task['data'],limit)
    current = history[0] if history else root
    task.update(job=current, base_job_id=root['id'],
                retry_history=[dict(job_id=j['id'], status=j['status']) for j in history],
                retry_request_key=current['request_key'] if history else None,
                retry_limit_reached=len(history) >= limit)
    if current['status'] not in TERMINAL or len(history) >= limit:
        return None
    return dict(base_job_id=root['id'], job_id=current['id'], job_hash=fingerprint(current))


def replay(db, app_id, parameters, request_key):
    """Read existing retry receipts; never reset jobs on a worker lease replay."""
    rows = [db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?',
            (app_id, identity(c['base_job_id'],parameters,request_key))).fetchone() for c in parameters['retry_candidates']]
    if not any(rows):
        return None
    if not all(rows):
        raise Invalid('Source retry receipts are incomplete; inspect this collection')
    jobs = [json_job(row) for row in rows]
    for candidate, job in zip(parameters['retry_candidates'], jobs):
        source = db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?', (app_id, candidate['job_id'])).fetchone()
        if source is None or job['action'] != 'sync' or job['data'] != json_job(source)['data']:
            raise Invalid('Source retry identity conflicts with saved work')
    return dict(tasks=[dict(job=job, retry_request_key=job['request_key']) for job in jobs])

def enqueue(db, app_id, plan, parameters, request_key, enqueue_task) -> object:
    """Atomically preserve failed receipts and enqueue exact approved replacement reads."""
    if set(parameters) != {'collection_hash', 'retry_candidates'} or not parameters['retry_candidates']:
        raise Invalid('Approve the exact current failed-source proposal')
    if len(parameters['retry_candidates']) > 12:
        raise Invalid('Source retry collection exceeds twelve reads')
    saved = replay(db, app_id, parameters, request_key)
    if saved is not None:
        return saved
    if parameters['collection_hash'] != plan['source_hash'] or parameters['retry_candidates'] != plan['retry_candidates']:
        raise Invalid('Source hash or failed read changed; approve the current retry proposal')
    tasks = {task.get('base_job_id'): task for task in plan['tasks']}
    result = []
    for candidate in parameters['retry_candidates']:
        task = tasks[candidate['base_job_id']]
        key = identity(candidate['base_job_id'],parameters,request_key)
        enqueue_task(db, app_id, dict(task, request_key=key))
        row = db.execute('SELECT * FROM jobs WHERE app_id=? AND request_key=?', (app_id, key)).fetchone()
        result.append(dict(job=json_job(row), retry_request_key=key))
    return dict(tasks=result)
