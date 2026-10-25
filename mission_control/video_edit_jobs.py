"""Current exact project render jobs and immutable app-owned edited MP4 artifacts."""
import hashlib
import json
from pathlib import Path
import re
import tempfile
import time
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .creative_rendering import owned, heartbeat, artifact_file as native_file
from .video_edit_contract import exact, identifier, integer, source_key
from .video_edit_projects import head, revision, saved_data, MAX_REVISIONS
from .video_edit_rendering import render
from .native_runtime_identity import identity as runtime_identity


def folder_for(store, app_id):
    """Resolve only the selected app's private artifact directory; reject links."""
    store.app(app_id);base = store.path.parent.resolve();root = base/'edited-videos';target = root/digest(app_id)
    if root.is_symlink() or target.is_symlink() or not target.resolve().is_relative_to(base):
        raise Invalid('Edited-video storage changed; inspect the local workspace')
    return target


def current(db, store, app_id, body):
    """Bind exact current head, app/source proofs and detected runtime bytes."""
    exact(body, ('project_id', 'revision', 'project_hash'));identifier(body['project_id'])
    integer(body['revision'], 1, MAX_REVISIONS, 'Render project revision')
    state = head(db, app_id, body['project_id'])
    if state['revision'] != body['revision']:raise Invalid('Project changed; select its current revision before rendering')
    row = revision(db, app_id, body['project_id'], body['revision'])
    if row['hash'] != body['project_hash']:raise Invalid('Project hash changed; reload before rendering')
    data = json.loads(row['data'])
    if digest(data) != row['hash']:raise Invalid('Saved project integrity changed; inspect local history')
    if saved_data(db, store, app_id, data['manifest_version'], data['definition']) != data:
        raise Invalid('Project source proof changed; inspect the current timeline')
    runtime = runtime_identity()
    if runtime['status'] != 'READY':raise Invalid(runtime['repair'])
    return dict(selection=body, project=data, runtime=runtime)


def check(db, store, app_id, request):
    """Worker inputs cannot forge source bindings, controls or a different runtime."""
    exact(request, ('selection', 'project', 'runtime'))
    if current(db, store, app_id, request['selection']) != request:
        raise Invalid('Frozen edit render proof changed; prepare a new request')


def artifact_file(store, app_id, render_id):
    """Retained edited bytes remain inspectable only while original source rights hold."""
    store.app(app_id)
    if not isinstance(render_id, str) or not re.fullmatch(r'[a-f0-9-]{36}', render_id):raise Invalid('Invalid edited artifact identifier')
    with connection(store.path) as db:
        row = db.execute('SELECT * FROM video_edit_renders WHERE app_id=? AND id=?', (app_id, render_id)).fetchone()
        if row is None:raise Invalid('Edited video does not belong to this app')
        data = json.loads(row['data'])
        if digest(data) != row['hash']:raise Invalid('Edited artifact record changed')
        project = data['request']['project']
        if saved_data(db, store, app_id, project['manifest_version'], project['definition']) != project:
            raise Invalid('Edited artifact source proof changed')
    path = folder_for(store, app_id)/(render_id+'.mp4')
    if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != data['artifact']['sha256']:
        raise Invalid('Edited video is missing or changed')
    return path, data


