"""Finite admitted-Reel schedules using the existing campaign queue and worker."""
import json
from datetime import datetime, timezone

from .campaign_contract import exact
from .campaign_schedule import MAX_ITEMS, SCHEMA, audit, owner_context, validate_items
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .organic_video_policy import Policies, _authority, _saved, child_deadline
from . import campaign_video_execution as video

KIND = 'ADMITTED_ORGANIC_VIDEO_V1'
OPERATION = 'organic-video.intent-execute'


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)
        db.execute('''CREATE TABLE IF NOT EXISTS campaign_video_schedule_bindings(
            intent_id TEXT PRIMARY KEY, item_id TEXT NOT NULL UNIQUE,
            batch_id TEXT NOT NULL REFERENCES campaign_schedule_batches(id))''')


def current_intent(db, store, app_id, identity, policy, context):
    row = video._row(db, app_id, identity)
    request = json.loads(row['data'])['request']
    if (request['policy_id'], request['policy_hash']) != (policy['id'], policy['hash']):
        raise PermissionError('Scheduled Reel belongs to another policy')
    video._bound(db, store, app_id, row, context)
    if row['stage'] != 'NEW':
        raise Invalid('Only an unstarted admitted Reel can enter a new schedule')
    return row


def due_authority(db, app_id, policy, row, due):
    """Bound a new schedule by both the parent and this exact admission."""
    request = json.loads(row['data'])['request']
    admission = _saved(db.execute('SELECT * FROM organic_video_admissions WHERE app_id=? AND id=?',
                                  (app_id,request['admission_id'])).fetchone())
    if admission['hash'] != request['admission_hash']:
        raise Invalid('Scheduled admission changed')
    legacy = policy['data']['policy']['expires_at']
    child = child_deadline(admission['data'],legacy)
    parent = policy.get('permission_expires_at',legacy)
    expiry = min(iso_time(child),iso_time(parent))
    if not datetime.now(timezone.utc) < due < expiry:
        raise Invalid('Schedule the Reel after now and before its admission and permission expire')
    return expiry.isoformat()


def prepare_items(db, store, app_id, items, policy, context):
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise Invalid('Choose one through twenty admitted Reels')
    prepared, seen = [], set()
    for item in items:
        exact(item, ('due_at', 'intent_id'))
        due = iso_time(item['due_at'])
        row = current_intent(db, store, app_id, item['intent_id'], policy, context)
        expiry = due_authority(db,app_id,policy,row,due)
        if row['id'] in seen or db.execute('SELECT 1 FROM campaign_video_schedule_bindings WHERE intent_id=?', (row['id'],)).fetchone():
            raise Invalid('This Reel already has a retained schedule; inspect it instead of duplicating it')
        seen.add(row['id'])
        prepared.append(dict(item_id=uid(), due_at=due.isoformat(), operation=OPERATION,permission_expires_at=expiry,
                             request=dict(intent_id=row['id'], intent_hash=row['hash'])))
    return prepared


