"""Owner-opt-in, app-bound Apple Analytics refresh scheduling."""
import json
import re
import time

from .apple_analytics import identity as analytics_identity
from .common import Invalid, canonical, digest, iso_time, now, safe_data, uid
from .db import connection

MIN_INTERVAL_HOURS = 24
MAX_INTERVAL_HOURS = 168
MAX_FAILURES = 3
MAX_SCHEDULES_PER_TICK = 100


def configuration(body):
    """Validate a versioned schedule command without accepting source secrets."""
    safe_data(body)
    if not isinstance(body, dict) or type(body.get('enabled')) is not bool:
        raise Invalid('Choose whether Apple analytics refresh is enabled')
    if body['enabled']:
        if set(body) != {'enabled', 'interval_hours', 'report_id', 'version'}:
            raise Invalid('Choose the report, refresh interval and current schedule version')
        if type(body['interval_hours']) is not int or not MIN_INTERVAL_HOURS <= body['interval_hours'] <= MAX_INTERVAL_HOURS:
            raise Invalid('Choose a refresh interval from 24 to 168 hours')
        analytics_identity(body['report_id'])
    elif set(body) != {'enabled', 'version'}:
        raise Invalid('Pausing a schedule accepts only its current version')
    if body.get('version') is not None and type(body['version']) is not int:
        raise Invalid('Invalid Apple analytics schedule version')
    return body


def schedule_audit(db, app_id, operation, detail):
    """Write a bounded, secret-free local audit entry for schedule changes."""
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
        (app_id, 'apple_metrics.schedule.' + operation, canonical(detail), now()))


def cancel_queued(db, row):
    """Cancel only an unclaimed scheduled read when its owner pauses or replaces it."""
    if row and row['last_job']:
        db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=? AND status='QUEUED'",
                   (now(), row['app_id'], row['last_job']))


def source_state(db, row):
    """Check the current app/connection binding without returning its private fields."""
    app = db.execute('SELECT data,version FROM apps WHERE id=?', (row['app_id'],)).fetchone()
    if app is None or app['version'] != row['app_version']:
        return False, 'App changed; review the current Apple connection and refresh settings'
    app_data = json.loads(app['data'])
    if not app_data.get('store_app_id'):
        return False, 'App Store identity is missing; review the app settings'
    record = db.execute('SELECT version,data,hash,source FROM records WHERE app_id=? AND id=? AND kind=?',
                        (row['app_id'], row['connection_id'], 'connection')).fetchone()
    if record is None or record['version'] != row['connection_version']:
        return False, 'Apple connection changed; review the connection and refresh settings'
    binding = json.loads(record['data'])
    if (digest({'kind':'connection','data':binding,'source':record['source']}) != record['hash']
            or record['hash'] != row['connection_hash']
            or binding.get('provider') != 'app_store'
            or str(binding.get('store_app_id')) != str(app_data['store_app_id'])
            or binding.get('auth_mode') == 'disconnected'):
        return False, 'Apple connection changed; review the connection and refresh settings'
    return True, None


