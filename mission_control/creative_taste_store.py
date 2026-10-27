"""Immutable owner-reviewed video direction; preferences are data, never grants."""
import json
import sqlite3
from .common import Invalid, canonical, digest, identifier, now, required, safe_data
from .db import connection
from .pmf_contract import count, exact, one
from .creative_taste import guidance
from .funnel_store import app_context
from .packaging_contract import reference
from .packaging_bindings import resolve
from .operation_authority import PROTECTED, check, store_identity
from .review_access import exact_role

SAVE_FIELDS = {'id', 'version', 'manifest_version', 'policy_sha256', 'data'}


def owner(db, store, app_id):
    """Only exact live protected owner HTTP authority can approve preferences."""
    context = PROTECTED.get()
    if context is None or 'principal' not in context or context['store'] != store_identity(store):
        raise PermissionError('Current protected owner review is required')
    envelope = json.loads(context['envelope'])
    if envelope['app_id'] != app_id or envelope['operation'] != 'packaging.owner':
        raise PermissionError('Owner review belongs to another operation or app')
    principal = check(db, context)
    return dict(principal=principal, role_version=context['role_version'])


def texts(values, maximum, label):
    """Bound user-supplied rules without treating their words as instructions."""
    if not isinstance(values, list) or len(values) > maximum:
        raise Invalid(label + ' exceeds its declared list limit')
    return [required(value, label, 4000) for value in values]


def definition(value):
    """Closed taste fields retain source labels separately from interpretation."""
    safe_data(value)
    exact(value, {'lens', 'voice', 'visual', 'examples', 'exclusions'})
    examples = value['examples']
    if not isinstance(examples, list) or len(examples) > 12:
        raise Invalid('Choose at most 12 taste examples')
    result = dict(lens=one(value['lens'], set(guidance()['lenses']), 'Taste lens'),
                  voice=required(value['voice'], 'Voice rules', 4000),
                  visual=required(value['visual'], 'Visual rules', 4000),
                  exclusions=texts(value['exclusions'], 20, 'Exclusion'), examples=[])
    for row in examples:
        exact(row, {'reference', 'interpretation'})
        ref = reference(row['reference'], {'SOURCE', 'ASSET', 'MEDIA'})
        result['examples'].append(dict(reference=ref, interpretation=required(row['interpretation'], 'Example interpretation', 4000)))
    identities = [canonical(row['reference']) for row in result['examples']]
    if len(set(identities)) != len(identities):raise Invalid('Choose distinct taste examples')
    return result


def normalize(body):
    """A policy change or forged approval field cannot enter saved guidance."""
    exact(body, SAVE_FIELDS)
    if body['policy_sha256'] != guidance()['policy_sha256']:
        raise Invalid('Creative guidance policy changed; inspect current guidance')
    return dict(id=identifier(body['id']), version=count(body['version'], 0, 99),
                manifest_version=count(body['manifest_version'], 1, 2147483647),
                policy_sha256=body['policy_sha256'], definition=definition(body['data']))


def bindings(db, store, app_id, value, app):
    """Examples retain current evidence identity without acquiring media rights."""
    return [resolve(db, store, app_id, row['reference'], app) for row in value['examples']]


