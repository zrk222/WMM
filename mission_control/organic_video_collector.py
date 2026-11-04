"""Durable external-agent research task; never performs internet access itself."""
from datetime import datetime, timedelta, timezone
import json

from .agent_grants import app_scope, current
from .common import Invalid, canonical, digest, iso_time, now, safe_data, uid
from .db import connection
from .operation_authority import PROTECTED, check, store_identity
from .organic_video_discovery import discovery_task, exact, qualify_submission
from .review_access import exact_role
from .store import audit


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS organic_discovery_tasks (
        id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL, task TEXT NOT NULL, task_hash TEXT NOT NULL,
        owner TEXT NOT NULL, owner_version INTEGER NOT NULL, grant_id TEXT NOT NULL REFERENCES agent_grants(id),
        grant_version INTEGER NOT NULL, status TEXT NOT NULL, claim_id TEXT, claimed_at TEXT, claim_until TEXT,
        submission TEXT, submission_hash TEXT, result TEXT, result_hash TEXT, created TEXT NOT NULL, updated TEXT NOT NULL,
        UNIQUE(app_id, request_id))''')


def _authorized(db, store, app_id, actor, body, operation, agent):
    """Derive identity from the protected gateway context, never from request data."""
    context = PROTECTED.get()
    if not context or context.get('store') != store_identity(store):
        raise PermissionError('Current protected operation is required')
    envelope = json.loads(context['envelope'])
    if (envelope.get('app_id') != app_id or envelope.get('operation') != operation
            or envelope.get('input') != body or ('grant_id' in context) != agent):
        raise PermissionError('Discovery operation does not match its protected admission')
    identity = check(db, context)
    if identity != actor:
        raise PermissionError('Caller identity differs from protected admission')
    return context


def _row(db, app_id, identity):
    row = db.execute('SELECT * FROM organic_discovery_tasks WHERE app_id=? AND id=?',
                     (app_id, identity)).fetchone()
    if not row:
        raise Invalid('Discovery task is unavailable')
    return row


def _current(db, row, observed):
    task = json.loads(row['task'])
    if digest(task) != row['task_hash']:
        raise Invalid('Discovery task integrity changed')
    if iso_time(task['policy']['expires']) <= observed:
        raise PermissionError('Discovery task expired')
    if app_scope(db, row['app_id']) != (task['app']['version'], task['app']['hash']):
        raise PermissionError('Discovery app context changed')
    exact_role(db, row['app_id'], row['owner'], row['owner_version'], 'OWNER')
    grant = db.execute('SELECT * FROM agent_grants WHERE id=?', (row['grant_id'],)).fetchone()
    if not grant or grant['version'] != row['grant_version'] or grant['owner'] != row['owner']:
        raise PermissionError('Discovery recipient authority changed')
    for name in ('organic-video.claim', 'organic-video.submit'):
        current(db, grant, {'app_id': row['app_id'], 'operation': name}, observed, check_quota=False)
    return task, grant


def _view(row):
    value = {'id': row['id'], 'app_id': row['app_id'], 'task_hash': row['task_hash'],
             'task': json.loads(row['task']), 'status': row['status'],
             'claim_id': row['claim_id'], 'claim_until': row['claim_until'],
             'submission_hash': row['submission_hash'],
             'result': json.loads(row['result']) if row['result'] else None,
             'provider_access': 'EXTERNAL_AGENT_NOT_VERIFIED', 'publication': 'NOT_RUN'}
    if digest(value['task']) != row['task_hash']:
        raise Invalid('Discovery task integrity changed')
    if row['submission_hash']:
        if (not row['submission'] or digest(json.loads(row['submission'])) != row['submission_hash']
                or value['result'] is None or digest(value['result']) != row['result_hash']):
            raise Invalid('Discovery submission or result integrity changed')
    return value


def prepare(store, app_id, actor, body) -> object:
    """Owner prepares a task for an existing owner-issued external-agent grant."""
    exact(body, ('request_id', 'query', 'policy'))
    safe_data(body)
    if not isinstance(body['request_id'], str) or not 1 <= len(body['request_id']) <= 120:
        raise Invalid('Use a bounded request identity')
    observed = datetime.now(timezone.utc)
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        context = _authorized(db, store, app_id, actor, body, 'organic-video.prepare', False)
        version, app_hash = app_scope(db, app_id)
        task = discovery_task({'id': app_id, 'version': version, 'hash': app_hash},
                              body['policy'], body['query'])
        grant = db.execute('SELECT * FROM agent_grants WHERE id=?',
                           (task['policy']['recipient_grant_id'],)).fetchone()
        if not grant or grant['owner'] != context['principal'] or grant['app_id'] != app_id:
            raise PermissionError('Choose an existing owner-issued recipient grant')
        for name in ('organic-video.claim', 'organic-video.submit'):
            current(db, grant, {'app_id': app_id, 'operation': name}, observed, check_quota=False)
        if iso_time(task['policy']['expires']) > iso_time(grant['expires']):
            raise PermissionError('Discovery task cannot outlast its recipient grant')
        _schema(db)
        prior = db.execute('SELECT * FROM organic_discovery_tasks WHERE app_id=? AND request_id=?',
                           (app_id, body['request_id'])).fetchone()
        if prior:
            if prior['request_hash'] != digest(body):
                raise Invalid('Discovery request identity was used for different input')
            _current(db, prior, observed)
            return _view(prior)
        identity = uid()
        stamp = now()
        db.execute('''INSERT INTO organic_discovery_tasks
            (id,app_id,request_id,request_hash,task,task_hash,owner,owner_version,grant_id,
             grant_version,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (identity, app_id, body['request_id'], digest(body), canonical(task), digest(task),
             context['principal'], context['role_version'], grant['id'], grant['version'],
             'READY', stamp, stamp))
        audit(db, app_id, 'organic_discovery.prepared', {'task_id': identity, 'task_hash': digest(task)})
        return _view(_row(db, app_id, identity))


