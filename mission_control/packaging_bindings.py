"""Reuse native app/source/rights evidence without granting execution authority."""
import sqlite3
from .common import Invalid, digest
from .funnel_store import creative_binding
from .creative_library import latest_capture
from .creative_briefs import bound_record, asset_checked, latest_proof
from .discovery_store import latest as research


def matching(row, ref):
    """A known identity with wrong bytes or an obsolete revision is rejected."""
    if row['version']!=ref['version'] or row['hash']!=ref['sha256']:
        raise Invalid('Packaging reference revision or hash changed')
    if digest(row['data'])!=row['hash']:raise Invalid('Packaging source integrity changed')
    return dict(ref)


def record(db, store, app_id, ref, app):
    """Use the existing product evidence and authentic asset checks."""
    kind=ref['kind'].lower();row=bound_record(db, app_id, ref['id'], kind, app['data'])
    expected=digest(dict(kind=kind, data=row['data'], source=row['source']))
    if row['version']!=ref['version'] or row['hash']!=ref['sha256'] or expected!=row['hash']:
        raise Invalid('Packaging product evidence revision or hash changed')
    if kind=='asset':asset_checked(store, app_id, row['data'])
    else:latest_proof(db, app_id, row, app['data'])
    return dict(ref)


def collection(db, app_id, ref, app):
    """Bind existing collections and recheck each captured source on readback."""
    row=research(db, app_id, ref['id'], 'COLLECTION');matching(row, ref);data=row['data']
    if data['manifest_version']!=app['version'] or data['app_hash']!=app['hash']:
        raise Invalid('Research collection app context changed')
    for item in data['results']:
        source=latest_capture(db, app_id, item['reference_id'])
        if source['hash']!=item['source_hash'] or source['version']!=item['source_version']:raise Invalid('Research collection source changed')
        if digest(source['data'])!=source['hash']:raise Invalid('Research source integrity changed')
        collection_review(db, app_id, item.get('review'))
    return dict(ref)


def collection_review(db, app_id, review):
    """A changed inspection invalidates the collection interpretation it supported."""
    if review is None:return
    current=research(db, app_id, review['id'], 'REVIEW')
    if current['version']!=review['version'] or current['hash']!=review['hash']:
        raise Invalid('Research collection review changed')


def resolve(db, store, app_id, ref, app):
    """Dispatch only declared kinds to current native evidence resolvers."""
    kind=ref['kind']
    if kind=='SOURCE':return matching(latest_capture(db, app_id, ref['id']), ref)
    if kind=='COLLECTION':return collection(db, app_id, ref, app)
    if kind=='BRIEF':return creative_binding(db, store, app_id, ref)
    if kind in {'CLAIM', 'ASSET'}:return record(db, store, app_id, ref, app)
    if kind=='MEDIA':
        from .managed_media_store import derivative_snapshot
        view,_=derivative_snapshot(db, store, app_id, ref['id'], ref['sha256'])
        if view['review_version']!=ref['version']:raise Invalid('Media reuse revision changed')
        return dict(ref)
    raise Invalid('Unsupported packaging evidence kind')


def variant_binding(db, store, app_id, ref, app):
    """Shot revisions require the current immutable variant and its live bindings."""
    from .packaging_store import latest, decode, frozen
    row=decode(latest(db, app_id, ref['id'], 'VARIANT'));matching(row, ref)
    if frozen(db, store, app_id, 'VARIANT', row['data']['definition'], app)!=row['data']:
        raise Invalid('Packaging variant sources changed')
    return dict(ref)


def shot_claims(db, app_id, shots):
    """A proof link cannot turn unrelated copy into a supported product claim."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    import json
    for shot in shots:
        if not shot['claim_text'] or not shot['claims']:continue
        texts=[]
        for ref in shot['claims']:
            row=db.execute("SELECT data FROM records WHERE app_id=? AND id=? AND kind='claim'", (app_id, ref['id'])).fetchone()
            if row is None:raise Invalid('Claim proof does not belong to this app')
            texts.append(json.loads(row['data']).get('claim'))
        if shot['claim_text'] not in texts:raise Invalid('Shot claim text must match selected app proof')
