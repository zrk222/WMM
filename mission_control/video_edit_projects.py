"""Append-only shared editor state, exact source proof and atomic history controls."""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
import json
import sqlite3
from .common import Invalid, canonical, digest, now, required
from .db import connection
from .creative_rendering import artifact_file, current_request
from .video_edit_contract import definition, edit, exact, identifier, integer, timing, FPS, source_key

MAX_REVISIONS = 200
MAX_PROJECTS = 100
ACTORS = ('LOCAL_SESSION', 'SCOPED_AGENT')
CALLER = ContextVar('video_project_admitted_caller', default=None)


@contextmanager
def admitted_caller(admission):
    """Only the authenticated gateway supplies public grant identity to project writes."""
    public = {key: admission[key] for key in ('grant_id', 'agent_id', 'attempt') if key in admission}
    token = CALLER.set(public)
    try:
        yield
    finally:
        CALLER.reset(token)


def row_view(row):
    """Return immutable saved content without interpreting it as a rendered video."""
    result = dict(row)
    result['data'] = json.loads(result['data'])
    result['actor'] = json.loads(result['actor'])
    result.pop('request_hash');result.pop('request_key')
    result.update(status='DRAFT_EDIT_PROJECT', render_execution='NOT_RUN_EDITS_NOT_RENDERED',
                  final_artifact_approval='NOT_ESTABLISHED', publication='NOT_RUN')
    result['timing'] = timing(result['data']['definition'])
    return result


def revision(db, app_id, identity, number):
    """A revision can only resolve inside its exact project and app namespace."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    row = db.execute('SELECT * FROM video_project_revisions WHERE app_id=? AND id=? AND revision=?',
                     (app_id, identity, number)).fetchone()
    if row is None:raise Invalid('Project revision does not belong to this app and project')
    return row


def head(db, app_id, identity):
    """Retain undo/redo stacks separately from immutable timeline revisions."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    row = db.execute('SELECT * FROM video_project_heads WHERE app_id=? AND id=?', (app_id, identity)).fetchone()
    if row is None:raise Invalid('Project does not belong to this app')
    return dict(row, undo=json.loads(row['undo']), redo=json.loads(row['redo']))


def app_version(db, app_id, expected):
    """Bind owner edits to the current product context before resolving any sources."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    integer(expected, 1, 2147483647, 'App version')
    row = db.execute('SELECT * FROM apps WHERE id=?', (app_id,)).fetchone()
    if row is None or row['version'] != expected:raise Invalid('App changed; reload the video project')
    return json.loads(row['data'])


def source_binding(db, store, app_id, source):
    """Resolve selected kind through its authoritative domain proof."""
    identity = source['id']
    if source['kind'] == 'MANAGED':
        from .managed_media_store import derivative_snapshot
        item, _ = derivative_snapshot(db, store, app_id, identity, source['sha256'])
        return dict(kind='MANAGED', id=identity, sha256=item['source_sha256'],
                    source_frames=int(item['metadata']['duration_seconds'] * FPS),
                    review_version=item['review_version'], manifest_version=item['manifest_version'])
    path, data = artifact_file(store, app_id, identity)
    current_request(db, store, app_id, data['request'])
    artifact = data['artifact']
    return dict(kind='NATIVE', id=identity, sha256=artifact['sha256'],
                source_frames=round(artifact['metadata']['duration_seconds'] * FPS),
                native_request_hash=digest(data['request']))


def bind_sources(db, store, app_id, value):
    """Every saved/restored source must still pass original rights, bytes and proof."""
    bindings = {}
    for clip in value['clips']:
        source = clip['source'];key = source_key(source)
        if key not in bindings:
            bindings[key] = source_binding(db, store, app_id, source)
        bound = bindings[key]
        if source['sha256'] != bound['sha256'] or clip['out_frame'] > bound['source_frames']:
            raise Invalid('Clip source hash or frame range changed; inspect the current source')
    return [bindings[key] for key in sorted(bindings)]


def saved_data(db, store, app_id, manifest, value):
    """Normalize the entire timeline and bind source bytes in the same DB snapshot."""
    app = app_version(db, app_id, manifest);value = definition(value)
    if value['locale'] != app['locale']:raise Invalid('Project language must match the current app locale')
    result = dict(definition=value, manifest_version=manifest, sources=bind_sources(db, store, app_id, value))
    if 'packaging' in value:
        from .packaging_editor import binding
        result['packaging'] = binding(db, store, app_id, value, manifest)
    return result


def replay(db, app_id, request_key, request_hash):
    """An old idempotent request returns its old revision without changing the head."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    row = db.execute('SELECT * FROM video_project_revisions WHERE app_id=? AND request_key=?', (app_id, request_key)).fetchone()
    if row is None:return None
    if row['request_hash'] != request_hash:raise Invalid('Video request key already belongs to a different edit')
    return row_view(row)