def claim(store, app_id, actor, body) -> object:
    """Recipient claims exactly one task with a bounded, non-transferable lease."""
    exact(body, ('task_id', 'task_hash'))
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        context = _authorized(db, store, app_id, actor, body, 'organic-video.claim', True)
        _schema(db)
        row = _row(db, app_id, body['task_id'])
        observed = datetime.now(timezone.utc)
        task, grant = _current(db, row, observed)
        if row['task_hash'] != body['task_hash'] or context['grant_id'] != grant['id']:
            raise PermissionError('Discovery task or recipient changed')
        if row['status'] == 'CLAIMED':
            if iso_time(row['claim_until']) <= observed:
                raise PermissionError('Discovery claim expired; prepare a new task')
            return _view(row)
        if row['status'] != 'READY':
            raise Invalid('Discovery task is no longer available to claim')
        until = min(observed + timedelta(seconds=task['policy']['max_seconds']),
                    iso_time(task['policy']['expires']), iso_time(grant['expires']))
        db.execute("UPDATE organic_discovery_tasks SET status='CLAIMED',claim_id=?,claimed_at=?,claim_until=?,updated=? WHERE id=? AND status='READY'",
                   (uid(), observed.isoformat(), until.isoformat(), now(), row['id']))
        audit(db, app_id, 'organic_discovery.claimed', {'task_id': row['id'], 'grant_id': grant['id']})
        return _view(_row(db, app_id, row['id']))


def submit(store, app_id, actor, body) -> object:
    """Save exact task-bound observations once; claims never prove independent verification."""
    exact(body, ('task_id', 'result'))
    safe_data(body)
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        context = _authorized(db, store, app_id, actor, body, 'organic-video.submit', True)
        _schema(db)
        row = _row(db, app_id, body['task_id'])
        observed = datetime.now(timezone.utc)
        task, grant = _current(db, row, observed)
        if context['grant_id'] != grant['id']:
            raise PermissionError('Discovery task belongs to another agent grant')
        result = body['result']
        if not isinstance(result, dict) or result.get('task_id') != row['id'] or result.get('claim_id') != row['claim_id']:
            raise PermissionError('Submission does not match the active claim')
        if row['submission_hash']:
            if row['submission_hash'] != digest(result):
                raise Invalid('Claim already has a different saved submission')
            return _view(row)
        if row['status'] != 'CLAIMED' or iso_time(row['claim_until']) <= observed:
            raise PermissionError('Discovery claim is unavailable or expired')
        if iso_time(result.get('collected_at')) < iso_time(row['claimed_at']):
            raise Invalid('Collection must occur after the claim')
        qualified = qualify_submission(task, result)
        for item in result['candidates']:
            for observation in (item['candidate'], *item['history']):
                if iso_time(observation['observed_at']) < iso_time(row['claimed_at']):
                    raise Invalid('Each source observation must be made after the claim')
        observed = datetime.now(timezone.utc)
        _current(db, row, observed)
        if iso_time(row['claim_until']) <= observed:
            raise PermissionError('Discovery claim expired before submission commit')
        incomplete = bool(result['failures']) or any(
            item['status'] == 'INSUFFICIENT_BASELINE' for item in qualified['items'])
        status = 'INCOMPLETE' if incomplete else 'SUBMITTED'
        db.execute('''UPDATE organic_discovery_tasks SET status=?,submission=?,submission_hash=?,result=?,result_hash=?,updated=?
                      WHERE id=? AND status='CLAIMED' ''',
                   (status, canonical(result), digest(result), canonical(qualified), digest(qualified), now(), row['id']))
        audit(db, app_id, 'organic_discovery.submitted', {'task_id': row['id'],
              'submission_hash': digest(result), 'status': status})
        return _view(_row(db, app_id, row['id']))
