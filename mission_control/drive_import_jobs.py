"""Private owner-bound Drive original import jobs on the existing durable worker."""
import time
import sqlite3
from .common import Invalid, canonical, digest, identifier, iso_time, now
from .db import connection
from .credential_vault import namespace
from .review_access import member
from .drive_media import Importer
from .managed_media_store import Media
from .creative_rendering import owned
from .worker import json_job

ACTION = 'drive_import'


def owner_version(db, app_id, principal):
    """Only current app owners can queue, read or cancel a private original import."""
    return member(db, app_id, principal, 'OWNER')['version']


def frozen(store, row, request, principal, version):
    """No token or native secret address enters the durable worker input."""
    return dict(request=dict(request), owner=principal, owner_version=version,
                namespace=namespace(store.path), connection_hash=digest(row))


class Imports:
    def __init__(self, store):
        self.store = store; self.importer = Importer(store); self.media = Media(store)

    def queue(self, app_id, body, principal):
        """Queue one source-bound durable import; identical owner/input retry deduplicates."""
        from .worker import enqueue
        identifier(app_id)
        with connection(self.store.path) as db:version = owner_version(db, app_id, principal)
        row, _ = self.importer.selected(app_id, body)
        request = frozen(self.store, row, body, principal, version)
        result = enqueue(self.store, app_id, ACTION, request, body['request_key'])
        return self.read(app_id, result['id'], principal)

    def authority(self, db, app_id, data):
        """A copied database, revoked owner or changed role cannot resume private work."""
        keys = {'request', 'owner', 'owner_version', 'namespace', 'connection_hash'}
        if not isinstance(data, dict) or set(data) != keys:raise Invalid('Drive job authority metadata is invalid')
        if data['namespace'] != namespace(self.store.path):raise Invalid('Drive job belongs to a different local workspace')
        if type(data['owner_version']) is not int or owner_version(db, app_id, data['owner']) != data['owner_version']:
            raise Invalid('Drive import owner authority changed; prepare a new import')

    def guard(self, job, stop=None):
        """Current job attempt, owner and source context must hold before every phase."""
        if stop is not None and stop.is_set():raise Invalid('Worker stopped; inspect the saved Drive import')
        with connection(self.store.path) as db:
            owned(db, job); self.authority(db, job['app_id'], job['data'])
            saved = db.execute('SELECT data,action FROM jobs WHERE id=? AND app_id=?', (job['id'], job['app_id'])).fetchone()
            if saved['action'] != ACTION or saved['data'] != canonical(job['data']):
                raise Invalid('Drive import request changed after worker admission')
        row, _ = self.importer.selected(job['app_id'], job['data']['request'])
        if digest(row) != job['data']['connection_hash']:raise Invalid('Drive source connection changed after queueing')

    def pulse(self, job, stop, last):
        """Check each phase/chunk while bounding durable lease writes to once per second."""
        self.guard(job, stop); current = time.monotonic()
        if current - last[0] >= 1:
            if self.renew(job):last[0] = current

    def renew(self, job):
        """Do not deadlock a media commit's own writer; retain ownership checks on every pulse."""
        try:
            with connection(self.store.path) as db:
                db.execute('PRAGMA busy_timeout=0')
                owned(db, job); self.authority(db, job['app_id'], job['data'])
                db.execute("UPDATE jobs SET lease=?,updated=? WHERE id=? AND status='RUNNING' AND attempts=?", (time.time() + 60, now(), job['id'], job['attempts']))
            return True
        except sqlite3.OperationalError as error:
            if getattr(error, 'sqlite_errorcode', None) not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):raise
            return False

    def previous(self, job):
        """Recover a committed original after a crash without another provider download."""
        request = job['data']['request']
        with connection(self.store.path) as db:
            row = db.execute('SELECT id FROM managed_media WHERE app_id=? AND request_key=?', (job['app_id'], request['request_key'])).fetchone()
        if row is None:return None
        item, _ = self.media.original(job['app_id'], row['id'], job['data']['owner'])
        provenance = item['provenance']
        expected = dict(kind='GOOGLE_DRIVE', connection_id=request['connection_id'], connection_version=request['connection_version'], file_id=request['file_id'])
        if any(provenance.get(key) != value for key, value in expected.items()):
            raise Invalid('Drive import key belongs to a different original source')
        return item

    def execute(self, job, stop=None):
        """Reuse existing lease/cancellation semantics; final media commit remains guarded."""
        from .workflow_telemetry import emit
        last = [0]
        def alive():self.pulse(job, stop, last)
        def progress(code):
            alive(); emit(self.store, job, code)
        alive(); item = self.previous(job)
        if item is None:
            item = self.importer.import_file(job['app_id'], job['data']['request'], alive, progress)
        alive(); progress('DRIVE_RETAINED')
        return dict(media_id=item['id'], source_sha256=item['source_sha256'], bytes=item['bytes'],
                    reuse_permission=item['rights_status'], next_action='REVIEW_SOURCE_REUSE', provider_writes='NOT_RUN')

    def read(self, app_id, job_id, principal):
        """An explicit owner route returns private input, actual events and sanitized result."""
        from .workflow_telemetry import run_view
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN'); owner_version(db, app_id, principal)
            row = db.execute('SELECT * FROM jobs WHERE app_id=? AND id=? AND action=?', (app_id, job_id, ACTION)).fetchone()
            if row is None:raise Invalid('Drive import does not belong to this app')
            job = json_job(row)
            value = {key: job[key] for key in ('id', 'app_id', 'action', 'status', 'attempts', 'created', 'updated')}
            value = run_view(db, app_id, value)
        finished = now() if job['status'] in ('QUEUED', 'RUNNING') else job['updated']
        value.update(selection=job['data']['request'], result=job['result'],
                     elapsed_seconds=max(0, (iso_time(finished) - iso_time(job['created'])).total_seconds()),
                     progress_percent=None, cost_minor=None, scope='PRIVATE_OWNER_IMPORT_PROGRESS')
        return value

    def list(self, app_id, principal):
        """Only the most recent hundred private imports are projected for an app owner."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            owner_version(db, app_id, principal)
            ids = [row['id'] for row in db.execute('SELECT id FROM jobs WHERE app_id=? AND action=? ORDER BY created DESC,id LIMIT 100', (app_id, ACTION))]
        return dict(items=[self.read(app_id, identity, principal) for identity in ids])

    def cancel(self, app_id, job_id, principal):
        """Cancellation is durable before the next read/native step can continue."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE'); owner_version(db, app_id, principal)
            changed = db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=? AND action=? AND status IN ('QUEUED','RUNNING')", (now(), app_id, job_id, ACTION)).rowcount
            if not changed:raise Invalid('Drive import cannot be canceled; reload its current state')
        return self.read(app_id, job_id, principal)
