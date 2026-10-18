"""Bounded typed action outcomes; raw diagnostics never enter the model context."""
from .common import Invalid,digest
from .db import connection
from .store import decode
from .feedback_artifacts import public_artifact,public_codes
from .source_progress import read_state,valid_children

TOOLS=('collect_sources','inspect_site','refresh_analytics','evaluate_experiment','reuse_observation')
JOB_STATES=('QUEUED','RUNNING','SUCCEEDED','BLOCKED','FAILED','CANCELLED')
OUTCOMES=('EVIDENCE_GATHERED','NEEDS_RESOLUTION','WAITING_FOR_SOURCES','WAITING_FOR_MATURITY')
LIMIT=100


def recent(store,app_id):
    """Inspect a bounded newest window and report omitted history explicitly."""
    with connection(store.path) as db:
        total=db.execute("SELECT count(*) FROM jobs WHERE app_id=? AND action='resolution'",(app_id,)).fetchone()[0]
        rows=db.execute("SELECT * FROM jobs WHERE app_id=? AND action='resolution' ORDER BY created DESC,id DESC LIMIT ?",(app_id,LIMIT)).fetchall()
    try:return [decode(r) for r in rows],total
    except (ValueError,TypeError):raise Invalid('Saved action history is malformed; inspect the affected runs before planning') from None


def valid_envelope(job,app):
    """Historical execution authority is not reused; app identity and integrity must match."""
    data=job.get('data') or {}
    if not isinstance(data,dict):return False
    frozen=data.get('envelope')
    if not isinstance(frozen,dict) or digest(frozen)!=data.get('envelope_hash'):return False
    expected=(app['id'],app['version'],digest(app['data']))
    if tuple(frozen.get(k) for k in ('app_id','manifest_version','app_hash'))!=expected:return False
    return frozen.get('tool') in TOOLS and isinstance(frozen.get('parameters'),dict)


def child_state(store,app_id,children):
    """A queued parent is not proof that its app-owned child reads completed."""
    return read_state(store,app_id,children)


def outcome(store,job):
    """Reduce result bodies to a closed state, excluding arbitrary summary/error fields."""
    if job['status'] not in JOB_STATES:return 'INVALID_RESULT'
    if job['status']!='SUCCEEDED':return job['status']
    result=job.get('result')
    if not isinstance(result,dict) or result.get('status') not in OUTCOMES:return 'INVALID_RESULT'
    if result['status']=='WAITING_FOR_SOURCES':return child_state(store,job['app_id'],result.get('children'))
    return result['status']


def observation(store,app,job):
    """Emit only typed state and hashes for this app current source identity."""
    valid=valid_envelope(job,app)
    frozen=job['data']['envelope'] if valid else {}
    tool=frozen.get('tool') if valid else 'untrusted_or_stale'
    state=outcome(store,job) if valid else 'INVALID_OR_STALE'
    if tool in ('inspect_site','reuse_observation') and state=='EVIDENCE_GATHERED':
        if reuse_candidate(store,app,[job]) is None:state='ARTIFACT_NOT_CURRENT'
    children=child_fingerprint(store,job)
    return dict(job_id=job['id'],tool=tool,state=state,proof='PARTIAL_OR_UNVERIFIED',
        source_sha256=digest(dict(data=job.get('data'),result=job.get('result'),state=state,children=children)))


def child_fingerprint(store,job):
    """Changed child reports invalidate planning even if their job status stays the same."""
    result=job.get('result') or {}
    identities=result.get('children',[]) if isinstance(result,dict) else []
    if isinstance(identities,list) and not identities:return digest([])
    if not valid_children(identities):return 'INVALID_CHILD_INDEX'
    with connection(store.path) as db:
        rows=[db.execute('SELECT status,data,result FROM jobs WHERE app_id=? AND id=?',(job['app_id'],i)).fetchone() for i in identities]
    return digest([tuple(r) if r else None for r in rows])


def selected_public_job(rows,app):
    """A newer failed matching attempt wins over any previous successful artifact."""
    target=app['data'].get('website')
    for job in rows:
        if not valid_envelope(job,app):return None
        frozen=job['data']['envelope']
        if frozen['tool'] in ('inspect_site','reuse_observation') and frozen['parameters'].get('url')==target:return job
    return None


def reuse_candidate(store,app,rows=None,exclude_request_key=None):
    """Find only a validated latest matching native artifact; denial never falls back."""
    if rows is None:rows,_=recent(store,app['id'])
    if exclude_request_key:rows=[r for r in rows if r.get('request_key')!=exclude_request_key]
    job=selected_public_job(rows,app)
    if not job or job['status']!='SUCCEEDED':return None
    return artifact_candidate(store,app,job)


def artifact_candidate(store,app,job):
    """Inspect the one exact artifact referenced by a completed typed result."""
    result=job.get('result') or {}
    if result.get('status')!='EVIDENCE_GATHERED':return None
    try:
        refs=result['artifacts']
        if not isinstance(refs,list) or len(refs)!=1 or refs[0].get('kind')!='aeo_check':return None
        ref=refs[0];target=job['data']['envelope']['parameters']['url']
        row=public_artifact(store,app['id'],ref['id'],ref['sha256'],target)
        return dict(artifact_id=row['id'],artifact_hash=row['hash'],url=target,repair_codes=public_codes(row),source_job_id=job['id'])
    except (Invalid,KeyError,TypeError,ValueError):return None


def feedback(store,app):
    """Keep the latest state per tool plus a stable fingerprint of the inspected window."""
    rows,total=recent(store,app['id']);latest={};views=[observation(store,app,j) for j in rows]
    for view in views:latest.setdefault(view['tool'],view)
    candidate=reuse_candidate(store,app,rows)
    public_reuse={k:v for k,v in (candidate or {}).items() if k!='url'}
    from .sequence_store import feedback as sequence_feedback
    sequence=sequence_feedback(store,app['id'])
    return dict(coverage='COMPLETE' if total<=LIMIT else 'PARTIAL_RECENT_WINDOW',inspected=len(rows),omitted=max(0,total-len(rows)),
        latest=list(latest.values()),source_sha256=digest(dict(actions=views,sequence=sequence)),
        sequence=sequence,reusable_public_observation=public_reuse or None,
        resolution='Use validated saved evidence for covered checks; pursue repair codes and remaining proof before repeating reads. Fresh rechecks require exact approval.',
        scope='Typed local action feedback only; no original requirement is automatically verified')
