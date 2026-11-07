"""Bind original-media editor projects to current shots and owner-reviewed taste."""
import sqlite3
from copy import deepcopy
from .common import Invalid, digest, identifier
from .db import connection
from .pmf_contract import exact, count, hashed
from .funnel_store import app_context
from .packaging_contract import reference
from .packaging_handoff import document
from .creative_taste_store import latest, decode, current


def provenance(value):
    """Retain exact reviewed identities, never executable source or authority."""
    exact(value, {'shots', 'taste'})
    taste = value['taste'];exact(taste, {'id', 'version', 'sha256'})
    return dict(shots=reference(value['shots'], {'SHOTS'}),
                taste=dict(id=identifier(taste['id']), version=count(taste['version'],1,100), sha256=hashed(taste['sha256'])))


def evidence(db, store, app_id, value, manifest):
    """Recheck all sources in the caller's existing project transaction."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    app = app_context(db, app_id, manifest)
    shots = document(db, store, app_id, value['shots'], 'SHOTS')
    if shots['source_status'] != 'CURRENT' or shots['missing_evidence']:
        raise Invalid('Resolve current shot, script, media and claim evidence before editor handoff')
    variant = document(db, store, app_id, shots['data']['definition']['variant'], 'VARIANT')
    creative = variant['data']['definition']
    if variant['source_status'] != 'CURRENT' or not creative['creative'] or not creative['app_proofs']:
        raise Invalid('Choose a current original brief and authentic app proof before editor handoff')
    taste = decode(latest(db, app_id, value['taste']['id']))
    if taste['version'] != value['taste']['version'] or taste['hash'] != value['taste']['sha256']:
        raise Invalid('Taste review revision or hash changed; inspect current owner direction')
    current(db, store, app_id, taste)
    return app, shots, taste


def selected_media(shots):
    """Research footage and still images cannot silently become timed originals."""
    return {(row['id'],row['sha256']) for shot in shots['data']['definition']['shots']
            for row in shot['assets'] if row['kind']=='MEDIA'}


def preserve_origin(before, after):
    """Ordinary editor saves cannot silently discard the reviewed origin."""
    if 'packaging' in before and 'packaging' not in after:
        raise Invalid('Retain the packaging origin when editing this project')


def binding(db, store, app_id, value, manifest):
    """Current saved-data checks also protect later edits and render admission."""
    ref = provenance(value['packaging'])
    app, shots, taste = evidence(db, store, app_id, ref, manifest)
    allowed = selected_media(shots)
    for clip in value['clips']:
        source = clip['source']
        if source['kind'] != 'MANAGED' or (source['id'],source['sha256']) not in allowed:
            raise Invalid('Editor source is not an original clip selected in this shot plan')
        if 'audio' not in clip:raise Invalid('Packaging clips require an explicit retained or muted audio choice')
    return dict(shots=ref['shots'], taste=ref['taste'], app_hash=app['hash'],
                variant=shots['data']['definition']['variant'], policy_sha256=taste['data']['policy_sha256'])


def ordered_clips(rows, shots):
    """Initial handoff covers every shot in order with explicit original-frame cuts."""
    expected = shots['data']['definition']['shots']
    if not isinstance(rows,list) or not 1 <= len(rows) <= 24 or len(rows) != len(expected):
        raise Invalid('Select one original clip per shot, at most 24 shots per project')
    result = []
    for row, shot in zip(rows, expected):
        if not isinstance(row,dict) or row.get('shot_id') != shot['id']:
            raise Invalid('Selected clip order must match every saved shot identity')
        selected = deepcopy(row);selected.pop('shot_id')
        source = selected.get('source',{})
        choices = {(item['id'],item['sha256'])for item in shot['assets']if item['kind']=='MEDIA'}
        if source.get('kind') != 'MANAGED' or (source.get('id'),source.get('sha256')) not in choices:
            raise Invalid('Select original media explicitly from this shot')
        result.append(selected)
    return result


def prepare(store, app_id, body):
    """Return the exact editable definition; saving uses existing Projects.save."""
    from .video_edit_contract import definition
    from .video_edit_projects import saved_data
    exact(body, {'manifest_version','shots','taste','title','purpose','output','clips'})
    manifest = count(body['manifest_version'],1,2147483647)
    ref = provenance(dict(shots=body['shots'],taste=body['taste']))
    with connection(store.path) as db:
        db.execute('BEGIN');app, shots, _ = evidence(db, store, app_id, ref, manifest)
        value = definition(dict(title=body['title'],purpose=body['purpose'],locale=app['data']['locale'],
                                output=body['output'],clips=ordered_clips(body['clips'],shots),packaging=ref))
        bound = saved_data(db,store,app_id,manifest,value)
        return dict(schema='wmm.packaging-editor-handoff.v1',app_id=app_id,manifest_version=manifest,
                    definition=value,source_binding=bound['packaging'],definition_sha256=digest(value),
                    status='EDITABLE_PROJECT_INPUT',project_save='NOT_RUN',render='NOT_RUN',
                    publication='NOT_RUN',execution_authority=False)