def latest(db, app_id, identity):
    """Resolve only this app's immutable guidance history."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    return db.execute('SELECT * FROM creative_taste_reviews WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1', (app_id, identity)).fetchone()


def decode(row):
    """Reject corrupted guidance before presenting any review status."""
    if row is None:raise Invalid('Taste review does not belong to this app')
    value = dict(row);value['data'] = json.loads(value['data'])
    if digest(value['data']) != value['hash']:raise Invalid('Taste review integrity changed')
    return value


def current(db, store, app_id, value):
    """Saved owner review stays historical when owner, app, policy or examples drift."""
    data = value['data'];app = app_context(db, app_id)
    if data['manifest_version'] != app['version'] or data['app_hash'] != app['hash']:
        raise Invalid('App changed after the taste review')
    if data['policy_sha256'] != guidance()['policy_sha256']:
        raise Invalid('Creative guidance policy changed after review')
    reviewer = data['reviewer']
    exact_role(db, app_id, reviewer['principal'], reviewer['role_version'], 'OWNER')
    if bindings(db, store, app_id, data['definition'], app) != data['bindings']:
        raise Invalid('Taste example evidence changed after review')


def readback(db, store, app_id, row):
    """Make currentness explicit while preserving original reviewed bytes."""
    value = decode(row)
    try:
        current(db, store, app_id, value);status = 'CURRENT_OWNER_REVIEW';reason = None
    except (Invalid, PermissionError, OSError) as error:
        status = 'STALE_OWNER_REVIEW';reason = str(error)
    return dict(value, source_status=status, source_reason=reason,
                execution_authority=False, reuse_authority=False, render='NOT_RUN', publication='NOT_RUN')


def save(store, app_id, body):
    """Append guidance under exact current owner authority in one transaction."""
    request = normalize(body)
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE');reviewer = owner(db, store, app_id)
        app = app_context(db, app_id, request['manifest_version'])
        old = latest(db, app_id, request['id'])
        if (old['version'] if old else 0) != request['version']:raise Invalid('Taste revision changed; inspect saved history')
        if db.execute('SELECT count(*) FROM creative_taste_reviews WHERE app_id=?', (app_id,)).fetchone()[0] >= 2000:
            raise Invalid('Taste history limit is 2000 revisions per app')
        data = dict(manifest_version=app['version'], app_hash=app['hash'], policy_sha256=request['policy_sha256'],
                    definition=request['definition'], reviewer=reviewer,
                    bindings=bindings(db, store, app_id, request['definition'], app))
        stamp = now();hashed = digest(data);version = request['version'] + 1
        db.execute('INSERT INTO creative_taste_reviews VALUES(?,?,?,?,?,?)', (app_id, request['id'], version, canonical(data), hashed, stamp))
        db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)', (app_id, 'packaging.taste-review', canonical(dict(id=request['id'], version=version, hash=hashed)), stamp))
        result = readback(db, store, app_id, latest(db, app_id, request['id']))
        if result['source_status'] != 'CURRENT_OWNER_REVIEW':raise Invalid('Taste evidence changed before commit')
        return result


def read(store, app_id, body):
    """Read an exact historical revision or latest without granting execution."""
    from .operation_catalog import exact_keys
    exact_keys(body, {'id'}, {'version'})
    identity = identifier(body['id'])
    with connection(store.path) as db:
        app_context(db, app_id);row = latest(db, app_id, identity)
        if 'version' in body:
            version = count(body['version'], 1, 100)
            row = db.execute('SELECT * FROM creative_taste_reviews WHERE app_id=? AND id=? AND version=?', (app_id, identity, version)).fetchone()
        return readback(db, store, app_id, row)


def reconcile(store, app_id, body):
    """Observe an uncertain save without replaying it or asserting caller identity."""
    request = normalize(body);expected = request['version'] + 1
    with connection(store.path) as db:
        app_context(db, app_id);owner(db, store, app_id)
        row = db.execute('SELECT * FROM creative_taste_reviews WHERE app_id=? AND id=? AND version=?', (app_id, request['id'], expected)).fetchone()
        value = None;status = 'NO_REVISION_OBSERVED'
        if row is not None:
            value = readback(db, store, app_id, row);data = value['data']
            matches = data['manifest_version'] == request['manifest_version'] and data['policy_sha256'] == request['policy_sha256'] and data['definition'] == request['definition']
            status = 'MATCHING_REVISION_OBSERVED' if matches else 'DIFFERENT_REVISION_OBSERVED'
        return dict(status=status, document=value, expected_revision=expected, automatic_retry=False,
                    caller_commit_identity='NOT_PROVEN', execution_authority=False)


def dispatch(store, app_id, action, body):
    """Keep the owner review route closed; agent proposals cannot approve themselves."""
    handlers = {'taste-review': save, 'taste-read': read, 'taste-reconcile': reconcile}
    return handlers[action](store, app_id, body)
