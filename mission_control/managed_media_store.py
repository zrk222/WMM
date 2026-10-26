"""Immutable app-owned video originals and append-only owner reuse attestations."""
from __future__ import annotations
import sqlite3

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import unicodedata
import uuid

from .common import Invalid, canonical, digest, identifier, now, required, uid
from .db import connection
from .managed_media_validation import inspect
from .review_access import member

MAX_BYTES = 67108864
MAX_ITEMS = 1000
MAX_REVIEWS = 100
MAX_FILENAME_BYTES = 255
MAX_EVIDENCE_CHARS = 1000
SUFFIXES = {'.mp4', '.mov', '.webm'}
_HEX = re.compile(r'[a-f0-9]{64}\Z')
_STORAGE_NAME = re.compile(r'[a-f0-9]{32}\.(?:mp4|mov|webm)\Z')
_FIELDS = {'manifest_version', 'request_key'}
_REVIEW_FIELDS = {'expected_version', 'manifest_version', 'source_sha256', 'status', 'basis', 'evidence'}
_BASES = {'OWNED', 'LICENSED', 'CONSENT'}
_STATUSES = {'ALLOWED', 'REVOKED'}
_REVIEW_ATTESTATION = 'OPERATOR_SUPPLIED_NOT_EXTERNALLY_VERIFIED'


def _integer(value, name, maximum=2147483647):
    if type(value) is not int or not 1 <= value <= maximum:
        raise Invalid(f'{name} must be a positive whole number')
    return value


def _request_key(value):
    if not isinstance(value, str) or not value.strip():
        raise Invalid('Request key must contain 1 through 120 UTF-8 bytes')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise Invalid('Request key must be valid UTF-8 text') from None
    if not 1 <= size <= 120:
        raise Invalid('Request key must contain 1 through 120 UTF-8 bytes')
    if '\x00' in value:
        raise Invalid('Request key contains an unsupported character')
    return value


