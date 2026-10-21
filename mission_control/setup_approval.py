"""Explicit local setup approval; source observations never grant provider authority."""
import json
import re
from .common import Invalid, canonical, digest, identifier, now
from .db import connection
from .store import app_data, audit
from .setup_discovery import proposal, currentness

EDITABLE = {'name', 'job', 'audience', 'locale', 'store_app_id', 'android_package', 'android_track'}


def request(body):
    """Only explicitly selected public setup fields can enter a local manifest update."""
    keys = {'app_id', 'id', 'proposal_hash', 'app_version', 'app_hash', 'changes', 'confirm_apply'}
    if not isinstance(body, dict) or set(body) != keys or body['confirm_apply'] is not True:
        raise Invalid('Approve the exact selected setup edits')
    identity_fields(body)
    changes = body['changes']
    if not isinstance(changes, dict) or not changes or set(changes) - EDITABLE:
        raise Invalid('Select supported setup fields only; no empty approval or authority changes')
    return {key: selected_value(key, value) for key, value in changes.items()}


def identity_fields(body):
    """Malformed JSON types never reach a SQLite binding or widen the selected app."""
    identifier(body['app_id'])
    if type(body['app_version']) is not int:
        raise Invalid('Review the exact current app version')
    if not isinstance(body['id'], str) or not re.fullmatch(r'[a-f0-9-]{36}', body['id']):
        raise Invalid('Choose a saved setup proposal')
    for key in ('proposal_hash', 'app_hash'):
        if not isinstance(body[key], str) or not re.fullmatch(r'[a-f0-9]{64}', body[key]):
            raise Invalid('Review the exact current setup source hash')


def selected_value(field, value):
    """Validate explicit review edits without silently truncating or inventing values."""
    if not isinstance(value, str) or not value.strip() or len(value) > 600:
        raise Invalid('Selected setup values must be nonempty text up to 600 characters')
    result = value.strip()
    validate_field(field, result)
    return result


def validate_field(field, value):
    """Use explicit identity syntax; never normalize an invented country or app ID."""
    if field == 'store_app_id' and not re.fullmatch(r'[1-9][0-9]{0,19}', value):
        raise Invalid('Use the exact positive numeric Apple Store app ID')
    if field == 'locale' and not re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', value):
        raise Invalid('Use an explicit locale language tag, for example en-GB')


def source_guard(app, row, body):
    """Reject changed, foreign, expired or already applied proposals before any mutation."""
    if body['app_id'] != app['id'] or body['proposal_hash'] != row['hash']:
        raise Invalid('Setup proposal source differs; reload this app before approval')
    if type(body['app_version']) is not int or body['app_version'] != app['version'] or body['app_hash'] != digest(app['data']):
        raise Invalid('App setup changed; rediscover or review the current app')
    if row['state'] != 'PENDING' or currentness(app, row) != 'PENDING':
        raise Invalid('Setup proposal is expired, changed or already applied; inspect history or rediscover')


def provenance(app, row, changes):
    """Bind each value to its observed source or explicit human edit, without claiming truth."""
    existing = app['data'].get('setup_sources', {})
    if not isinstance(existing, dict):
        raise Invalid('Saved setup provenance needs review before replacement')
    result = dict(existing)
    data = row['data']
    for key, value in changes.items():
        candidates = data['projection']['fields'].get(key, [])
        match = next((item for item in candidates if item['value'] == value), None)
        result[key] = dict(value_sha256=digest(value), proposal_id=row['id'], proposal_hash=row['hash'],
                           source_url=data['source_url'], source_sha256=data['source_sha256'], observed_at=data['observed_at'],
                           basis=match['basis'] if match else 'EXPLICIT_REVIEW_EDIT',
                           label='PUBLIC_METADATA_UNVERIFIED' if match else 'HUMAN_EDIT',
                           ownership='NOT_VERIFIED', product_claims='NOT_VERIFIED')
    return result


def apply(store, app_id, body):
    """Commit the approved subset and proposal result atomically, preserving other app data."""
    changes = request(body)
    store.app(app_id)
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        saved = db.execute('SELECT id,data,version FROM apps WHERE id=?', (app_id,)).fetchone()
        app = dict(id=saved['id'], data=json.loads(saved['data']), version=saved['version'])
        row = proposal(db, app_id, body['id'])
        source_guard(app, row, body)
        data = app_data(dict(app['data'], **changes, setup_sources=provenance(app, row, changes)))
        stamp = now()
        result = dict(status='APPLIED', app_id=app_id, proposal_id=row['id'], app_version=app['version'] + 1,
                      changed_fields=sorted(changes), external_writes=False, provider_permissions='UNCHANGED', readiness='NOT_VERIFIED')
        db.execute('UPDATE apps SET data=?,version=version+1,updated=? WHERE id=? AND version=?',
                   (canonical(data), stamp, app_id, app['version']))
        updated = db.execute("UPDATE setup_proposals SET state='APPLIED',result=?,updated=? WHERE app_id=? AND id=? AND state='PENDING'",
                             (canonical(result), stamp, app_id, row['id'])).rowcount
        if updated != 1:
            raise Invalid('Proposal changed before approval; reload current setup')
        audit(db, app_id, 'setup.proposal_applied', dict(proposal_id=row['id'], proposal_hash=row['hash'], fields=sorted(changes)))
    return result
