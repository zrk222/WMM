"""One bounded, app-scoped interpretation of durable source collection progress."""
from .db import connection

STATES = {'QUEUED', 'RUNNING', 'SUCCEEDED', 'BLOCKED', 'FAILED', 'CANCELLED'}


def valid_children(identities):
    """Reject corrupt or duplicated indexes before any database lookup."""
    if not isinstance(identities, list) or not 0 < len(identities) <= 12:
        return False
    if any(not isinstance(i, str) or not 0 < len(i) <= 120 for i in identities):
        return False
    return len(set(identities)) == len(identities)


def children(db, app_id, identities):
    """Only source reads in the owning workspace can satisfy the parent."""
    if not valid_children(identities):
        return [dict(job_id=None, status='INVALID_CHILD_INDEX')]
    result = []
    for identity in identities:
        row = db.execute('SELECT action,status,data FROM jobs WHERE app_id=? AND id=?',
                         (app_id, identity)).fetchone()
        state = row['status'] if row and row['action'] == 'sync' else 'MISSING'
        if row and row['action']=='experiment_tracking':state=tracking_state(db,app_id,identity,row)
        result.append(dict(job_id=identity, status=state))
    return result


def tracking_state(db,app_id,identity,job):
    """Worker completion is insufficient: inspect the exact native tracking receipt."""
    import json
    from .common import Invalid
    from .experiment_tracking import decode
    try:
        row=db.execute('SELECT * FROM experiment_tracking_runs WHERE app_id=? AND job_id=?',(app_id,identity)).fetchone()
        if row is None:return 'MISSING'
        saved=decode(row)
        if json.loads(job['data'])!=dict(tracking_run_id=saved['id']):return 'MISSING'
        if job['status'] in ('QUEUED','RUNNING'):return job['status']
        if job['status']!='SUCCEEDED':return job['status']
        return 'SUCCEEDED' if saved['status']=='OBSERVED' else 'BLOCKED'
    except (Invalid,ValueError,TypeError):return 'MISSING'


def state(states):
    """A completed dispatcher is not a completed collection or campaign."""
    if not states or len(states) > 12 or any(s not in STATES for s in states):
        return 'NEEDS_RESOLUTION'
    if any(s in ('BLOCKED', 'FAILED', 'CANCELLED') for s in states):
        return 'NEEDS_RESOLUTION'
    return 'EVIDENCE_GATHERED' if all(s == 'SUCCEEDED' for s in states) else 'COLLECTING_SOURCES'


def read_state(store, app_id, identities):
    """Reconstruct status after restart without requesting any external source."""
    if not valid_children(identities):
        return 'NEEDS_RESOLUTION'
    with connection(store.path) as db:
        return state([r['status'] for r in children(db, app_id, identities)])


def explanation(status, rows):
    """Describe actual child progress and the next permitted action, not dispatch."""
    completed = sum(r['status'] == 'SUCCEEDED' for r in rows)
    total = len(rows)
    if status == 'EVIDENCE_GATHERED':
        return (f'All {total} provider source reads completed; campaign proof remains unverified',
                ['Review the collected reports for release scope, coverage and remaining evidence gaps'])
    if status == 'COLLECTING_SOURCES':
        return (f'{completed} of {total} provider source reads completed; collection continues',
                ['Wait for outstanding reads; inspect completed reports while collection continues'])
    return ('Source collection needs resolution; completed reports are retained',
            ['Inspect failed, cancelled or missing reads; resolve source access and approve a current collection proposal'])
