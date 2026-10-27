"""Source-bound production checklists reuse evidence; they never grant execution."""
import sqlite3
from .common import Invalid,digest
from .db import connection
from .funnel_store import app_context
from .packaging_contract import reference
from .packaging_store import latest,readback
from .pmf_contract import exact,count
from .managed_media_store import derivative_snapshot


def document(db,store,app_id,ref,kind):
    """An exact latest document identity cannot silently follow later revisions."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    item=readback(db,store,app_id,latest(db,app_id,ref['id'],kind))
    if item['version']!=ref['version'] or item['hash']!=ref['sha256']:
        raise Invalid('Packaging handoff revision or hash changed; inspect the current plan')
    return item


def media_choices(db,store,app_id,assets):
    """Resolve permitted original media without exposing private storage paths."""
    if type(db) is not sqlite3.Connection:raise TypeError('Native SQLite connection required')
    result=[]
    for ref in assets:
        if ref['kind']!='MEDIA':continue
        try:
            view,_=derivative_snapshot(db,store,app_id,ref['id'],ref['sha256'])
            if view['review_version']!=ref['version']:raise Invalid('Media review revision changed')
            result.append(dict(reference=dict(ref),status='CURRENT_REUSABLE_ORIGINAL',
                               metadata=view['metadata'],reuse_attestation='OWNER_SUPPLIED',problem=None))
        except (Invalid,OSError):
            result.append(dict(reference=dict(ref),status='STALE_OR_UNAVAILABLE',metadata=None,
                               reuse_attestation='NOT_CURRENT',problem='Inspect current media bytes and owner reuse review'))
    return result


def shot_row(db,store,app_id,shot,script):
    """Research timing is inspiration evidence, never an original-media trim."""
    media=media_choices(db,store,app_id,shot['assets'])
    gaps=[]
    if not media:gaps.append('TIMED_ORIGINAL_MEDIA_REQUIRED')
    if any(row['status']!='CURRENT_REUSABLE_ORIGINAL' for row in media):gaps.append('CURRENT_MEDIA_AND_RIGHTS_REQUIRED')
    if shot['claim_text'] and not shot['claims']:gaps.append('CLAIM_PROOF_REQUIRED')
    if digest(script)!=shot['segment_sha256']:gaps.append('SCRIPT_SHOT_REVIEW_REQUIRED')
    return dict(id=shot['id'],kind=shot['kind'],description=shot['description'],
                script=dict(script,sha256=digest(script)),claim_text=shot['claim_text'],claims=shot['claims'],
                research=dict(source=shot['source'],start_ms=shot['start_ms'],end_ms=shot['end_ms'],reuse_authority=False),
                still_assets=[ref for ref in shot['assets'] if ref['kind']=='ASSET'],media=media,gaps=gaps,
                decisions_required=['ORIGINAL_SOURCE_FRAME_RANGE','SOURCE_AUDIO_CHOICE','DESTINATION_FRAMING','CURRENT_TASTE_REVIEW'])


def preview(store,app_id,body):
    """Read exact plan and current upstream evidence in one local snapshot."""
    exact(body,{'manifest_version','shots'})
    manifest=count(body['manifest_version'],1,2147483647)
    ref=reference(body['shots'],{'SHOTS'})
    with connection(store.path) as db:
        db.execute('BEGIN');app=app_context(db,app_id,manifest)
        shots=document(db,store,app_id,ref,'SHOTS')
        definition=shots['data']['definition'];variant_ref=definition['variant']
        variant=document(db,store,app_id,variant_ref,'VARIANT')
        scripts={row['id']:row for row in definition['script']}
        rows=[shot_row(db,store,app_id,shot,scripts[shot['segment_id']]) for shot in definition['shots']]
        gaps=dict(shots=shots['missing_evidence'],variant=variant['missing_evidence'])
        current=shots['source_status']=='CURRENT' and variant['source_status']=='CURRENT'
        value=dict(schema='wmm.packaging-handoff-checklist.v1',app_id=app_id,manifest_version=manifest,
                   app_hash=app['hash'],shots=ref,variant=variant_ref,rows=rows,evidence_gaps=gaps,
                   source_status='CURRENT' if current else 'STALE',
                   source_problems=[v['source_reason'] for v in [shots,variant] if v['source_reason']],
                   status='EDITING_DECISIONS_REQUIRED',render='NOT_RUN',publication='NOT_RUN',execution_authority=False)
        return dict(value,checklist_sha256=digest(value))
