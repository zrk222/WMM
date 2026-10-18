"""Atomic owned/shared membership and revocable source authority for worker jobs."""
import json
from .common import Invalid,digest,iso_time,now
from .db import connection


def authority(store, run):
    """A current plan hash is necessary but never replaces current app authority."""
    from .resolution_tools import guard
    from .sequence_store import ACTIVE
    if run['state'] not in ACTIVE:raise Invalid('Sequence stopped or finished; no further owned work is permitted')
    plan=run['plan']
    if digest(plan)!=run['plan_hash'] or plan['app_id']!=run['app_id']:
        raise Invalid('Sequence approval integrity differs; review a new proposal')
    if iso_time(now())>iso_time(plan['expires_at']):raise Invalid('Sequence approval expired; review current work')
    guard(store,run['app_id'],plan['steps'][0]['data']['envelope'])
    return run

def link(db, app_id, run_id, job_id, owned) -> object:
    """Link source ownership atomically to the reviewed sequence."""
    from .sequence_store import decode,ACTIVE
    row=db.execute('SELECT * FROM campaign_sequences WHERE id=? AND app_id=?',(run_id,app_id)).fetchone()
    job=db.execute('SELECT action,data FROM jobs WHERE id=? AND app_id=?',(job_id,app_id)).fetchone()
    if row is None or job is None or job['action'] not in ('sync','resolution','experiment_tracking'):
        raise Invalid('Sequence job ownership is unavailable for this app')
    run=decode(row)
    if run['state'] not in ACTIVE or iso_time(now())>iso_time(run['plan']['expires_at']):
        raise Invalid('Sequence stopped or expired before source enqueue')
    if digest(run['plan'])!=run['plan_hash']:raise Invalid('Sequence approval integrity differs')
    hashed=digest(json.loads(job['data']))
    db.execute('INSERT OR IGNORE INTO sequence_jobs VALUES(?,?,?,?,?)',(run_id,app_id,job_id,int(owned),hashed))
    saved=db.execute('SELECT owned,data_hash FROM sequence_jobs WHERE run_id=? AND job_id=?',(run_id,job_id)).fetchone()
    if saved['data_hash']!=hashed or owned and not saved['owned']:
        raise Invalid('Saved sequence ownership differs; no job authority was changed')
    return dict(job_id=job_id,owned=bool(saved['owned']))

def guard_owned(store, job) -> object:
    """Reject cancelled or stale authority before and after owned work."""
    from .sequence_store import decode
    with connection(store.path) as db:
        row=db.execute('SELECT r.*,l.data_hash AS job_hash FROM campaign_sequences r JOIN sequence_jobs l ON r.id=l.run_id WHERE l.job_id=? AND l.owned=1',(job['id'],)).fetchone()
    if row is None:return None
    run=decode(row)
    if run['app_id']!=job['app_id'] or run['job_hash']!=digest(job['data']):
        raise Invalid('Owned sequence job identity changed; no read is permitted')
    return authority(store,run)


def callback(store, job):
    """Only a verified owned resolution can register its source-read children."""
    owner=guard_owned(store,job)
    if owner is None:return None
    def register(db,app_id,identity,created):
        return link(db,app_id,owner['id'],identity,created)
    return register
