"""Finite owner-reviewed Page post and existing-post promotion schedules."""
import json
import time
from datetime import datetime, timezone

from .campaign_contract import ad_data, post_data
from .campaign_execution import CampaignExecutionService, row_scope
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .review_access import member

MAX_ITEMS = 20
SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_schedule_batches (
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL, owner TEXT NOT NULL, scope_id TEXT NOT NULL,
 summary TEXT NOT NULL, summary_hash TEXT NOT NULL, status TEXT NOT NULL,
 version INTEGER NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaign_schedule_items (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES campaign_schedule_batches(id),
 due REAL NOT NULL, body TEXT NOT NULL, body_hash TEXT NOT NULL,
 status TEXT NOT NULL, job_id TEXT UNIQUE, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS campaign_schedule_due ON campaign_schedule_items(status,due);
"""


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)


def owner_context(store, app_id):
    from .campaign_access import identity
    context, actor = identity(store, app_id)
    if 'principal' not in context:
        raise PermissionError('A freshly authenticated owner is required')
    return actor


def checked_scope(db, service, app_id, actor, scope_id):
    row = service._row(db, app_id, scope_id)
    scope = row_scope(row)
    if scope['owner_principal'] != actor:
        raise PermissionError('Campaign scope belongs to another owner')
    service._check(db, app_id, actor, scope, 'RUN_POST')
    return scope


def prepare_items(items, scope, db, app_id):
    prepared, seen = [], set()
    for item in items:
        due, operation, post = prepare_item(item, scope, db, app_id)
        if post['request_id'] in seen:
            raise Invalid('Scheduled request identities must be unique')
        seen.add(post['request_id'])
        value = dict(item_id=uid(), due_at=due.isoformat(), request=post)
        if 'operation' in item:
            value['operation'] = operation
        prepared.append(value)
    return prepared


def prepare_item(item, scope, db, app_id):
    if not isinstance(item, dict) or set(item) not in ({'due_at', 'request'}, {'due_at', 'request', 'operation'}):
        raise Invalid('Each scheduled item needs an exact due time and post')
    due = iso_time(item['due_at'])
    if not datetime.now(timezone.utc) < due < iso_time(scope['expires_at']):
        raise Invalid('Scheduled post must be due before scope expiry')
    operation = item.get('operation', 'campaign.publish')
    if operation not in ('campaign.publish', 'campaign.ad-launch'):
        raise Invalid('Unsupported scheduled campaign operation')
    post = ad_data(item['request']) if operation == 'campaign.ad-launch' else post_data(item['request'])
    if (post['content_hash'] not in scope['approved_content_hashes']
            or post['rights_hash'] not in scope['approved_rights_hashes']):
        raise PermissionError('Scheduled post is outside campaign approval')
    if operation == 'campaign.ad-launch':
        check_paid_review(db, app_id, scope, post, due)
    return due, operation, post


def check_paid_review(db, app_id, scope, body, due):
    if (not scope['ad_account_id'] or body['targeting_hash'] not in scope['approved_targeting_hashes']
            or body['lifetime_budget_minor'] > scope['max_campaign_minor']
            or body['lifetime_budget_minor'] > scope['max_total_minor']
            or not due < iso_time(body['end_time']) <= iso_time(scope['expires_at'])):
        raise PermissionError('Paid promotion exceeds the approved scope')
    post = db.execute("""SELECT 1 FROM campaign_intents WHERE app_id=? AND page_id=? AND remote_id=?
        AND status='VERIFIED' AND content_hash=? AND rights_hash=?""",
        (app_id, scope['page_id'], body['post_id'], body['content_hash'], body['rights_hash'])).fetchone()
    if post is None:
        raise PermissionError('Schedule only a verified saved Page post')


def validate_items(rows, summary, *, require_future=True):
    if len(rows) != len(summary['items']):
        raise Invalid('Scheduled items changed or are no longer in the future')
    for item in rows:
        body = json.loads(item['body'])
        if (digest(body) != item['body_hash'] or body not in summary['items']
                or item['id'] != body['item_id']
                or item['due'] != iso_time(body['due_at']).timestamp()
                or (require_future and item['due'] <= time.time())):
            raise Invalid('Scheduled items changed or are no longer in the future')


class CampaignSchedules:
    def __init__(self, store):
        self.store = store
        initialize(store)

    def prepare(self, app_id, body):
        actor = owner_context(self.store, app_id)
        if not isinstance(body, dict) or set(body) != {'scope_id', 'items'}:
            raise Invalid('Provide the exact campaign scope and scheduled items')
        items = body['items']
        if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
            raise Invalid('Choose one to twenty scheduled posts')
        from .campaign_access import policy_checker
        service = CampaignExecutionService(self.store, policy_checker(self.store))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            scope = checked_scope(db, service, app_id, actor, body['scope_id'])
            identity = uid()
            prepared = prepare_items(items, scope, db, app_id)
            if any(item.get('operation') == 'campaign.ad-launch' for item in prepared):
                service._check(db, app_id, actor, scope, 'RUN_AD')
            summary = dict(batch_id=identity, app_id=app_id, owner=actor,
                           scope_id=scope['scope_id'], scope_hash=scope['approval_hash'], items=prepared)
            stamp = now()
            db.execute('INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)',
                (identity, app_id, actor, scope['scope_id'], canonical(summary), digest(summary), 'DRAFT', 1, stamp, stamp))
            for item in prepared:
                db.execute('INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)',
                    (item['item_id'], identity, iso_time(item['due_at']).timestamp(), canonical(item),
                     digest(item), 'DRAFT', None, stamp, stamp))
            audit(db, app_id, 'prepared', dict(batch_id=identity, summary_hash=digest(summary)))
        return dict(summary=summary, summary_hash=digest(summary), status='DRAFT')

    def activate(self, app_id, batch_id, summary_hash):
        actor = owner_context(self.store, app_id)
        from .campaign_access import policy_checker
        service = CampaignExecutionService(self.store, policy_checker(self.store))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=?', (batch_id, app_id)).fetchone()
            if row is None or row['owner'] != actor or row['status'] != 'DRAFT':
                raise Invalid('Scheduled batch is unavailable for activation')
            summary = json.loads(row['summary'])
            scope = checked_scope(db, service, app_id, actor, row['scope_id'])
            if (digest(summary) != row['summary_hash'] or summary_hash != row['summary_hash']
                    or scope['approval_hash'] != summary['scope_hash']):
                raise Invalid('Scheduled batch or scope changed; review again')
            rows = db.execute('SELECT * FROM campaign_schedule_items WHERE batch_id=?', (batch_id,)).fetchall()
            validate_items(rows, summary)
            db.execute("UPDATE campaign_schedule_batches SET status='ACTIVE',version=version+1,updated=? WHERE id=?", (now(), batch_id))
            db.execute("UPDATE campaign_schedule_items SET status='READY',updated=? WHERE batch_id=?", (now(), batch_id))
            audit(db, app_id, 'activated', dict(batch_id=batch_id, summary_hash=summary_hash))
        return self.status(app_id, batch_id)

    def status(self, app_id, batch_id):
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            row = db.execute('SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=? AND owner=?',
                             (batch_id, app_id, actor)).fetchone()
            if row is None:
                raise Invalid('Scheduled batch is unavailable')
            summary = json.loads(row['summary'])
            if digest(summary) != row['summary_hash']:
                raise Invalid('Scheduled batch summary needs repair')
            if summary.get('kind') == 'ADMITTED_ORGANIC_VIDEO_V1':
                from .organic_video_schedule import VideoSchedules
                return VideoSchedules(self.store).status(app_id, batch_id)
            items = []
            for item in db.execute('SELECT * FROM campaign_schedule_items WHERE batch_id=? ORDER BY due,id', (batch_id,)):
                items.append(item_status(db, app_id, row['scope_id'], item))
            return dict(id=row['id'], status=row['status'], version=row['version'],
                        scope_id=row['scope_id'], summary=summary,
                        summary_hash=row['summary_hash'], items=items)

    def history(self, app_id):
        """Return the latest 50 owner-owned batches with saved local receipt state."""
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            ids = [row['id'] for row in db.execute(
                'SELECT id FROM campaign_schedule_batches WHERE app_id=? AND owner=? ORDER BY created DESC,id DESC LIMIT 50',
                (app_id, actor))]
        return {'batches': [self.status(app_id, identity) for identity in ids]}

    def revoke(self, app_id, batch_id, version):
        actor = owner_context(self.store, app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            member(db, app_id, actor, 'OWNER')
            row = db.execute('SELECT * FROM campaign_schedule_batches WHERE id=? AND app_id=? AND owner=?',
                             (batch_id, app_id, actor)).fetchone()
            if row is None or type(version) is not int or row['version'] != version:
                raise Invalid('Scheduled batch revision changed; reload')
            db.execute("UPDATE campaign_schedule_batches SET status='OFF',version=version+1,updated=? WHERE id=?", (now(), batch_id))
            db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE status='QUEUED' AND id IN (SELECT job_id FROM campaign_schedule_items WHERE batch_id=?)", (now(), batch_id))
            db.execute("UPDATE campaign_schedule_items SET status='CANCELLED',updated=? WHERE batch_id=? AND status IN ('READY','DRAFT')", (now(), batch_id))
            audit(db, app_id, 'off', dict(batch_id=batch_id, version=version+1))
        return self.status(app_id, batch_id)


def audit(db, app_id, action, detail):
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
               (app_id, 'campaign_schedule.' + action, canonical(detail), now()))


def item_status(db, app_id, scope_id, item):
    job = db.execute('SELECT status,result FROM jobs WHERE id=?', (item['job_id'],)).fetchone() if item['job_id'] else None
    body = json.loads(item['body'])
    operation = body.get('operation', 'campaign.publish')
    if operation == 'campaign.ad-launch':
        intent = db.execute('SELECT id,status,ids,commitment,currency FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND request_id=? AND request_hash=?',
                            (app_id, scope_id, body['request']['request_id'], digest(body['request']))).fetchone()
    else:
        intent = db.execute('SELECT id,status,remote_id FROM campaign_intents WHERE app_id=? AND scope_id=? AND request_id=? AND request_hash=?',
                            (app_id, scope_id, body['request']['request_id'], digest(body['request']))).fetchone()
    intent = dict(intent) if intent else None
    if intent and 'ids' in intent:
        intent['ids'] = json.loads(intent['ids'])
    return dict(item_id=item['id'], due_at=body['due_at'], status=item['status'],
                operation=operation, effective_status=effective_status(item['status'], job, intent, operation),
                job_id=item['job_id'], job_status=job['status'] if job else None, intent=intent)


def effective_status(item_status, job, intent, operation):
    if intent:
        state = intent['status']
        if state == 'VERIFIED' and operation == 'campaign.publish':
            return 'VERIFIED'
        if state == 'ACTIVE_campaign' and operation == 'campaign.ad-launch':
            return 'ACTIVE_VERIFIED'
        if state == 'PAUSED_campaign':
            return 'PAUSED_VERIFIED'
        if job and job['status'] == 'RUNNING':
            return 'RUNNING'
        return 'NEEDS_RECONCILIATION'
    if job:
        return {'QUEUED':'QUEUED','RUNNING':'RUNNING','CANCELLED':'CANCELLED',
                'BLOCKED':'BLOCKED','FAILED':'BLOCKED','SUCCEEDED':'NEEDS_RECONCILIATION'}.get(job['status'], 'BLOCKED')
    return item_status


def tick(store):
    """Atomically enqueue each due item once; no provider calls occur here."""
    initialize(store)
    count = 0
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        from .organic_video_monitor import advance as advance_video
        count += advance_video(db, store)
        rows = db.execute("""SELECT i.*,b.app_id,b.scope_id,b.summary,b.summary_hash
            FROM campaign_schedule_items i JOIN campaign_schedule_batches b ON b.id=i.batch_id
            WHERE i.status='READY' AND b.status='ACTIVE' AND i.due<=?
            ORDER BY i.due,i.id LIMIT ?""", (time.time(), MAX_ITEMS-count)).fetchall()
        for row in rows:
            body = json.loads(row['body'])
            summary = json.loads(row['summary'])
            if (digest(body) != row['body_hash'] or digest(summary) != row['summary_hash']
                    or body not in summary['items'] or body['item_id'] != row['id']
                    or row['due'] != iso_time(body['due_at']).timestamp()):
                db.execute("UPDATE campaign_schedule_items SET status='BLOCKED',updated=? WHERE id=?", (now(), row['id']))
                continue
            data = dict(batch_id=row['batch_id'], item_id=row['id'], scope_id=row['scope_id'], request=body['request'])
            operation = body.get('operation', 'campaign.publish')
            if 'operation' in body:
                data['operation'] = operation
            action = 'campaign_ad' if operation == 'campaign.ad-launch' else 'campaign_post'
            job_id = uid()
            db.execute('INSERT INTO jobs(id,app_id,action,data,status,created,updated,request_key) VALUES(?,?,?,?,?,?,?,?)',
                       (job_id, row['app_id'], action, canonical(data), 'QUEUED', now(), now(), 'campaign-schedule-' + row['id']))
            db.execute("UPDATE campaign_schedule_items SET status='QUEUED',job_id=?,updated=? WHERE id=? AND status='READY'",
                       (job_id, now(), row['id']))
            audit(db, row['app_id'], 'queued', dict(batch_id=row['batch_id'], item_id=row['id'], job_id=job_id))
            count += 1
    return count


def execute(store, job):
    from .campaign_access import policy_checker
    from .campaign_schedule_authority import bound
    with bound(store, job):
        data = job['data']
        if data.get('operation') == 'organic-video.intent-execute':
            from .campaign_video_execution import execute as execute_video
            return execute_video(store, job['app_id'], 'schedule:' + job['id'], data['request']['intent_id'], None)
        service = CampaignExecutionService(store, policy_checker(store))
        run = service.run_ad if data.get('operation') == 'campaign.ad-launch' else service.run_post
        return run(job['app_id'], 'schedule:' + job['id'], data['scope_id'], data['request'])