class VideoSchedules:
    def __init__(self, store):
        self.store = store
        initialize(store)

    def prepare(self, app_id, body):
        exact(body, ('policy_id', 'policy_hash', 'items'))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            context = _authority(db, self.store, app_id, 'organic-video.schedule-prepare', body, True)
            policy = Policies(self.store)._current(db, db.execute(
                'SELECT * FROM organic_video_policies WHERE app_id=? AND id=?', (app_id, body['policy_id'])).fetchone())
            if policy['hash'] != body['policy_hash'] or policy['data']['owner'] != context['principal']:
                raise PermissionError('Use the exact policy approved by this owner')
            items = prepare_items(db, self.store, app_id, body['items'], policy, context)
            identity, stamp = uid(), now()
            from .organic_video_monitor import CONFIG
            summary = dict(batch_id=identity, app_id=app_id, owner=context['principal'], kind=KIND, monitoring=dict(CONFIG),
                           scope_id=policy['id'], scope_hash=policy['hash'], items=items)
            db.execute('INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (identity, app_id, context['principal'], policy['id'], canonical(summary), digest(summary), 'DRAFT', 1, stamp, stamp))
            for item in items:
                db.execute('INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)',
                           (item['item_id'], identity, iso_time(item['due_at']).timestamp(), canonical(item), digest(item), 'DRAFT', None, stamp, stamp))
                db.execute('INSERT INTO campaign_video_schedule_bindings VALUES(?,?,?)',
                           (item['request']['intent_id'], item['item_id'], identity))
            audit(db, app_id, 'video_prepared', dict(batch_id=identity, summary_hash=digest(summary)))
        return dict(summary=summary, summary_hash=digest(summary), status='DRAFT')

    def activate(self, app_id, body):
        exact(body, ('batch_id', 'summary_hash'))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            context = _authority(db, self.store, app_id, 'organic-video.schedule-activate', body, True)
            row = batch(db, app_id, body['batch_id'], context['principal'])
            summary = json.loads(row['summary'])
            if row['status'] != 'DRAFT' or row['summary_hash'] != body['summary_hash']:
                raise Invalid('Review the exact current draft schedule before activation')
            policy = Policies(self.store)._current(db, db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?',
                                                                (app_id, summary['scope_id'])).fetchone())
            if policy['hash'] != summary['scope_hash']:
                raise Invalid('Scheduled policy changed')
            items = db.execute('SELECT * FROM campaign_schedule_items WHERE batch_id=?', (row['id'],)).fetchall()
            validate_items(items, summary)
            for item in summary['items']:
                intent = current_intent(db, self.store, app_id, item['request']['intent_id'], policy, context)
                expiry = due_authority(db,app_id,policy,intent,iso_time(item['due_at']))
                if item.get('permission_expires_at',expiry) != expiry:
                    raise Invalid('Scheduled admission deadline changed; review again')
                if intent['hash'] != item['request']['intent_hash'] or iso_time(item['due_at']) <= datetime.now(timezone.utc):
                    raise Invalid('The scheduled intent or due time needs review')
            db.execute("UPDATE campaign_schedule_batches SET status='ACTIVE',version=version+1,updated=? WHERE id=?", (now(), row['id']))
            db.execute("UPDATE campaign_schedule_items SET status='READY',updated=? WHERE batch_id=?", (now(), row['id']))
            audit(db, app_id, 'video_activated', dict(batch_id=row['id'], summary_hash=row['summary_hash']))
        return self.status(app_id, row['id'])

    def status(self, app_id, identity):
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            row = batch(db, app_id, identity, actor)
            summary = json.loads(row['summary'])
            validate_items(db.execute('SELECT * FROM campaign_schedule_items WHERE batch_id=?', (identity,)).fetchall(), summary, require_future=False)
            items = []
            for item in db.execute('SELECT * FROM campaign_schedule_items WHERE batch_id=? ORDER BY due,id', (identity,)):
                body = json.loads(item['body'])
                intent = video._view(video._row(db, app_id, body['request']['intent_id']))
                job = db.execute('SELECT status FROM jobs WHERE id=?', (item['job_id'],)).fetchone()
                from .organic_video_monitor import status as observation_status
                items.append(dict(item_id=item['id'], due_at=body['due_at'], status=item['status'], operation=OPERATION,
                                  job_id=item['job_id'], job_status=job['status'] if job else None, intent=intent,
                                  phase_checks=observation_status(db, app_id, item['id'])))
            return dict(id=row['id'], status=row['status'], version=row['version'], scope_id=row['scope_id'],
                        summary=summary, summary_hash=row['summary_hash'], items=items)


def batch(db, app_id, identity, actor):
    row = db.execute('SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=? AND owner=?',
                     (identity, app_id, actor)).fetchone()
    if row is None:
        raise Invalid('This video schedule is unavailable')
    summary = json.loads(row['summary'])
    if digest(summary) != row['summary_hash'] or summary.get('kind') != KIND:
        raise Invalid('Video schedule summary changed')
    return row
