"""App-owned Hypit jobs, retained attempts and immutable decoded artifacts."""
import hashlib
import json
import re
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .creative_rendering import render_request, current_request, owned, heartbeat
from .hypit_authoring import scene_contract
from .hypit_media import MAX_BYTES
from .hypit_runtime import identity, render, build_identity


def private_path(store, app_id, *parts):
    """Internal identifiers choose paths; linked private directories are rejected."""
    base = store.path.parent.resolve()
    path = base / 'hypit' / digest(app_id)
    candidates = [base / 'hypit', path]
    for part in parts:
        path = path / part
        candidates.append(path)
    if any(item.is_symlink() for item in candidates) or not path.resolve().is_relative_to(base):
        raise Invalid('Hypit private storage changed; inspect local storage before retrying')
    return path


def brief_scene(request):
    """Preserve approved script verbatim and distribute its integer duration exactly."""
    captions = request['captions']
    seconds, extra = divmod(request['duration_seconds'], len(captions))
    value = dict(title=request['brief']['data']['app']['name'], shape=request['shape'],
                 scenes=[dict(text=text, seconds=seconds + (index < extra)) for index, text in enumerate(captions)])
    return scene_contract(value)


def current_inputs(db, store, app_id, data):
    """Worker data is checked against current proof, exact scripts and scene schema."""
    if not isinstance(data, dict) or set(data) != {'request', 'scene'}:
        raise Invalid('Hypit job has unsupported frozen inputs')
    current_request(db, store, app_id, data['request'])
    if brief_scene(data['request']) != data['scene']:
        raise Invalid('Hypit scene differs from the approved brief')


def saved(row):
    """Read persisted envelopes only while their original data hash matches."""
    value = dict(row)
    value['data'] = json.loads(value['data'])
    if digest(value['data']) != value['hash']:
        raise Invalid('Hypit saved history changed; inspect before reuse')
    return value


def capability():
    """Inspect launcher presence only; workspace reads never start its runtime."""
    try:
        runtime = identity()
    except (Invalid, OSError):
        return dict(status='UNAVAILABLE', repair='Install the optional Hypit CLI and prepare its local browser and media tools.')
    return dict(status='DETECTED', launcher_sha256=runtime['launcher_sha256'],
                repair='Compiler, local endpoints and media readiness are checked when a render starts.')


