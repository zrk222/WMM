"""Data-only native scene studio; the trusted host owns rendering and decoding.

The Python service never executes Hypit/Node and never accepts a media path or a
user-supplied claim of decoding. A separate native-only completion entry point
must provide an inspection produced by the native decoder.
"""
import json
import re
from uuid import UUID, uuid4

from .common import Invalid, canonical, digest, identifier, now, required
from .db import connection
from .hypit_authoring import scene_contract
from .ios_bridge import decode_document, encode_response


def studio_scene(value):
    """Extend the shared literal scene vocabulary with approved managed video."""
    if not isinstance(value, dict) or not isinstance(value.get('scenes'), list):
        raise Invalid('Use a declarative studio scene')
    base = dict(value, scenes=[{k: v for k, v in item.items() if k != 'media'} if isinstance(item, dict) else item
                               for item in value['scenes']])
    result = scene_contract(base)
    for src, dest in zip(value['scenes'], result['scenes']):
        if 'media' not in src: continue
        media = src['media']
        if (not isinstance(media, dict) or set(media) != {'id', 'sha256', 'in_frame', 'audio'} or
                not isinstance(media['id'], str) or not re.fullmatch('[a-f0-9-]{36}', media['id']) or
                not isinstance(media['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', media['sha256']) or
                type(media['in_frame']) is not int or not 0 <= media['in_frame'] <= 1439 or
                media['in_frame'] + dest['seconds'] * 24 > 1440 or
                media['audio'] not in ('MUTE', 'RETAIN')):
            raise Invalid('Choose an approved video, source start and audio mode')
        dest['media'] = dict(media)
    return result


class NativeStudio:
    def __init__(self, service, identities):
        self.service, self.identities = service, identities

    def call(self, session, app_id, action, payload, *, inspection=None):
        from .operation_authority import bound_owner, protected
        body = decode_document(payload)
        fields = {
            'projects': set(), 'read': {'project_id'},
            'save': {'project_id', 'base_revision', 'manifest_version', 'request_key', 'scene'},
            'plan': {'project_id', 'revision', 'source_hash'},
            'start': {'project_id', 'revision', 'source_hash', 'request_key'},
            'inspect': {'job_id'}, 'artifact': {'job_id'}, 'cancel': {'job_id'},
            'validate': {'job_id', 'packet_hash'}, 'finish': {'job_id', 'packet_hash'},
        }
        if action not in fields or not isinstance(body, dict) or set(body) != fields[action]:
            raise Invalid('Use an exact native studio action')
        if (action == 'finish') != (inspection is not None):
            raise Invalid('Native decoding evidence is required only for completion')
        user = self.identities.fresh(session)
        envelope = dict(app_id=app_id, operation='native.studio.' + action, input=body)
        with bound_owner(self.service.store, envelope, self.identities, session, user):
            with protected(self.service.store, envelope):
                with connection(self.service.store.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    return encode_response(self._dispatch(db, app_id, user['principal'], action, body, inspection))

    @staticmethod
    def _project(db, app_id, project_id):
        identifier(project_id)
        row = db.execute('SELECT * FROM ios_studio_projects WHERE app_id=? AND id=? ORDER BY revision DESC LIMIT 1',
                         (app_id, project_id)).fetchone()
        if row is None: raise Invalid('Studio project is unavailable in this app')
        return row

    @staticmethod
    def _public(row):
        return dict(project_id=row['id'], revision=row['revision'], manifest_version=row['manifest_version'],
                    source_hash=row['source_hash'], scene=json.loads(row['scene']))

    def _current(self, db, app_id, body):
        row = self._project(db, app_id, body['project_id'])
        app = db.execute('SELECT version FROM apps WHERE id=?', (app_id,)).fetchone()
        if (type(body['revision']) is not int or body['revision'] != row['revision'] or
                body['source_hash'] != row['source_hash'] or app is None or app['version'] != row['manifest_version'] or
                digest(json.loads(row['scene'])) != row['source_hash']):
            raise Invalid('Project, source or app revision changed; reopen the current project')
        return row

    def _packet(self, db, app_id, row):
        scene = json.loads(row['scene'])
        studio_scene(scene)
        packet = dict(schema='growth.ios-studio-packet.v1', app_id=app_id,
                      project_id=row['id'], revision=row['revision'], source_hash=row['source_hash'],
                      manifest_version=row['manifest_version'], scene=scene, fps=24,
                      frame_count=24 * sum(x['seconds'] for x in scene['scenes']),
                      status='PREPARED_NOT_RENDERED', execution_authority=False)
        bindings = []
        from .managed_media_store import derivative_snapshot
        for item in scene['scenes']:
            if 'media' not in item: continue
            media = item['media']
            source, _ = derivative_snapshot(db, self.service.store, app_id, media['id'], media['sha256'])
            if media['in_frame'] + item['seconds'] * 24 > int(source['metadata']['duration_seconds'] * 24):
                raise Invalid('Scene exceeds the approved source duration')
            if media['audio'] == 'RETAIN' and not source['metadata']['audio']:
                raise Invalid('The selected original has no decoded audio to retain')
            bindings.append(dict(id=media['id'], sha256=media['sha256'], review_version=source['review_version'],
                                 manifest_version=source['manifest_version'], audio=source['metadata']['audio']))
        if bindings: packet['media_bindings'] = bindings
        return dict(packet, packet_hash=digest(packet))

    def _job(self, db, app_id, user, identity):
        try: UUID(identity)
        except (ValueError, TypeError, AttributeError): raise Invalid('Choose a valid studio job') from None
        row = db.execute('SELECT * FROM ios_studio_jobs WHERE app_id=? AND id=?', (app_id, identity)).fetchone()
        if row is None or row['owner'] != user: raise PermissionError('Studio job is unavailable to this owner')
        return row

    @staticmethod
    def _job_public(row):
        return dict(job_id=row['id'], project_id=row['project_id'], revision=row['revision'],
                    source_hash=row['source_hash'], packet_hash=row['packet_hash'], status=row['status'],
                    result=json.loads(row['result']) if row['result'] else None)

    def _dispatch(self, db, app_id, user, action, body, inspection):
        if action == 'projects':
            rows = db.execute('SELECT p.* FROM ios_studio_projects p WHERE p.app_id=? AND p.revision=(SELECT MAX(q.revision) FROM ios_studio_projects q WHERE q.app_id=p.app_id AND q.id=p.id) ORDER BY p.created DESC', (app_id,)).fetchall()
            return dict(projects=[self._public(r) for r in rows])
        if action == 'read':
            row = self._project(db, app_id, body['project_id'])
            jobs = db.execute('SELECT * FROM ios_studio_jobs WHERE app_id=? AND project_id=? AND owner=? ORDER BY created,id', (app_id, row['id'], user)).fetchall()
            return dict(project=self._public(row), jobs=[self._job_public(j) for j in jobs])
        if action == 'save':
            identity = identifier(body['project_id'])
            required(body['request_key'], 'Request key', 100)
            scene = studio_scene(body['scene'])
            if type(body['base_revision']) is not int or body['base_revision'] < 0 or type(body['manifest_version']) is not int:
                raise Invalid('Use the exact project and app revisions')
            app = db.execute('SELECT version FROM apps WHERE id=?', (app_id,)).fetchone()
            if app is None or app['version'] != body['manifest_version']: raise Invalid('App setup changed')
            request_hash = digest(body)
            old = db.execute('SELECT * FROM ios_studio_projects WHERE app_id=? AND request_key=?', (app_id, body['request_key'])).fetchone()
            if old:
                if old['request_hash'] != request_hash or old['owner'] != user: raise Invalid('Request key belongs to another edit')
                return self._public(old)
            latest = db.execute('SELECT MAX(revision) FROM ios_studio_projects WHERE app_id=? AND id=?', (app_id, identity)).fetchone()[0] or 0
            if latest != body['base_revision']: raise Invalid('Studio project changed; reopen before saving')
            revision = latest + 1
            db.execute('INSERT INTO ios_studio_projects VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (app_id, identity, revision, app['version'], canonical(scene), digest(scene), user, body['request_key'], request_hash, now()))
            return self._public(self._project(db, app_id, identity))
        if action in ('plan', 'start'):
            row = self._current(db, app_id, body)
            packet = self._packet(db, app_id, row)
            if action == 'plan': return packet
            required(body['request_key'], 'Request key', 100)
            request_hash = digest(body)
            old = db.execute('SELECT * FROM ios_studio_jobs WHERE app_id=? AND request_key=?', (app_id, body['request_key'])).fetchone()
            if old:
                if old['request_hash'] != request_hash or old['owner'] != user: raise Invalid('Request key belongs to another render')
                return dict(job=self._job_public(old), packet=packet)
            job_id, stamp = str(uuid4()), now()
            db.execute('INSERT INTO ios_studio_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (app_id, job_id, row['id'], row['revision'], row['source_hash'], packet['packet_hash'], user,
                        body['request_key'], request_hash, 'PREPARED', None, stamp, stamp))
            return dict(job=self._job_public(self._job(db, app_id, user, job_id)), packet=packet)
        row = self._job(db, app_id, user, body['job_id'])
        if action == 'inspect': return self._job_public(row)
        if action == 'artifact':
            if row['status'] != 'SUCCEEDED' or row['result'] is None:
                raise Invalid('There is no decoded artifact for this attempt')
            project = db.execute('SELECT * FROM ios_studio_projects WHERE app_id=? AND id=? AND revision=?',
                                 (app_id, row['project_id'], row['revision'])).fetchone()
            app = db.execute('SELECT version FROM apps WHERE id=?', (app_id,)).fetchone()
            if (project is None or app is None or app['version'] != project['manifest_version'] or
                    project['source_hash'] != row['source_hash'] or digest(json.loads(project['scene'])) != row['source_hash'] or
                    self._packet(db, app_id, project)['packet_hash'] != row['packet_hash']):
                raise Invalid('Saved artifact source or app revision no longer matches')
            return self._job_public(row)
        if action == 'cancel':
            if row['status'] == 'PREPARED':
                db.execute("UPDATE ios_studio_jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=?", (now(), app_id, row['id']))
            elif row['status'] != 'CANCELLED': raise Invalid('Completed render cannot be cancelled')
            return self._job_public(self._job(db, app_id, user, row['id']))
        if action == 'finish' and row['status'] == 'SUCCEEDED':
            project = self._current(db, app_id, dict(project_id=row['project_id'], revision=row['revision'], source_hash=row['source_hash']))
            if (body['packet_hash'] != row['packet_hash'] or self._packet(db, app_id, project)['packet_hash'] != row['packet_hash'] or
                    inspection != json.loads(row['result'])):
                raise Invalid('Completed render retry differs from its committed evidence')
            return self._job_public(row)
        if row['status'] != 'PREPARED' or body['packet_hash'] != row['packet_hash']:
            raise Invalid('Studio render is cancelled, completed or has changed')
        project = self._current(db, app_id, dict(project_id=row['project_id'], revision=row['revision'], source_hash=row['source_hash']))
        packet = self._packet(db, app_id, project)
        if packet['packet_hash'] != row['packet_hash']: raise Invalid('Studio packet changed')
        if action == 'validate': return packet
        # Only the fixed native finish bridge may supply this separate decoder result.
        if not isinstance(inspection, dict) or set(inspection) != {'artifact_id', 'sha256', 'bytes', 'frames', 'width', 'height', 'audio'}:
            raise Invalid('Native decoder evidence is malformed')
        try:
            if UUID(inspection['artifact_id']) != UUID(row['id']):
                raise Invalid('Native artifact does not belong to this render')
        except (ValueError, TypeError, AttributeError): raise Invalid('Native artifact identity is malformed') from None
        width, height = (720, 1280) if packet['scene']['shape'] == 'PORTRAIT' else (1280, 720)
        if (not isinstance(inspection['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', inspection['sha256']) or
                type(inspection['bytes']) is not int or not 0 < inspection['bytes'] <= 67108864 or
                type(inspection['frames']) is not int or inspection['frames'] != packet['frame_count'] or
                type(inspection['width']) is not int or inspection['width'] != width or
                type(inspection['height']) is not int or inspection['height'] != height or
                type(inspection['audio']) is not bool or inspection['audio'] != any(x.get('media', {}).get('audio') == 'RETAIN' for x in packet['scene']['scenes'])):
            raise Invalid('Decoded artifact does not match the prepared scene')
        db.execute("UPDATE ios_studio_jobs SET status='SUCCEEDED',result=?,updated=? WHERE app_id=? AND id=?",
                   (canonical(inspection), now(), app_id, row['id']))
        return self._job_public(self._job(db, app_id, user, row['id']))

    def source(self, session, app_id, job_id, packet_hash, media_id, sha256):
        """Return a private path only to the fixed native host after revalidation."""
        from .operation_authority import bound_owner, protected
        from .managed_media_store import _decode_data, _file_path
        body = dict(job_id=job_id, packet_hash=packet_hash, media_id=media_id, sha256=sha256)
        user = self.identities.fresh(session)
        envelope = dict(app_id=app_id, operation='native.studio.source', input=body)
        with bound_owner(self.service.store, envelope, self.identities, session, user):
            with protected(self.service.store, envelope):
                with connection(self.service.store.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    job = self._job(db, app_id, user['principal'], job_id)
                    if job['status'] != 'PREPARED' or packet_hash != job['packet_hash']:
                        raise Invalid('Studio render is not current')
                    project = self._current(db, app_id, dict(project_id=job['project_id'], revision=job['revision'], source_hash=job['source_hash']))
                    packet = self._packet(db, app_id, project)
                    if packet['packet_hash'] != packet_hash or not any(
                        x.get('media', {}).get('id') == media_id and x.get('media', {}).get('sha256') == sha256
                        for x in packet['scene']['scenes']):
                        raise Invalid('Source is not bound to this render')
                    row = db.execute('SELECT * FROM managed_media WHERE app_id=? AND id=?', (app_id, media_id)).fetchone()
                    data = _decode_data(row)
                    return _file_path(self.service.store, app_id, data['storage_name'])