class AppleMetricsSchedules:
    """Persist one explicit owner schedule per app and dispatch through the worker."""
    def __init__(self, store):
        self.store = store

    def get(self, app_id):
        """Return schedule status and the latest job state without connection hashes."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            row = db.execute('SELECT * FROM apple_metrics_schedules WHERE app_id=?', (app_id,)).fetchone()
            return public_row(db, row)

    def save(self, app_id, body, *, commit_check=None):
        """Create, replace or pause an explicitly owner-approved app schedule."""
        self.store.app(app_id)
        body = configuration(body)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            if commit_check is not None:
                commit_check(db)
            old = db.execute('SELECT * FROM apple_metrics_schedules WHERE app_id=?', (app_id,)).fetchone()
            expected = old['version'] if old else None
            if body['version'] != expected:
                raise Invalid('Apple analytics schedule changed; reload before saving')
            if not body['enabled']:
                if old is None:
                    raise Invalid('There is no Apple analytics schedule to pause')
                cancel_queued(db, old)
                version = old['version'] + 1
                db.execute("UPDATE apple_metrics_schedules SET enabled=0,version=?,status='PAUSED',last_error=NULL,updated=? WHERE app_id=?",
                           (version, now(), app_id))
                schedule_audit(db, app_id, 'paused', {'schedule_id': old['id'], 'version': version})
            else:
                app = db.execute('SELECT data,version FROM apps WHERE id=?', (app_id,)).fetchone()
                if app is None:
                    raise Invalid('App is unavailable')
                app_data = json.loads(app['data'])
                store_app_id = app_data.get('store_app_id')
                if not isinstance(store_app_id, str) or not store_app_id.isdigit():
                    raise Invalid('Save this app\'s numeric App Store identity before scheduling analytics')
                candidates = []
                for record in db.execute('SELECT id,version,data,hash,source FROM records WHERE app_id=? AND kind=?',
                                         (app_id, 'connection')):
                    binding = json.loads(record['data'])
                    if (binding.get('provider') == 'app_store'
                            and str(binding.get('store_app_id')) == store_app_id
                            and binding.get('auth_mode') != 'disconnected'):
                        candidates.append((record, binding))
                if len(candidates) != 1:
                    raise Invalid('Connect exactly one current Apple App Store account for this app')
                record, binding = candidates[0]
                if digest({'kind':'connection','data':binding,'source':record['source']}) != record['hash']:
                    raise Invalid('Apple connection failed its integrity check; reconnect before scheduling')
                if old:
                    cancel_queued(db, old)
                schedule_id = old['id'] if old else uid()
                version = (expected or 0) + 1
                due = time.time()
                db.execute('''INSERT INTO apple_metrics_schedules
                    (app_id,id,connection_id,connection_version,connection_hash,app_version,report_id,
                     interval_hours,enabled,version,next_due,last_due,last_job,reconciled_job,failures,
                     status,last_success,last_error,updated)
                    VALUES(?,?,?,?,?,?,?,?,1,?,?,NULL,NULL,NULL,0,'ENABLED',NULL,NULL,?)
                    ON CONFLICT(app_id) DO UPDATE SET id=excluded.id,connection_id=excluded.connection_id,
                     connection_version=excluded.connection_version,connection_hash=excluded.connection_hash,
                     app_version=excluded.app_version,report_id=excluded.report_id,
                     interval_hours=excluded.interval_hours,enabled=1,version=excluded.version,
                     next_due=excluded.next_due,last_due=NULL,last_job=NULL,reconciled_job=NULL,
                     failures=0,status='ENABLED',last_error=NULL,updated=excluded.updated''',
                    (app_id, schedule_id, record['id'], record['version'], record['hash'], app['version'],
                     body['report_id'], body['interval_hours'], version, due, now()))
                schedule_audit(db, app_id, 'enabled', {'schedule_id': schedule_id,
                    'version': version, 'report_id': body['report_id'],
                    'interval_hours': body['interval_hours']})
        return self.get(app_id)

    def tick(self):
        """Reconcile current jobs, reject stale sources, and queue at most 100 due reads."""
        count = 0
        current = time.time()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT * FROM apple_metrics_schedules WHERE enabled=1 ORDER BY next_due LIMIT ?',
                              (MAX_SCHEDULES_PER_TICK,)).fetchall()
            for row in rows:
                valid, reason = source_state(db, row)
                if not valid:
                    disable(db, row, 'CONNECTION_CHANGED', reason)
                    continue
                if not reconcile(db, row):
                    continue
                fresh = db.execute('SELECT * FROM apple_metrics_schedules WHERE app_id=?',
                                   (row['app_id'],)).fetchone()
                if fresh and fresh['enabled'] and fresh['next_due'] <= current:
                    dispatch(db, fresh, current)
                    count += 1
        return count


def public_row(db, row):
    """Expose useful durable status but omit connection hashes and credential references."""
    if row is None:
        return None
    result = {key: row[key] for key in ('app_id','id','connection_version','app_version','report_id',
        'interval_hours','version','next_due','last_due','last_job','reconciled_job','failures',
        'status','last_success','last_error','updated')}
    result['enabled'] = bool(row['enabled'])
    job = db.execute('SELECT status FROM jobs WHERE app_id=? AND id=?', (row['app_id'], row['last_job'])).fetchone() if row['last_job'] else None
    result['last_job_status'] = job['status'] if job else None
    return result


def disable(db, row, status, reason):
    """Stop future reads while preserving the last job and explaining recovery."""
    cancel_queued(db, row)
    db.execute('UPDATE apple_metrics_schedules SET enabled=0,status=?,last_error=?,updated=? WHERE app_id=?',
               (status, reason[:240], now(), row['app_id']))
    schedule_audit(db, row['app_id'], 'disabled', {'schedule_id': row['id'], 'status': status})


WAITING_FIELDS = {'schema','status','operation','provider','app_id','store_app_id','connection_id',
                  'connection_version','report_id','report_family','granularity','coverage',
                  'metadata_source_hash','connection_hash','observed_at','metric_observations','external_writes'}


def waiting_marker(result):
    return isinstance(result, dict) and (result.get('status') == 'WAITING_FOR_REPORTS'
        or result.get('schema') == 'wmm.apple_metrics.waiting.v1')


def valid_waiting(db, row, job, result):
    """Accept only a complete waiting result bound to this still-current scheduled job."""
    try:
        if not isinstance(result, dict) or set(result) != WAITING_FIELDS:
            return False
        check_scheduled_db(db, job)
        app = db.execute('SELECT data FROM apps WHERE id=?', (row['app_id'],)).fetchone()
        record = db.execute('SELECT data FROM records WHERE app_id=? AND id=? AND kind=?',
                            (row['app_id'], row['connection_id'], 'connection')).fetchone()
        if app is None or record is None:
            return False
        app_data, binding = json.loads(app['data']), json.loads(record['data'])
        if (result['schema'] != 'wmm.apple_metrics.waiting.v1' or result['status'] != 'WAITING_FOR_REPORTS'
                or result['operation'] != 'analytics_metrics_latest' or result['provider'] != 'app_store'
                or result['app_id'] != row['app_id'] or result['store_app_id'] != app_data.get('store_app_id')
                or result['connection_id'] != row['connection_id']
                or type(result['connection_version']) is not int or result['connection_version'] != row['connection_version']
                or result['report_id'] != row['report_id'] or result['report_family'] != 'App Downloads Standard'
                or result['granularity'] != 'DAILY' or result['coverage'] != 'COMPLETE'
                or result['metric_observations'] is not None or result['external_writes'] is not False
                or result['connection_hash'] != digest(binding)
                or not isinstance(result['metadata_source_hash'], str)
                or not re.fullmatch(r'[0-9a-f]{64}', result['metadata_source_hash'])):
            return False
        iso_time(result['observed_at'])
        return True
    except (Invalid, TypeError, ValueError, KeyError, AttributeError):
        return False


def valid_numeric(db, row, job, result):
    """Recognize only an actual complete downloads partition summary as numeric success."""
    try:
        if not isinstance(result, dict):
            return False
        check_scheduled_db(db, job)
        app = db.execute('SELECT data FROM apps WHERE id=?', (row['app_id'],)).fetchone()
        if app is None:
            return False
        if (result.get('operation') != 'analytics_metrics_latest' or result.get('provider') != 'app_store'
                or result.get('app_id') != row['app_id']
                or result.get('store_app_id') != json.loads(app['data']).get('store_app_id')
                or result.get('report_id') != row['report_id'] or result.get('report_family') != 'App Downloads Standard'
                or result.get('granularity') != 'DAILY' or result.get('coverage') != 'COMPLETE'
                or result.get('external_writes') is not False or type(result.get('partition_count')) is not int
                or result['partition_count'] < 1 or not isinstance(result.get('partitions'), list)
                or len(result['partitions']) != result['partition_count']
                or type(result.get('observation_count')) is not int or result['observation_count'] < 0
                or not isinstance(result.get('metadata_source_hash'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', result['metadata_source_hash'])):
            return False
        iso_time(result.get('observed_at'))
        return True
    except (Invalid, TypeError, ValueError, KeyError, AttributeError):
        return False


def reconcile(db, row):
    """Apply each terminal job result once and stop after three consecutive failures."""
    if not row['last_job']:
        return True
    job = db.execute('SELECT * FROM jobs WHERE app_id=? AND id=?',
                     (row['app_id'], row['last_job'])).fetchone()
    if job is None:
        disable(db, row, 'BLOCKED', 'Scheduled job record is missing; review before resuming')
        return False
    if job['status'] in ('QUEUED', 'RUNNING'):
        return False
    if row['reconciled_job'] == row['last_job']:
        return True
    try:
        result = json.loads(job['result'] or '{}')
        job_input = json.loads(job['data'])
    except (TypeError, ValueError):
        result, job_input = {}, {}
    job_data = dict(job)
    job_data['data'] = job_input
    success = job['status'] == 'SUCCEEDED' and (valid_waiting(db, row, job_data, result) if waiting_marker(result)
                                                 else valid_numeric(db, row, job_data, result))
    failures = 0 if success else row['failures'] + 1
    last_error = None if success else safe_failure(result)
    status = 'ENABLED' if failures < MAX_FAILURES else 'BLOCKED'
    enabled = int(failures < MAX_FAILURES and job['status'] != 'CANCELLED')
    if job['status'] == 'CANCELLED':
        status = 'PAUSED'
    db.execute('UPDATE apple_metrics_schedules SET failures=?,reconciled_job=?,last_error=?,enabled=?,status=?,updated=? WHERE app_id=?',
        (failures, row['last_job'], last_error, enabled, status, now(), row['app_id']))
    schedule_audit(db, row['app_id'], 'reconciled', {'job_id': row['last_job'],
        'status': 'INVALID_RESULT' if job['status'] == 'SUCCEEDED' and not success else job['status'], 'failures': failures})
    return bool(enabled)


def dispatch(db, row, current):
    """Enqueue a source-bound latest-instance read and move its next due time atomically."""
    data = {'connection_id': row['connection_id'], 'connection_version': row['connection_version'],
        'manifest_version': row['app_version'], 'analytics_schedule_id': row['id'],
        'analytics_schedule_version': row['version'], 'analytics_schedule_due': row['next_due'],
        'options': {'operation': 'analytics_metrics_latest', 'report_id': row['report_id']}}
    request_key = 'apple-metrics-schedule-' + digest({'app_id': row['app_id'], 'schedule_id': row['id'],
        'schedule_version': row['version'], 'due': row['next_due']})
    job_id = uid()
    stamp = now()
    db.execute('INSERT OR IGNORE INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
        (job_id, row['app_id'], 'sync', canonical(data), 'QUEUED', stamp, stamp, request_key))
    saved = db.execute('SELECT id FROM jobs WHERE app_id=? AND request_key=?',
                       (row['app_id'], request_key)).fetchone()['id']
    interval = row['interval_hours'] * 3600
    db.execute('UPDATE apple_metrics_schedules SET last_due=?,last_job=?,next_due=?,updated=? WHERE app_id=?',
        (row['next_due'], saved, current + interval, stamp, row['app_id']))
    schedule_audit(db, row['app_id'], 'queued', {'job_id': saved, 'request_key': request_key})


def check_scheduled_db(db, job):
    """Require the exact still-enabled schedule before provider access or persistence."""
    data = job['data']
    schedule_id = data.get('analytics_schedule_id')
    if not schedule_id:
        return None
    required = {'analytics_schedule_id','analytics_schedule_version','analytics_schedule_due'}
    if not required.issubset(data):
        raise Invalid('Scheduled Apple analytics input is incomplete')
    row = db.execute('SELECT * FROM apple_metrics_schedules WHERE app_id=? AND id=?',
                     (job['app_id'], schedule_id)).fetchone()
    options = data.get('options')
    if (row is None or not row['enabled'] or row['status'] != 'ENABLED'
            or row['version'] != data['analytics_schedule_version']
            or row['last_job'] != job['id'] or row['last_due'] != data['analytics_schedule_due']
            or row['connection_id'] != data.get('connection_id')
            or row['connection_version'] != data.get('connection_version')
            or row['app_version'] != data.get('manifest_version')
            or not isinstance(options, dict)
            or options != {'operation':'analytics_metrics_latest','report_id':row['report_id']}):
        raise Invalid('Apple analytics schedule changed; owner review is required before retrying')
    valid, reason = source_state(db, row)
    if not valid:
        raise Invalid(reason)
    if row['last_due'] > time.time():
        raise Invalid('Apple analytics schedule is not due')
    return row


def check_scheduled(store, job):
    """Read-check schedule authority outside provider time; caller rechecks at commit."""
    if 'analytics_schedule_id' not in job['data']:
        return None
    with connection(store.path) as db:
        return check_scheduled_db(db, job)


def complete_job(db, job, result, status):
    """Record scheduled success/failure with the durable job's terminal state."""
    data = job['data']
    schedule_id = data.get('analytics_schedule_id')
    if not schedule_id or status == 'RUNNING':
        return
    row = db.execute('SELECT * FROM apple_metrics_schedules WHERE app_id=? AND id=?',
                     (job['app_id'], schedule_id)).fetchone()
    if (row is None or row['last_job'] != job['id']
            or row['version'] != data.get('analytics_schedule_version')):
        return
    if not row['enabled']:
        return
    if status == 'SUCCEEDED':
        if waiting_marker(result):
            if valid_waiting(db, row, job, result):
                db.execute("UPDATE apple_metrics_schedules SET failures=0,reconciled_job=?,last_error=NULL,status='ENABLED',updated=? WHERE app_id=?",
                    (job['id'], now(), job['app_id']))
                schedule_audit(db, job['app_id'], 'waiting', {'job_id': job['id'], 'status': 'WAITING_FOR_REPORTS'})
                return
            result = {'error':'Scheduled Apple analytics waiting result failed its source check'}
            status = 'BLOCKED'
        elif valid_numeric(db, row, job, result):
            db.execute("UPDATE apple_metrics_schedules SET failures=0,reconciled_job=?,last_success=?,last_error=NULL,status='ENABLED',updated=? WHERE app_id=?",
                (job['id'], now(), now(), job['app_id']))
            schedule_audit(db, job['app_id'], 'completed', {'job_id': job['id'], 'status': status})
            return
        else:
            result = {'error':'Scheduled Apple analytics result failed its source check'}
            status = 'BLOCKED'
    if status == 'CANCELLED':
        disable(db, row, 'PAUSED', 'Scheduled read was cancelled; review the schedule before resuming')
        return
    valid, reason = source_state(db, row)
    if not valid:
        disable(db, row, 'CONNECTION_CHANGED', reason)
        return
    failures = row['failures'] + 1
    blocked = failures >= MAX_FAILURES
    message = safe_failure(result)
    db.execute('UPDATE apple_metrics_schedules SET failures=?,reconciled_job=?,last_error=?,enabled=?,status=?,updated=? WHERE app_id=?',
        (failures, job['id'], message, int(not blocked), 'BLOCKED' if blocked else 'ENABLED', now(), job['app_id']))
    schedule_audit(db, job['app_id'], 'failed', {'job_id': job['id'], 'failures': failures,
        'status': 'BLOCKED' if blocked else 'ENABLED'})


def safe_failure(result):
    """Keep only a short, control-character-free error summary in schedule state."""
    value = result.get('error') if isinstance(result, dict) else None
    if not isinstance(value, str) or not value:
        return 'Scheduled Apple analytics read failed; review the job before retrying'
    return ''.join(char for char in value if char >= ' ' and char not in '\x7f')[:240]