def artifact_file(store, app_id, render_id):
    """Check selected-app scope and bounded exact bytes before any download."""
    store.app(app_id)
    if not isinstance(render_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', render_id):
        raise Invalid('Invalid Hypit render identifier')
    with connection(store.path) as db:
        row = db.execute('SELECT * FROM hypit_renders WHERE app_id=? AND id=?', (app_id, render_id)).fetchone()
    if not row:
        raise Invalid('Hypit video does not belong to this app')
    data = saved(row)['data']
    path = private_path(store, app_id, 'artifacts', render_id + '.mp4')
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise Invalid('Hypit video is missing or unavailable')
    if hashlib.sha256(path.read_bytes()).hexdigest() != data['artifact']['sha256']:
        raise Invalid('Hypit video changed; inspect retained source before rendering again')
    return path, data


class HypitRenders:
    def __init__(self, store):
        self.store = store

    def queue(self, app_id, body):
        """Freeze the current brief before creating an idempotent local render job."""
        from .worker import enqueue
        self.store.app(app_id)
        if not isinstance(body, dict) or set(body) != {'data', 'request_key'}:
            raise Invalid('Hypit render needs guided brief fields and a retry identity')
        identity()
        with connection(self.store.path) as db:
            request = render_request(db, self.store, app_id, body['data'])
        data = dict(request=request, scene=brief_scene(request))
        return enqueue(self.store, app_id, 'hypit_render', data, body['request_key'])

    def list(self, app_id):
        """Show immutable outputs, source freshness and retained unfinished history."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = [saved(row) for row in db.execute('SELECT * FROM hypit_renders WHERE app_id=? ORDER BY created DESC,id', (app_id,))]
            attempts = [saved(row) for row in db.execute('SELECT * FROM hypit_attempts WHERE app_id=? ORDER BY created DESC,job_id', (app_id,))]
        for row in rows:
            try:
                artifact_file(self.store, app_id, row['id'])
                with connection(self.store.path) as db:
                    current_inputs(db, self.store, app_id, row['data']['inputs'])
                row['status'] = 'CURRENT'
            except (Invalid, OSError, KeyError):
                row['status'] = 'STALE_OR_UNAVAILABLE'
        return dict(items=rows, attempts=attempts, capability=capability(), authoring_mode='APPROVED_BRIEF_CAPTIONS', publication='NOT_RUN')

    def begin(self, job):
        """Reserve one retained project before a process can submit any work."""
        folder = private_path(self.store, job['app_id'], job['id'])
        data = dict(project=folder.relative_to(self.store.path.parent.resolve()).as_posix(), inputs_hash=digest(job['data']), build_id=None)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            owned(db, job)
            current_inputs(db, self.store, job['app_id'], job['data'])
            previous = db.execute('SELECT * FROM hypit_attempts WHERE app_id=? AND job_id=?', (job['app_id'], job['id'])).fetchone()
            if previous:
                raise Invalid('Hypit attempt already exists; inspect its retained build without resubmitting')
            db.execute('INSERT INTO hypit_attempts VALUES(?,?,?,?,?,?,?,?)',
                       (job['app_id'], job['id'], job['attempts'], canonical(data), digest(data), 'STARTED', now(), now()))
        folder.mkdir(parents=True, exist_ok=False)
        return folder

    def submitted(self, job, key):
        """Persist the actual submitted build before status observation starts."""
        build_identity(dict(build=dict(id=key)))
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            owned(db, job)
            row = db.execute('SELECT * FROM hypit_attempts WHERE app_id=? AND job_id=?', (job['app_id'], job['id'])).fetchone()
            attempt = saved(row)
            if attempt['attempt'] != job['attempts'] or attempt['data']['build_id'] is not None:
                raise Invalid('Hypit build identity was already recorded or attempt changed')
            data = dict(attempt['data'], build_id=key)
            db.execute('UPDATE hypit_attempts SET data=?,hash=?,status=?,updated=? WHERE app_id=? AND job_id=?',
                       (canonical(data), digest(data), 'SUBMITTED', now(), job['app_id'], job['id']))

    def execute(self, job, stop=None):
        """Replay committed output or run the single durably reserved attempt."""
        with connection(self.store.path) as db:
            owned(db, job)
            current_inputs(db, self.store, job['app_id'], job['data'])
            previous = db.execute('SELECT * FROM hypit_renders WHERE app_id=? AND job_id=?', (job['app_id'], job['id'])).fetchone()
        if previous:
            row = saved(previous)
            artifact_file(self.store, job['app_id'], row['id'])
            return dict(render_id=row['id'], artifact_hash=row['data']['artifact']['sha256'], publication='NOT_RUN')
        folder = self.begin(job)
        try:
            result = render(folder, job['data']['scene'], alive=lambda: heartbeat(self.store, job, stop), submitted=lambda key: self.submitted(job, key))
            heartbeat(self.store, job, stop)
            return self.commit(job, folder, result)
        except Exception:
            with connection(self.store.path) as db:
                db.execute('UPDATE hypit_attempts SET status=?,updated=? WHERE app_id=? AND job_id=? AND attempt=?',
                           ('NEEDS_INSPECTION', now(), job['app_id'], job['id'], job['attempts']))
            raise Invalid('Hypit run interrupted; inspect the retained attempt before retrying') from None

    def commit(self, job, folder, result):
        """Accept copied bytes only while frozen proof and actual build remain current."""
        output = folder / 'video.mp4'
        if output.is_symlink() or not 0 < output.stat().st_size <= MAX_BYTES:
            raise Invalid('Hypit output is unavailable or exceeds its bound')
        content = output.read_bytes()
        if hashlib.sha256(content).hexdigest() != result['artifact']['sha256']:
            raise Invalid('Hypit output changed before commit')
        render_id = uid()
        target = private_path(self.store, job['app_id'], 'artifacts', render_id + '.mp4')
        target.parent.mkdir(parents=True, exist_ok=True)
        data = dict(inputs=job['data'], artifact=result['artifact'], receipt=result, renderer='HYPIT_LOCAL',
                    authoring_mode='APPROVED_BRIEF_CAPTIONS', visual_review='REQUIRED', publication='NOT_RUN')
        created = False
        try:
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE')
                owned(db, job)
                current_inputs(db, self.store, job['app_id'], job['data'])
                row = db.execute('SELECT * FROM hypit_attempts WHERE app_id=? AND job_id=?', (job['app_id'], job['id'])).fetchone()
                attempt = saved(row)
                if attempt['attempt'] != job['attempts'] or attempt['data']['build_id'] != result['build_id']:
                    raise Invalid('Hypit output does not match the retained build')
                with target.open('xb') as destination:
                    created = True
                    destination.write(content)
                db.execute('INSERT INTO hypit_renders VALUES(?,?,?,?,?,?)', (job['app_id'], render_id, job['id'], canonical(data), digest(data), now()))
                db.execute('UPDATE hypit_attempts SET status=?,updated=? WHERE app_id=? AND job_id=?', ('COMPLETE', now(), job['app_id'], job['id']))
                db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                           (job['app_id'], 'hypit.render.completed', canonical(dict(id=render_id, hash=digest(data))), now()))
        except Exception:
            if created:
                target.unlink(missing_ok=True)
            raise
        return dict(render_id=render_id, artifact_hash=result['artifact']['sha256'], publication='NOT_RUN')