def append(db, app_id, identity, data, previous, undo, redo, actor, action, request_key, request_hash):
    """Write immutable revision, current head and public hash audit in one commit."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    number = previous + 1
    if number > MAX_REVISIONS:raise Invalid('Project revision limit reached; create a variant project')
    stamp = now();value_hash = digest(data)
    db.execute('INSERT INTO video_project_revisions VALUES(?,?,?,?,?,?,?,?,?,?,?)',
               (app_id, identity, number, canonical(data), value_hash, previous, canonical(actor), action, request_key, request_hash, stamp))
    db.execute('INSERT INTO video_project_heads VALUES(?,?,?,?,?) ON CONFLICT(app_id,id) DO UPDATE SET revision=?,undo=?,redo=?',
               (app_id, identity, number, canonical(undo), canonical(redo), number, canonical(undo), canonical(redo)))
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
               (app_id, 'video.project.' + action.lower(), canonical(dict(id=identity, revision=number, hash=value_hash, actor=actor)), stamp))
    return row_view(revision(db, app_id, identity, number))


class Projects:
    """Identical human and admitted-agent project operations; no execution authority."""
    def __init__(self, store, actor='LOCAL_SESSION'):
        if actor not in ACTORS:raise Invalid('Unknown video project caller')
        self.store = store;self.actor = actor

    def caller(self):
        """Draft-session origin and admitted public agent identity are separate facts."""
        if self.actor == 'LOCAL_SESSION':return dict(kind=self.actor)
        public = CALLER.get()
        if not public or any(not isinstance(public.get(key), str) for key in ('grant_id', 'agent_id')):
            raise PermissionError('Admitted agent identity is required for project edits')
        return dict(public, kind=self.actor)

    def list(self, app_id):
        """Return bounded saved heads with honest source freshness and draft status."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            rows = db.execute('SELECT r.* FROM video_project_revisions r JOIN video_project_heads h ON h.app_id=r.app_id AND h.id=r.id AND h.revision=r.revision WHERE r.app_id=? ORDER BY r.created DESC,r.id LIMIT ?', (app_id, MAX_PROJECTS)).fetchall()
            return dict(items=[self.public(db, app_id, row) for row in rows], render_execution='NOT_RUN_EDITS_NOT_RENDERED')

    def public(self, db, app_id, row):
        """Old timeline states stay readable when later source proof becomes stale."""
        result = row_view(row);data = result['data']
        try:
            actual = saved_data(db, self.store, app_id, data['manifest_version'], data['definition'])
            if actual != data:raise Invalid('Source binding changed')
            result['source_status'] = 'CURRENT'
        except (Invalid, OSError):
            result['source_status'] = 'STALE_OR_UNAVAILABLE'
        return result

    def read(self, app_id, identity):
        """Show current state and all bounded metadata, without discarding history."""
        self.store.app(app_id);identifier(identity)
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            state = head(db, app_id, identity)
            result = self.public(db, app_id, revision(db, app_id, identity, state['revision']))
            result['history'] = [dict(row, actor=json.loads(row['actor'])) for row in db.execute('SELECT revision,hash,parent_revision,actor,action,created FROM video_project_revisions WHERE app_id=? AND id=? ORDER BY revision', (app_id, identity))]
            result.update(can_undo=bool(state['undo']), can_redo=bool(state['redo']))
            return result

    def save(self, app_id, body):
        """Create or replace a complete timeline under exact expected revision."""
        exact(body, ('id', 'revision', 'manifest_version', 'data', 'request_key'))
        identifier(body['id']);definition(body['data'])
        return self.write(app_id, body['id'], body, 'SAVE')

    def edit(self, app_id, identity, body):
        """Apply the shared typed clip command to the expected current revision."""
        exact(body, ('revision', 'manifest_version', 'command', 'request_key'))
        return self.write(app_id, identity, body, 'EDIT')

    def history(self, app_id, identity, body):
        """Undo, redo or restore an exact prior state as a new immutable revision."""
        if not isinstance(body, dict) or body.get('operation') not in ('UNDO', 'REDO', 'RESTORE'):
            raise Invalid('Choose undo, redo or restore')
        fields = ('revision', 'manifest_version', 'operation', 'request_key')
        exact(body, fields + (('target_revision',) if body['operation'] == 'RESTORE' else ()))
        return self.write(app_id, identity, body, body['operation'])

    def write(self, app_id, identity, body, action):
        """Linearize revision/replay/source checks with the mutation and audit append."""
        self.store.app(app_id);identifier(identity)
        integer(body['revision'], 0, MAX_REVISIONS, 'Expected project revision')
        key = required(body['request_key'], 'Video request key', 120)
        actor = self.caller()
        request_actor = {key: value for key, value in actor.items() if key != 'attempt'}
        request_hash = digest(dict(project_id=identity, action=action, body=body, actor=request_actor))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            old = replay(db, app_id, key, request_hash)
            if old is not None:return old
            current = self.current(db, app_id, identity, body, action)
            value, undo, redo = next_state(db, app_id, identity, current, body, action)
            if current is not None:
                from .packaging_editor import preserve_origin
                preserve_origin(row_view(revision(db,app_id,identity,current['revision']))['data']['definition'],value)
            data = saved_data(db, self.store, app_id, body['manifest_version'], value)
            return append(db, app_id, identity, data, body['revision'], undo, redo,
                          actor, action, key, request_hash)

    def current(self, db, app_id, identity, body, action):
        """Only explicit revision zero can create; stale writes never overwrite heads."""
        if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
        if body['revision'] == 0:
            if action != 'SAVE':raise Invalid('Create the project before editing it')
            if db.execute('SELECT 1 FROM video_project_heads WHERE app_id=? AND id=?', (app_id, identity)).fetchone():
                raise Invalid('Project already exists; reload its current revision')
            if db.execute('SELECT count(*) FROM video_project_heads WHERE app_id=?', (app_id,)).fetchone()[0] >= MAX_PROJECTS:
                raise Invalid('Workspace project limit reached')
            return None
        current = head(db, app_id, identity)
        if current['revision'] != body['revision']:raise Invalid('Project changed; reload before applying this edit')
        return current

    def diff(self, app_id, identity, body):
        """Compare exact saved source-frame states without inventing visual differences."""
        exact(body, ('from_revision', 'to_revision'));identifier(identity);self.store.app(app_id)
        for key in body:integer(body[key], 1, MAX_REVISIONS, 'Diff revision')
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            before = row_view(revision(db, app_id, identity, body['from_revision']))
            after = row_view(revision(db, app_id, identity, body['to_revision']))
        left = before['data']['definition'];right = after['data']['definition']
        return dict(from_hash=before['hash'], to_hash=after['hash'],
                    changed_fields=[key for key in left if left[key] != right[key]],
                    before=left, after=right, render_comparison='NOT_RUN')


def next_state(db, app_id, identity, current, body, action):
    """Undo/redo move content pointers while every accepted action appends a revision."""
    if current is None:return deepcopy(body['data']), [], []
    number = current['revision'];undo = current['undo'];redo = current['redo']
    old = row_view(revision(db, app_id, identity, number))['data']['definition']
    if action == 'UNDO':
        if not undo:raise Invalid('There is no earlier project state to undo')
        target = undo.pop();redo.append(number)
    elif action == 'REDO':
        if not redo:raise Invalid('There is no undone project state to redo')
        target = redo.pop();undo.append(number)
    else:
        undo.append(number);redo = []
        if action == 'SAVE':return deepcopy(body['data']), undo, redo
        if action == 'EDIT':return edit(old, body['command']), undo, redo
        integer(body['target_revision'], 1, number, 'Restore revision')
        target = body['target_revision']
    return row_view(revision(db, app_id, identity, target))['data']['definition'], undo, redo
