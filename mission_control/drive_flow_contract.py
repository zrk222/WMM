"""Frozen Drive consent context and redacted progress; prepared is never connected."""
import json
from .common import Invalid, digest
from .drive_auth import SCOPE
from .drive_secrets import reference

LIVE = ('PENDING', 'EXCHANGING', 'AWAITING_ACCOUNT')
PERMISSION = 'Google grants access to selected files, including modification permission; WMM uses provider reads only. Selection does not grant adaptation or publication rights.'


def decoded(row):
    """Internal SQL rows never become public status objects directly."""
    if row is None:raise Invalid('Drive consent was not found in this app; start a new selection')
    value = dict(row)
    try:
        value['data'] = json.loads(value['data'])
        value['result'] = json.loads(value['result']) if value['result'] else None
    except (ValueError, TypeError, RecursionError):
        raise Invalid('Drive consent metadata is invalid; start a new selection') from None
    return value


def request(body):
    """Owner approval must refer to current exact app and prior connection revisions."""
    keys = {'client_json', 'manifest_version', 'connection_id', 'connection_version', 'confirm_scope'}
    if not isinstance(body, dict) or set(body) != keys or body['confirm_scope'] is not True:
        raise Invalid('Approve the displayed selected-file Drive permission and current app setup')
    for field in ('manifest_version', 'connection_version'):
        if type(body[field]) is not int or body[field] < 0:
            raise Invalid('Reload the app and Drive connection before preparing consent')
    if body['connection_id'] is not None:reference(body['connection_id'])
    return {key: body[key] for key in keys}


def source_guard(db, frozen):
    """Connection revision checks serialize setup against replacement and disconnect."""
    app = db.execute('SELECT version FROM apps WHERE id=?', (frozen['app_id'],)).fetchone()
    if app is None or app['version'] != frozen['manifest_version']:
        raise Invalid('App setup changed; prepare new Drive consent')
    old = db.execute('SELECT * FROM drive_connections WHERE app_id=?', (frozen['app_id'],)).fetchone()
    current = (old['id'], old['version']) if old else (None, 0)
    if current != (frozen['connection_id'], frozen['connection_version']):
        raise Invalid('Drive connection changed; reload before selecting files')
    return old


def binding(row):
    """Protect the exact immutable flow context, not just its visible client identity."""
    keys = ('id', 'app_id', 'manifest_version', 'connection_id', 'connection_version', 'state_hash', 'expires', 'data')
    return digest({key: row[key] for key in keys})


def public(row):
    """No callback proof, native address, token or client configuration is exposed."""
    return {key: row[key] for key in ('id', 'status', 'expires', 'created', 'updated', 'result')}


def summary(rows, cleanup_pending):
    """Bounded local preparation state cannot imply an active provider connection."""
    return dict(flows=[public(row) for row in rows], cleanup_pending=cleanup_pending,
                scope=SCOPE, permission_summary=PERMISSION,
                scope_of_result='CONSENT_PROGRESS_ONLY', connected_account='NOT_ASSESSED')
