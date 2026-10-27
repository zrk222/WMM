"""App-scoped append-only packaging drafts and script-linked preproduction shots."""
import sqlite3
import json
from .common import Invalid, canonical, digest, identifier, now
from .db import connection
from .pmf_contract import count, exact, one
from .funnel_store import app_context
from . import packaging_contract as contract
from .packaging_bindings import resolve, variant_binding, shot_claims


def decode(row):
    """Reject corrupt persisted definitions before returning any evidence status."""
    if row is None:raise Invalid('Packaging document does not belong to this app')
    result=dict(row);result['data']=json.loads(result['data'])
    if digest(result['data'])!=result['hash']:raise Invalid('Packaging document integrity changed')
    return result


def latest(db, app_id, identity, kind):
    """Select one exact app and document kind, never a foreign identity."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    return db.execute('SELECT * FROM packaging_documents WHERE app_id=? AND id=? AND kind=? ORDER BY version DESC LIMIT 1',
                      (app_id, identity, kind)).fetchone()


def references(kind, definition):
    """Enumerate all supplied references; missing evidence remains a draft gap."""
    if kind=='VARIANT':
        result=[*definition['sources'], *definition['app_proofs']]
        if definition['creative'] is not None:result.append(definition['creative'])
        return result
    result=[]
    for shot in definition['shots']:
        result.extend([*shot['assets'], *shot['claims']])
        if shot['source'] is not None:result.append(shot['source'])
    return result


def frozen(db, store, app_id, kind, definition, app):
    """Freeze current bindings without copying restricted source payloads."""
    bindings=[resolve(db, store, app_id, ref, app) for ref in references(kind, definition)]
    if kind=='SHOTS':
        bindings.append(variant_binding(db, store, app_id, definition['variant'], app))
        shot_claims(db, app_id, definition['shots'])
    return dict(definition=definition, manifest_version=app['version'], app_hash=app['hash'], bindings=bindings)


def gaps(kind, definition):
    """Report missing original assets and claim support independently of currentness."""
    if kind=='VARIANT':
        return [key for key in ('sources', 'creative', 'app_proofs') if not definition[key]]
    result=[];covered={shot['segment_id'] for shot in definition['shots']}
    for segment in definition['script']:
        if segment['id'] not in covered:result.append(dict(segment_id=segment['id'], missing='SHOT'))
    for shot in definition['shots']:
        if not shot['assets']:result.append(dict(shot_id=shot['id'], missing='ASSET_AND_RIGHTS'))
        if shot['claim_text'] and not shot['claims']:result.append(dict(shot_id=shot['id'], missing='CLAIM_PROOF'))
    return result


def readback(db, store, app_id, row):
    """Historical definitions stay intact while live currentness is recomputed."""
    item=decode(row);data=item['data'];app=app_context(db, app_id)
    try:
        current=frozen(db, store, app_id, item['kind'], data['definition'], app)==data
        reason=None if current else 'App manifest changed'
    except (Invalid, OSError) as error:current=False;reason=str(error)
    missing=gaps(item['kind'], data['definition'])
    return dict(item, source_status='CURRENT' if current else 'STALE', source_reason=reason,
                missing_evidence=missing, evidence_status='MISSING' if missing else 'SUPPLIED_CURRENT' if current else 'STALE',
                state='DRAFT', render='NOT_RUN', publication='NOT_RUN', execution_authority=False)


class Packaging:
    """Only local preparation, with bounded immutable revision history."""
    def __init__(self, store):self.store=store

    def save(self, app_id, body):
        """Atomically reject obsolete app, source, and document revisions."""
        exact(body, {'id', 'version', 'kind', 'manifest_version', 'data'})
        identity=identifier(body['id']);expected=count(body['version'], 0, 99)
        kind=one(body['kind'], {'VARIANT', 'SHOTS'}, 'Packaging kind')
        definition=contract.variant(body['data']) if kind=='VARIANT' else contract.shotlist(body['data'])
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app=app_context(db, app_id, body['manifest_version'])
            old=db.execute('SELECT * FROM packaging_documents WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1', (app_id, identity)).fetchone()
            if (old['version'] if old else 0)!=expected:raise Invalid('Packaging revision changed; reload')
            if old and old['kind']!=kind:raise Invalid('Packaging identity has another kind')
            if db.execute('SELECT count(*) FROM packaging_documents WHERE app_id=?', (app_id,)).fetchone()[0]>=2000:
                raise Invalid('Packaging history limit is 2000 revisions per app')
            value=frozen(db, self.store, app_id, kind, definition, app);stamp=now();hashed=digest(value)
            db.execute('INSERT INTO packaging_documents VALUES(?,?,?,?,?,?,?)', (app_id, identity, expected+1, kind, canonical(value), hashed, stamp))
            db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',
                       (app_id, 'packaging.'+kind.lower(), canonical(dict(id=identity, version=expected+1, hash=hashed)), stamp))
            result=readback(db, self.store, app_id, latest(db, app_id, identity, kind))
            if result['source_status']!='CURRENT':raise Invalid('Packaging evidence changed before commit')
            return result

    def read(self, app_id, identity, kind, version=None):
        """Read exact history while surfacing current evidence failures separately."""
        identifier(identity);one(kind, {'VARIANT', 'SHOTS'}, 'Packaging kind')
        with connection(self.store.path) as db:
            app_context(db, app_id);row=latest(db, app_id, identity, kind)
            if version is not None:
                count(version, 1, 100)
                row=db.execute('SELECT * FROM packaging_documents WHERE app_id=? AND id=? AND kind=? AND version=?', (app_id, identity, kind, version)).fetchone()
            return readback(db, self.store, app_id, row)

    def list(self, app_id, offset=0):
        """Bound complete history pages to 100 immutable revisions each."""
        count(offset, 0, 2000)
        with connection(self.store.path) as db:
            app_context(db, app_id)
            total=db.execute('SELECT count(*) FROM packaging_documents WHERE app_id=?', (app_id,)).fetchone()[0]
            rows=db.execute('SELECT * FROM packaging_documents WHERE app_id=? ORDER BY created,id,version LIMIT 100 OFFSET ?', (app_id, offset)).fetchall()
            items=[readback(db, self.store, app_id, row) for row in rows];following=offset+len(items)
            return dict(items=items, total=total, offset=offset, limit=100, next_offset=following if following<total else None)
