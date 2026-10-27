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
