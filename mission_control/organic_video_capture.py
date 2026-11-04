"""Owner-selected organic demo intake using the existing managed media library."""

import hashlib
import json
import re

from .common import Invalid, identifier
from .db import connection
from .managed_media_store import MAX_BYTES, Media, derivative_snapshot
from .operation_authority import REQUEST, protected
from .review_access import exact_role


OPERATION = 'organic-video.import-demo'
SOURCE = 'OWNER_SELECTED_DEMO_MP4'
_FIELDS = {
    'request_id', 'manifest_version', 'release', 'filename', 'source',
    'app_owned', 'contains_private_data', 'uses_personal_account',
}


def intake_envelope(app_id, selection, raw):
    """Bind a trusted file picker's exact bytes to a fresh owner admission."""
    if identifier(app_id) != app_id:
        raise Invalid('Use the exact app ID')
    if not isinstance(selection, dict) or set(selection) != _FIELDS:
        raise Invalid('Use exact demo selection fields')
    if (selection['source'] != SOURCE or selection['app_owned'] is not True
            or selection['contains_private_data'] is not False
            or selection['uses_personal_account'] is not False):
        raise Invalid('Select app-owned demo footage without private data or personal accounts')
    for field, pattern in (
        ('request_id', r'[A-Za-z0-9_-]{1,100}'),
        ('release', r'[A-Za-z0-9][A-Za-z0-9 .+_()\-]{0,79}'),
        ('filename', r'[A-Za-z0-9][A-Za-z0-9 ._\-]{0,119}\.[mM][pP]4'),
    ):
        if not isinstance(selection[field], str) or not re.fullmatch(pattern, selection[field]):
            raise Invalid(f'Invalid demo {field}; choose a local MP4 basename and bounded release fields')
    version = selection['manifest_version']
    if type(version) is not int or not 1 <= version <= 2147483647:
        raise Invalid('Use the exact current app manifest version')
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES:
        raise Invalid('Choose original MP4 bytes within the 64 MiB media bound')
    return dict(app_id=app_id, operation=OPERATION,
                input=dict(selection, source_sha256=hashlib.sha256(raw).hexdigest(), byte_count=len(raw)))


def _current_release(db, app_id, version, release):
    row = db.execute('SELECT version,data FROM apps WHERE id=?', (app_id,)).fetchone()
    if row is None or row['version'] != version or json.loads(row['data']).get('release') != release:
        raise Invalid('Demo selection does not match the current app release and manifest')


def import_owner_demo(store, app_id, selection, raw):
    """Import one selected MP4 under its exact bound owner operation.

    The trusted transport must first authenticate the owner and bind the envelope
    returned by intake_envelope. The attestations describe the owner's selection.
    They are not content scanning or rights approval.
    """
    envelope = intake_envelope(app_id, selection, raw)
    authority = REQUEST.get()
    if not authority or 'principal' not in authority or 'grant_id' in authority:
        raise PermissionError('A current owner session is required for demo import')
    selected = envelope['input']
    version, release = selected['manifest_version'], selected['release']
    with protected(store, envelope) as principal:
        with connection(store.path) as db:
            _current_release(db, app_id, version, release)
        provenance = dict(kind=SOURCE, release=release, owner_principal=principal,
                          owner_role_version=authority['role_version'],
                          app_owned=True, contains_private_data=False, uses_personal_account=False)
        upload = dict(manifest_version=version, request_key='organic-demo:' + selected['request_id'])
        # The trusted provenance seam is shared with provider media import.
        # Media owns request replay, validation, commit-time manifest checks and byte retention.
        item = Media(store)._ingest(app_id, selected['filename'], raw, upload, lambda: None, provenance)
    return dict(app_id=app_id, release=release, manifest_version=version, media_id=item['id'],
                media_record_sha256=item['hash'], source_sha256=item['source_sha256'],
                byte_count=item['bytes'], source=SOURCE, rights_authority='SEPARATE_OWNER_REVIEW')


def demo_snapshot(db, store, app_id, media_id, source_sha256, *, capture=False):
    """Read current app-owned demo footage for downstream derivative admission."""
    if type(capture) is not bool:
        raise Invalid('Capture must be a boolean')
    item, raw = derivative_snapshot(db, store, app_id, media_id, source_sha256, capture=capture)
    provenance = item['provenance']
    if (not isinstance(provenance, dict)
            or set(provenance) != {'kind', 'release', 'owner_principal', 'owner_role_version',
                                   'app_owned', 'contains_private_data', 'uses_personal_account'}
            or provenance.get('kind') != SOURCE
            or provenance.get('app_owned') is not True or provenance.get('contains_private_data') is not False
            or provenance.get('uses_personal_account') is not False):
        raise Invalid('Select footage from an owner-attested organic demo import')
    _current_release(db, app_id, item['manifest_version'], provenance['release'])
    exact_role(db, app_id, provenance['owner_principal'], provenance['owner_role_version'], 'OWNER')
    if item['latest_review']['basis'] != 'OWNED':
        raise Invalid('Organic demo footage requires current owner review with an OWNED basis')
    return item, raw