class EditRenders:
    """Reuse durable worker ownership; this service never approves or publishes media."""
    def __init__(self, store):self.store = store

    def queue(self, app_id, body):
        """Queue exact proof once; identical retry keys reuse the existing durable job."""
        from .worker import enqueue
        exact(body, ('data', 'request_key'));self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN');request = current(db, self.store, app_id, body['data'])
        return enqueue(self.store, app_id, 'edit_render', request, body['request_key'])

    def list(self, app_id):
        """Keep artifact integrity, saved revision and current-head status distinct."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = db.execute('SELECT * FROM video_edit_renders WHERE app_id=? ORDER BY created DESC,id LIMIT 100', (app_id,)).fetchall()
        result = []
        for row in rows:
            item = dict(row);item['data'] = json.loads(item['data'])
            try:
                artifact_file(self.store, app_id, row['id'])
                with connection(self.store.path) as db:check(db, self.store, app_id, item['data']['request'])
                item['status'] = 'CURRENT'
            except (Invalid, OSError):item['status'] = 'STALE_OR_UNAVAILABLE'
            result.append(item)
        return dict(items=result, publication='NOT_RUN', final_artifact_review='REQUIRED')

    def execute(self, job, stop=None):
        """Render privately and commit only if exact current proof and ownership survive."""
        from .workflow_telemetry import emit
        emit(self.store, job, 'EDIT_PROOF');app_id = job['app_id'];request = job['data']
        with connection(self.store.path) as db:
            owned(db, job);check(db, self.store, app_id, request)
            old = db.execute('SELECT id FROM video_edit_renders WHERE app_id=? AND job_id=?', (app_id, job['id'])).fetchone()
        if old:
            path, data = artifact_file(self.store, app_id, old['id'])
            return dict(render_id=old['id'], artifact_hash=data['artifact']['sha256'], publication='NOT_RUN')
        root = folder_for(self.store, app_id);root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='attempt-', dir=root) as directory:
            folder = Path(directory);emit(self.store, job, 'EDIT_SOURCES')
            sources = self.copy_sources(folder, app_id, request)
            emit(self.store, job, 'EDIT_ENCODING')
            output, artifact = render(folder, request['project']['definition'], sources,
                                      self.render_guard(job, stop))
            heartbeat(self.store, job, stop);emit(self.store, job, 'EDIT_COMMIT')
            return self.commit(job, artifact, output)

    def render_guard(self, job, stop):
        """Stop an owned renderer when current uploaded-source reuse is revoked."""
        from .managed_media_store import derivative_snapshot
        checked = [0.0]
        def alive():
            heartbeat(self.store, job, stop)
            stamp = time.monotonic()
            if stamp - checked[0] < 1:
                return
            with connection(self.store.path) as db:
                db.execute('BEGIN')
                for source in job['data']['project']['sources']:
                    if source['kind'] == 'MANAGED':
                        derivative_snapshot(db, self.store, job['app_id'], source['id'], source['sha256'], verify_bytes=False)
            checked[0] = stamp
        return alive

    def copy_sources(self, folder, app_id, request):
        """Capture verified source bytes once; never reopen an untrusted original path."""
        from .managed_media_store import derivative_snapshot
        result = {}
        for index, source in enumerate(request['project']['sources']):
            if source['kind'] == 'MANAGED':
                with connection(self.store.path) as db:
                    db.execute('BEGIN')
                    _, raw = derivative_snapshot(db, self.store, app_id, source['id'], source['sha256'], capture=True)
            else:
                path, data = native_file(self.store, app_id, source['id'])
                raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != source['sha256']:raise Invalid('Source changed while copying edited media')
            target = folder/f'source{index}.mp4';target.write_bytes(raw);result[source_key(source)] = target
        return result

    def commit(self, job, artifact, output):
        """Remove exclusively created output if the guarded artifact transaction fails."""
        app_id = job['app_id'];identity = uid();target = folder_for(self.store, app_id)/(identity+'.mp4');created = False
        data = dict(request=job['data'], artifact=artifact, renderer='NATIVE_EDIT_TIMELINE',
                    publication='NOT_RUN', final_artifact_review='REQUIRED', audio='SELECTED_SOURCE_AUDIO' if any(c.get('audio') == 'RETAIN' for c in job['data']['project']['definition']['clips']) else 'SILENT_NATIVE_SOURCE_PROFILE',
                    cost=dict(model_api_charge_minor=0, machine_cost='NOT_MEASURED'))
        try:
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE');owned(db, job);check(db, self.store, app_id, job['data'])
                with target.open('xb') as destination:created = True;destination.write(output.read_bytes())
                db.execute('INSERT INTO video_edit_renders VALUES(?,?,?,?,?,?)',
                           (app_id, identity, job['id'], canonical(data), digest(data), now()))
                db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                           (app_id, 'video.edit.rendered', canonical(dict(id=identity, hash=digest(data))), now()))
        except Exception:
            if created:target.unlink(missing_ok=True)
            raise
        return dict(render_id=identity, artifact_hash=artifact['sha256'], publication='NOT_RUN')