def _filename(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise Invalid('Choose a video filename with a basename up to 255 UTF-8 bytes')
    basename = unicodedata.normalize('NFC', value.replace('\\', '/').rsplit('/', 1)[-1]).strip().rstrip(' .')
    if not basename or any(ord(char) < 32 for char in basename):
        raise Invalid('Choose a video filename with a usable basename')
    try:
        size = len(basename.encode('utf-8'))
    except UnicodeError:
        raise Invalid('Video filename must be valid UTF-8 text') from None
    if size > MAX_FILENAME_BYTES:
        raise Invalid('Video filename basename exceeds 255 UTF-8 bytes')
    suffix = Path(basename).suffix.lower()
    if suffix not in SUFFIXES:
        raise Invalid('Choose an MP4, MOV or WebM video')
    return basename, suffix


def _upload_body(body):
    if not isinstance(body, dict) or set(body) != _FIELDS:
        raise Invalid('Upload needs exactly manifest_version and request_key')
    return _integer(body['manifest_version'], 'Manifest version'), _request_key(body['request_key'])


def _request_hash(manifest, filename, source_hash, size, provenance=None):
    value = dict(manifest_version=manifest, filename=filename, source_sha256=source_hash, bytes=size)
    if provenance is not None:value['provenance'] = provenance
    return digest(value)


def _manifest(db, app_id, expected):
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    row = db.execute('SELECT version FROM apps WHERE id=?', (app_id,)).fetchone()
    if row is None:
        raise KeyError('App workspace not found')
    if row['version'] != expected:
        raise Invalid('App setup changed. Refresh and reopen the upload before retrying.')
    return row['version']


def _validated(raw, suffix, alive):
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise Invalid('Imported video must contain 1 through 67108864 bytes')
    result = inspect(raw, suffix, alive=alive)
    expected = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    if not isinstance(result, dict) or result.get('sha256') != expected['sha256'] or result.get('bytes') != expected['bytes']:
        raise Invalid('Video inspection did not match the supplied original bytes')
    if set(result) != {'sha256', 'bytes', 'metadata', 'decoded'}:
        raise Invalid('Video inspection returned an unsupported evidence shape')
    metadata, decoded = result['metadata'], result['decoded']
    if not isinstance(metadata, dict) or not isinstance(decoded, dict):
        raise Invalid('Video inspection evidence is malformed')
    if type(metadata.get('audio')) is not bool:
        raise Invalid('Video audio evidence is malformed')
    if type(decoded.get('video_frames')) is not int or decoded['video_frames'] < 1:
        raise Invalid('Video inspection did not prove a decoded picture')
    if type(decoded.get('audio_frames')) is not int or decoded['audio_frames'] < 0:
        raise Invalid('Video decoded audio evidence is malformed')
    if metadata['audio'] != (decoded['audio_frames'] > 0):
        raise Invalid('Video audio metadata differs from decoded audio evidence')
    try:
        if len(canonical(metadata).encode('utf-8')) > 8192 or len(canonical(decoded).encode('utf-8')) > 4096:
            raise Invalid('Video inspection evidence exceeds its storage bound')
    except (TypeError, ValueError, UnicodeError):
        raise Invalid('Video inspection evidence is not finite JSON') from None
    return result


def _linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _identity(info):
    return info.st_dev, info.st_ino


def _plain(path, directory, missing=False):
    try:
        info = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise Invalid('Managed media storage is missing') from None
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if _linked(info) or not expected(info.st_mode):
        raise Invalid('Managed media storage contains a linked or unsupported path')
    return info


def _inside(path, base):
    try:
        return path.resolve(strict=True).is_relative_to(base.resolve(strict=True))
    except (OSError, RuntimeError):
        return False


def _folder(store, app_id, create=False):
    base = Path(store.path).parent.absolute()
    _plain(base, True)
    root = base / 'managed-media'
    target = root / digest(app_id)
    for directory in (root, target):
        info = _plain(directory, True, missing=True)
        if info is None and create:
            try:
                directory.mkdir()
            except FileExistsError:
                pass
            info = _plain(directory, True)
        elif info is None:
            raise Invalid('Managed media storage is missing')
        if not _inside(directory, base):
            raise Invalid('Managed media storage escapes the database parent')
    return target


def _file_path(store, app_id, name, create=False):
    if not isinstance(name, str) or not _STORAGE_NAME.fullmatch(name):
        raise Invalid('Managed media has an invalid private file identifier')
    folder = _folder(store, app_id, create)
    return folder / name


def _path_signature(path, size):
    base = path.parents[2]
    _plain(base, True)
    for directory in (path.parents[1], path.parent):
        _plain(directory, True)
        if not _inside(directory, base):
            raise Invalid('Managed media directory escaped the database parent')
    info = _plain(path, False)
    if info.st_size != size:
        raise Invalid('Managed media original size changed')
    if path.resolve(strict=True).parent != path.parent.resolve(strict=True) or not _inside(path, base):
        raise Invalid('Managed media original escaped its private directory')
    return info


def _read_original(path, size, expected_hash):
    before = _path_signature(path, size)
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        raise Invalid('Managed media original is unavailable') from None
    try:
        opened = os.fstat(descriptor)
        if _linked(opened) or _identity(opened) != _identity(before) or opened.st_size != size:
            raise Invalid('Managed media original changed before it was read')
        chunks, total = [], 0
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            while True:
                chunk = stream.read(min(1048576, size + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > size:
                    raise Invalid('Managed media original grew beyond its stored size')
        after = os.fstat(descriptor)
        current = _path_signature(path, size)
        raw = b''.join(chunks)
        if _identity(after) != _identity(opened) or _identity(current) != _identity(before) or total != size:
            raise Invalid('Managed media original changed while it was read')
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise Invalid('Managed media original digest changed')
        return raw
    finally:
        os.close(descriptor)


def _remove_owned(path, identity):
    if identity is None:
        return
    try:
        base = path.parents[2]
        _plain(base, True)
        for directory in (path.parents[1], path.parent):
            _plain(directory, True)
            if not _inside(directory, base):
                return
        info = _plain(path, False, missing=True)
        if info is not None and _identity(info) == identity and _inside(path, base):
            path.unlink()
    except (Invalid, OSError):
        return


def _write_exclusive(path, raw, alive):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise Invalid('Managed media original could not be stored exclusively') from None
    identity = _identity(os.fstat(descriptor))
    try:
        offset = 0
        while offset < len(raw):
            alive()
            offset += os.write(descriptor, raw[offset:offset + 1048576])
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if info.st_size != len(raw) or _linked(info):
            raise Invalid('Managed media original changed while it was stored')
        stored = _path_signature(path, len(raw))
        if _identity(stored) != identity:
            raise Invalid('Managed media original path changed while it was stored')
        return identity
    except BaseException:
        os.close(descriptor)
        _remove_owned(path, identity)
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass


def _decode_data(row):
    try:
        data = json.loads(row['data'])
        if canonical(data) != row['data']:
            raise ValueError('noncanonical')
        bound = dict(app_id=row['app_id'], id=row['id'], data=row['data'], request_key=row['request_key'],
                     request_hash=row['request_hash'], created=row['created'])
        if digest(bound) != row['hash']:
            raise ValueError('hash')
    except (TypeError, ValueError, KeyError):
        raise Invalid('Managed media record integrity changed') from None
    required_fields = {'manifest_version', 'filename', 'source_sha256', 'bytes', 'metadata', 'decoded',
                       'provenance', 'storage_name', 'rights_status'}
    if not isinstance(data, dict) or set(data) != required_fields or data['rights_status'] != 'UNKNOWN':
        raise Invalid('Managed media record has an unsupported shape')
    if not _HEX.fullmatch(data['source_sha256']) or type(data['bytes']) is not int or not 1 <= data['bytes'] <= MAX_BYTES:
        raise Invalid('Managed media source identity is malformed')
    _integer(data['manifest_version'], 'Manifest version')
    return data


def _review_hash(row):
    try:
        data = json.loads(row['data'])
        if canonical(data) != row['data']:
            raise ValueError('noncanonical')
        bound = dict(app_id=row['app_id'], media_id=row['media_id'], version=row['version'],
                     data=row['data'], created=row['created'])
        if digest(bound) != row['hash']:
            raise ValueError('hash')
    except (TypeError, ValueError, KeyError):
        raise Invalid('Managed media review history integrity changed') from None
    keys = {'manifest_version', 'source_sha256', 'status', 'basis', 'evidence', 'authority',
            'reviewer_principal', 'reviewer_role_version'}
    if not isinstance(data, dict) or set(data) != keys or data['authority'] != _REVIEW_ATTESTATION:
        raise Invalid('Managed media review history has an unsupported shape')
    if data['status'] not in _STATUSES or data['basis'] not in _BASES or not _HEX.fullmatch(data['source_sha256']):
        raise Invalid('Managed media review history contains invalid values')
    if not isinstance(data['evidence'], str) or not 1 <= len(data['evidence']) <= MAX_EVIDENCE_CHARS:
        raise Invalid('Managed media review evidence exceeds its storage bound')
    _integer(data['manifest_version'], 'Manifest version')
    _integer(data['reviewer_role_version'], 'Owner role version')
    if not isinstance(data['reviewer_principal'], str) or not data['reviewer_principal']:
        raise Invalid('Managed media review principal is malformed')
    return data


def _review_envelope(body):
    if not isinstance(body, dict) or set(body) != _REVIEW_FIELDS:
        raise Invalid('Review needs exactly the current version, source hash, decision, basis and evidence')
    expected = body['expected_version']
    if type(expected) is not int or not 0 <= expected < MAX_REVIEWS:
        raise Invalid('Expected review version is outside the allowed range')
    manifest = _integer(body['manifest_version'], 'Manifest version')
    source_hash = body['source_sha256']
    if not isinstance(source_hash, str) or not _HEX.fullmatch(source_hash):
        raise Invalid('Review source digest is malformed')
    status, basis = body['status'], body['basis']
    if not isinstance(status, str) or status not in _STATUSES or not isinstance(basis, str) or basis not in _BASES:
        raise Invalid('Choose ALLOWED or REVOKED and OWNED, LICENSED or CONSENT')
    evidence = body['evidence']
    if not isinstance(evidence, str) or not 1 <= len(evidence) <= MAX_EVIDENCE_CHARS:
        raise Invalid('Review evidence must contain 1 through 1000 characters')
    try:
        if len(evidence.encode('utf-8')) > 4000:
            raise Invalid('Review evidence must contain 1 through 1000 characters')
    except UnicodeError:
        raise Invalid('Review evidence must be valid UTF-8 text') from None
    return dict(expected_version=expected, manifest_version=manifest, source_sha256=source_hash,
                status=status, basis=basis, evidence=evidence)


def _principal(user):
    if not isinstance(user, dict):
        raise PermissionError('A current app OWNER identity is required')
    value = required(user.get('principal'), 'Authenticated principal', 200)
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise Invalid('Authenticated principal must be valid UTF-8 text') from None
    return value


def _history(db, app_id, media_id):
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    rows = db.execute('SELECT * FROM managed_media_reviews WHERE app_id=? AND media_id=? ORDER BY version',
                      (app_id, media_id)).fetchall()
    if len(rows) > MAX_REVIEWS:
        raise Invalid('Managed media review history exceeds its retained limit')
    public, latest = [], None
    for expected, row in enumerate(rows, 1):
        if row['version'] != expected:
            raise Invalid('Managed media review history is not append-only')
        data = _review_hash(row)
        latest = data
        public.append(dict(version=expected, manifest_version=data['manifest_version'],
                           source_sha256=data['source_sha256'], status=data['status'], basis=data['basis'],
                           evidence=data['evidence'], authority=data['authority'], created=row['created']))
    return public, latest


def _reviewer_current(db, app_id, review):
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    row = db.execute('SELECT role,status,version FROM operator_roles WHERE app_id=? AND principal=?',
                     (app_id, review['reviewer_principal'])).fetchone()
    return bool(row and row['role'] == 'OWNER' and row['status'] == 'ACTIVE' and
                row['version'] == review['reviewer_role_version'])


def _public(db, store, app_id, row, include_history=False, verify_bytes=False, original_verified=False):
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    data = _decode_data(row)
    path = _file_path(store, app_id, data['storage_name'])
    _path_signature(path, data['bytes'])
    if verify_bytes:
        _read_original(path, data['bytes'], data['source_sha256'])
    reviews, latest = _history(db, app_id, row['id'])
    version = db.execute('SELECT version FROM apps WHERE id=?', (app_id,)).fetchone()
    if version is None:
        raise KeyError('App workspace not found')
    current_version = version['version']
    rights, reason = 'UNKNOWN', 'NO_REVIEW'
    if latest:
        if latest['manifest_version'] != current_version or latest['source_sha256'] != data['source_sha256']:
            rights, reason = 'STALE', 'SOURCE_OR_MANIFEST_CHANGED'
        elif latest['status'] == 'ALLOWED' and not _reviewer_current(db, app_id, latest):
            rights, reason = 'STALE', 'REVIEWER_ROLE_CHANGED'
        else:
            rights = latest['status']
            reason = 'OWNER_REVOKED' if rights == 'REVOKED' else 'CURRENT_OWNER_ATTESTATION'
    result = dict(app_id=app_id, id=row['id'], hash=row['hash'], created=row['created'],
                  manifest_version=data['manifest_version'], filename=data['filename'],
                  source_sha256=data['source_sha256'], bytes=data['bytes'], metadata=data['metadata'],
                  decoded=data['decoded'], provenance=data['provenance'], rights_status=rights,
                  rights_reason=reason, reuse_available=rights == 'ALLOWED', review_version=len(reviews),
                  review_history_status='AVAILABLE', upload_request_key_sha256=hashlib.sha256(row['request_key'].encode('utf-8')).hexdigest(),
                  source_integrity='VERIFIED' if verify_bytes or original_verified else 'PRESENT_UNVERIFIED')
    if latest:
        result['latest_review'] = dict(version=len(reviews), manifest_version=latest['manifest_version'],
                                       source_sha256=latest['source_sha256'], status=latest['status'],
                                       basis=latest['basis'], evidence=latest['evidence'],
                                       authority=latest['authority'], created=reviews[-1]['created'])
    if include_history:
        result['review_history'] = reviews
    return result


class Media:
    """Private app-scoped media intake, owner review and fail-closed resolution."""
    def __init__(self, store):
        self.store = store

    def upload(self, app_id, filename, raw, body, alive=lambda: None):
        """Validate exact bytes, then immutably retain them under a generated name."""
        return self._ingest(app_id, filename, raw, body, alive)

    def _ingest(self, app_id, filename, raw, body, alive, provenance=None):
        """Server-side provider intake shares byte validation; public upload has no provenance field."""
        alive()
        app_id = identifier(app_id)
        manifest, request_key = _upload_body(body)
        basename, suffix = _filename(filename)
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
            raise Invalid('Imported video must contain 1 through 67108864 bytes')
        with connection(self.store.path) as db:
            _manifest(db, app_id, manifest)
            prior = db.execute('SELECT * FROM managed_media WHERE app_id=? AND request_key=?',
                               (app_id, request_key)).fetchone()
            if prior:
                result = self._replay(db, app_id, prior, manifest, basename, raw, provenance)
                alive()
                return result
        result = _validated(raw, suffix, alive)
        request_hash = _request_hash(manifest, basename, result['sha256'], result['bytes'], provenance)
        return self._commit_upload(app_id, manifest, request_key, request_hash, basename, raw, result, alive, provenance)

    def _replay(self, db, app_id, row, manifest, filename, raw, provenance=None):
        data = _decode_data(row)
        request_hash = _request_hash(manifest, filename, hashlib.sha256(raw).hexdigest(), len(raw), provenance)
        if row['request_hash'] != request_hash:
            raise Invalid('Request key already belongs to a different media upload')
        _read_original(_file_path(self.store, app_id, data['storage_name']), data['bytes'], data['source_sha256'])
        return _public(db, self.store, app_id, row, verify_bytes=True)

    def _commit_upload(self, app_id, manifest, key, request_hash, filename, raw, inspected, alive, provenance=None):
        media_id = uid()
        storage_name = uuid.uuid4().hex + Path(filename).suffix.lower()
        path = _file_path(self.store, app_id, storage_name, create=True)
        source_data = dict(manifest_version=manifest, filename=filename, source_sha256=inspected['sha256'],
                           bytes=inspected['bytes'], metadata=inspected['metadata'], decoded=inspected['decoded'],
                           provenance=provenance if provenance is not None else dict(kind='LOCAL_UPLOAD', filename=filename), storage_name=storage_name,
                           rights_status='UNKNOWN')
        created, committed, identity = False, False, None
        try:
            with connection(self.store.path) as db:
                db.execute('BEGIN IMMEDIATE')
                _manifest(db, app_id, manifest)
                prior = db.execute('SELECT * FROM managed_media WHERE app_id=? AND request_key=?',
                                   (app_id, key)).fetchone()
                if prior:
                    result = self._replay(db, app_id, prior, manifest, filename, raw, provenance)
                    alive()
                    return result
                count = db.execute('SELECT count(*) FROM managed_media WHERE app_id=?', (app_id,)).fetchone()[0]
                if count >= MAX_ITEMS:
                    raise Invalid('App media library already contains 1000 retained items')
                _folder(self.store, app_id, create=True)
                identity = _write_exclusive(path, raw, alive)
                created = True
                alive()
                stamp, encoded = now(), canonical(source_data)
                row_hash = digest(dict(app_id=app_id, id=media_id, data=encoded, request_key=key,
                                       request_hash=request_hash, created=stamp))
                db.execute('INSERT INTO managed_media(app_id,id,data,hash,request_key,request_hash,created) VALUES(?,?,?,?,?,?,?)',
                           (app_id, media_id, encoded, row_hash, key, request_hash, stamp))
            committed = True
            return self.read(app_id, media_id)
        except BaseException:
            if created and not committed:
                _remove_owned(path, identity)
            raise

    def list(self, app_id):
        """Return bounded metadata without storage paths, source bytes or raw keys."""
        app_id = identifier(app_id)
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = db.execute('SELECT * FROM managed_media WHERE app_id=? ORDER BY created DESC,id LIMIT ?',
                              (app_id, MAX_ITEMS)).fetchall()
            return dict(items=[_public(db, self.store, app_id, row) for row in rows])

    def sources(self, app_id):
        """Project bounded source selection metadata without owner evidence or file access."""
        rows = self.list(app_id)['items']
        fields = ('id', 'manifest_version', 'source_sha256', 'bytes', 'metadata', 'decoded',
                  'rights_status', 'reuse_available', 'review_version', 'source_integrity')
        return dict(app_id=app_id, items=[dict(kind='MANAGED', **{key: row[key] for key in fields}) for row in rows],
                    source_bytes_access=False, review_authority=False,
                    next_action='Select current approved sources for a shared editor project; save and render reverify source bytes and owner reuse.')

    def read(self, app_id, media_id):
        """Verify exact retained original bytes and expose bounded review history."""
        app_id = identifier(app_id)
        media_id = required(media_id, 'Media ID', 60)
        self.store.app(app_id)
        with connection(self.store.path) as db:
            row = db.execute('SELECT * FROM managed_media WHERE app_id=? AND id=?', (app_id, media_id)).fetchone()
            if row is None:
                raise Invalid('Media does not belong to this app')
            return _public(db, self.store, app_id, row, include_history=True, verify_bytes=True)

    def original(self, app_id, media_id, principal):
        """Return one OWNER-authorized, hash-checked byte snapshot without exposing its path."""
        app_id = identifier(app_id)
        media_id = required(media_id, 'Media ID', 60)
        principal = required(principal, 'Authenticated principal', 200)
        try:
            principal.encode('utf-8')
        except UnicodeError:
            raise Invalid('Authenticated principal must be valid UTF-8 text') from None
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            member(db, app_id, principal, 'OWNER')
            row = db.execute('SELECT * FROM managed_media WHERE app_id=? AND id=?', (app_id, media_id)).fetchone()
            if row is None:
                raise Invalid('Media does not belong to this app')
            data = _decode_data(row)
            path = _file_path(self.store, app_id, data['storage_name'])
            raw = _read_original(path, data['bytes'], data['source_sha256'])
            item = _public(db, self.store, app_id, row, include_history=True, original_verified=True)
            return item, raw

    def review(self, app_id, media_id, body, user):
        """Append a current database-owner attestation without certifying its claim."""
        app_id = identifier(app_id)
        media_id = required(media_id, 'Media ID', 60)
        request = _review_envelope(body)
        principal = _principal(user)
        self._append_review(app_id, media_id, request, principal)
        return self.read(app_id, media_id)

    def _append_review(self, app_id, media_id, request, principal):
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            _manifest(db, app_id, request['manifest_version'])
            member_row = member(db, app_id, principal, 'OWNER')
            row = db.execute('SELECT * FROM managed_media WHERE app_id=? AND id=?', (app_id, media_id)).fetchone()
            if row is None:
                raise Invalid('Media does not belong to this app')
            data = _decode_data(row)
            if request['source_sha256'] != data['source_sha256']:
                raise Invalid('Review does not match the retained original digest')
            _read_original(_file_path(self.store, app_id, data['storage_name']), data['bytes'], data['source_sha256'])
            history, _ = _history(db, app_id, media_id)
            if request['expected_version'] != len(history):
                raise Invalid('Media review changed; reload its current review version')
            if len(history) >= MAX_REVIEWS:
                raise Invalid('Media review history reached its retained limit')
            self._insert_review(db, app_id, media_id, request, principal, member_row['version'])

    @staticmethod
    def _insert_review(db, app_id, media_id, request, principal, role_version):
        if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
        version, stamp = request['expected_version'] + 1, now()
        review_data = dict(manifest_version=request['manifest_version'], source_sha256=request['source_sha256'],
                           status=request['status'], basis=request['basis'], evidence=request['evidence'],
                           authority=_REVIEW_ATTESTATION, reviewer_principal=principal,
                           reviewer_role_version=role_version)
        encoded = canonical(review_data)
        row_hash = digest(dict(app_id=app_id, media_id=media_id, version=version, data=encoded, created=stamp))
        db.execute('INSERT INTO managed_media_reviews(app_id,media_id,version,data,hash,created) VALUES(?,?,?,?,?,?)',
                   (app_id, media_id, version, encoded, row_hash, stamp))

    def resolve(self, app_id, media_id, sha256, require_reuse=True):
        """Return only a verified internal path, requiring current owner review by default."""
        if type(require_reuse) is not bool:
            raise Invalid('Reuse requirement must be a boolean')
        app_id = identifier(app_id)
        media_id = required(media_id, 'Media ID', 60)
        if not isinstance(sha256, str) or not _HEX.fullmatch(sha256):
            raise Invalid('Expected media digest is malformed')
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute('BEGIN')
            row = db.execute('SELECT * FROM managed_media WHERE app_id=? AND id=?', (app_id, media_id)).fetchone()
            if row is None:
                raise Invalid('Media does not belong to this app')
            data = _decode_data(row)
            if data['source_sha256'] != sha256:
                raise Invalid('Selected media digest changed; reload the original')
            view = _public(db, self.store, app_id, row, include_history=True, verify_bytes=True)
            if require_reuse and not view['reuse_available']:
                raise Invalid('Current owner reuse attestation is missing, stale or revoked')
            return _file_path(self.store, app_id, data['storage_name'])


def derivative_snapshot(db, store, app_id, media_id, expected_sha256, capture=False, verify_bytes=True):
    """Resolve current reuse and verified bytes inside the editor's DB snapshot."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    row = db.execute('SELECT * FROM managed_media WHERE app_id=? AND id=?', (app_id, media_id)).fetchone()
    if row is None:
        raise Invalid('Media does not belong to this app')
    data = _decode_data(row)
    if data['source_sha256'] != expected_sha256:
        raise Invalid('Selected media digest changed; reload the original')
    if capture and not verify_bytes:
        raise Invalid('Source byte capture requires integrity verification')
    view = _public(db, store, app_id, row, include_history=True, verify_bytes=verify_bytes)
    if not view['reuse_available']:
        raise Invalid('Current owner reuse attestation is missing, stale or revoked')
    raw = None
    if capture:
        raw = _read_original(_file_path(store, app_id, data['storage_name']), data['bytes'], expected_sha256)
    return view, raw
