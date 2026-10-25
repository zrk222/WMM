"""Request-local standing authority and commit/worker interlocks for fixed services."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
import json

from .common import Invalid, digest

ACTIVE = ContextVar('wmm_standing_execution', default=None)


def execution_row(db, identity):
    """Require an exact retained execution; identity never comes from an envelope."""
    row = db.execute('SELECT * FROM automation_executions WHERE id=?', (identity,)).fetchone()
    if row is None:
        raise PermissionError('Standing execution is unavailable')
    return row


def job_hash(job):
    """Bind immutable job intent separately from its changing status and lease."""
    return digest({key: job[key] for key in ('app_id', 'action', 'data', 'request_key')})


def guard_connection(path, db, committing=False):
    """Recheck policy inside the same transaction as a local business commit."""
    context = ACTIVE.get()
    if context is None:
        return
    if str(Path(path).resolve()) != context['store']:
        raise PermissionError('Standing execution cannot cross its local datastore')
    from .complete_automation import checked_policy, utc
    row = execution_row(db, context['id'])
    policy, _ = checked_policy(db, row['policy_id'], utc())
    if policy['version'] != row['policy_version']:
        raise PermissionError('Standing approval revision changed before commit')
    if context.get('job_id'):
        check_job(db, context, row)
    elif row['status'] != 'DISPATCHED':
        raise PermissionError('Standing execution was cancelled or already completed')
    if committing and db.in_transaction and db.total_changes:
        db.execute('UPDATE automation_executions SET write_commits=write_commits+1 WHERE id=?', (row['id'],))


def check_job(db, context, execution):
    """Cancelled, modified or replaced worker leases cannot inherit old authority."""
    row = db.execute('SELECT j.*,s.execution_id,s.request_hash FROM jobs j JOIN automation_job_scopes s ON s.job_id=j.id WHERE j.id=?', (context['job_id'],)).fetchone()
    if row is None or row['execution_id'] != execution['id'] or row['status'] != 'RUNNING' or row['attempts'] != context['attempt']:
        raise PermissionError('Standing job is cancelled or its worker lease changed')
    value = dict(row)
    value['data'] = json.loads(value['data'])
    if row['request_hash'] != job_hash(value):
        raise PermissionError('Standing job input changed after admission')


def attach_job(db, job, created):
    """Attach new owned jobs or retain an exact same-policy idempotent queue result."""
    context = ACTIVE.get()
    if context is None:
        return
    previous = db.execute('SELECT s.*,e.policy_id FROM automation_job_scopes s JOIN automation_executions e ON e.id=s.execution_id WHERE s.job_id=?', (job['id'],)).fetchone()
    if previous:
        original = execution_row(db, context['id'])
        if previous['policy_id'] != original['policy_id'] or previous['request_hash'] != job_hash(job):
            raise PermissionError('Existing job belongs to a different standing scope')
        return
    if not created:
        raise PermissionError('Standing scope cannot adopt an unrelated existing job')
    db.execute('INSERT INTO automation_job_scopes VALUES(?,?,?)', (job['id'], context['id'], job_hash(job)))


@contextmanager
def bound(store, identity, job=None):
    """Keep authority local to this request/worker and clear it even on failure."""
    value = dict(store=str(store.path.resolve()), id=identity)
    if job:
        value.update(job_id=job['id'], attempt=job['attempts'])
    token = ACTIVE.set(value)
    try:
        yield
    finally:
        ACTIVE.reset(token)


def start(store, admission, envelope):
    """Linearize dispatch against OFF and reject intent substitution or replay."""
    from .db import connection
    from .complete_automation import checked_policy, utc
    identity = admission['automation_execution_id']
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = execution_row(db, identity)
        checked_policy(db, row['policy_id'], utc())
        if row['grant_id'] != admission['grant_id'] or row['input_hash'] != digest(envelope) or row['status'] != 'ADMITTED':
            raise PermissionError('Standing dispatch binding changed or was already claimed')
        db.execute("UPDATE automation_executions SET status='DISPATCHED',updated=? WHERE id=?", (utc().isoformat(), identity))
    return identity


def finish(store, identity, result=None, error=None):
    """Persist outcome outside domain authority; partial failures stay uncertain."""
    from .db import connection
    from .complete_automation import utc
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        row = execution_row(db, identity)
        if row['status'] not in ('DISPATCHED', 'CANCEL_REQUESTED'):
            raise Invalid('Standing execution result is already recorded or was never dispatched')
        outcome = execution_outcome(row, error)
        try:
            result_hash = digest(result) if error is None else None
        except (TypeError, ValueError):
            result_hash, outcome = None, 'UNKNOWN'
        db.execute('UPDATE automation_executions SET status=?,result_hash=?,updated=? WHERE id=?', (outcome, result_hash, utc().isoformat(), identity))


def execution_outcome(row, error):
    """Separate known success, cancelled work and partial-write uncertainty decisions."""
    from .operation_outcome import EffectUncertain
    if error is None:
        return 'SUCCEEDED'
    if isinstance(error, EffectUncertain):
        return 'UNKNOWN'
    if row['status'] == 'CANCEL_REQUESTED':
        return 'UNKNOWN' if row['write_commits'] else 'CANCELLED'
    if isinstance(error, (Invalid, PermissionError, KeyError)) and not row['write_commits']:
        return 'FAILED'
    return 'UNKNOWN'


def execute_admitted(service, envelope, admission):
    """Use the fixed dispatcher with admitted context; legacy grants remain intact."""
    from .operation_runtime import execute
    from .video_edit_projects import admitted_caller
    with admitted_caller(admission):
        return dispatch_admitted(service, envelope, admission, execute)


def dispatch_admitted(service, envelope, admission, execute):
    """Retain exact admission and standing-write guards within the caller context."""
    if 'automation_execution_id' not in admission:
        return execute(service, envelope)
    identity = start(service.store, admission, envelope)
    try:
        with bound(service.store, identity):
            result = execute(service, envelope)
    except BaseException as error:
        finish(service.store, identity, error=error)
        raise
    finish(service.store, identity, result=result)
    return result


@contextmanager
def job_execution(store, job):
    """Workers inherit only their durable exact job scope, never ambient credentials."""
    from .db import connection
    from .complete_automation import checked_policy, utc, verify_access
    with connection(store.path) as db:
        row = db.execute('SELECT execution_id FROM automation_job_scopes WHERE job_id=?', (job['id'],)).fetchone()
        if row is not None:
            execution = execution_row(db, row['execution_id'])
            policy, summary = checked_policy(db, execution['policy_id'], utc())
            verify_access(store, policy['app_id'], summary['inventory']['selection']['agent_connection_id'])
    if row is None:
        yield
        return
    with bound(store, row['execution_id'], job):
        with connection(store.path):
            pass
        yield
