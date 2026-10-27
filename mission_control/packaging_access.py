"""Shared packaging preparation controls and observation-only reconciliation."""
from .common import Invalid, digest, identifier
from .db import connection
from .operation_catalog import exact_keys
from .pmf_contract import count, one
from .funnel_store import app_context
from .packaging_store import Packaging, decode, readback
from . import packaging_contract as contract

ACTIONS={'save','read','history','reconcile','checklist','taste-review','taste-read','taste-reconcile'}
SAVE_FIELDS={'id','version','kind','manifest_version','data'}


def history(store, app_id, body):
    """Page compact revision identities; read one document to assess evidence."""
    exact_keys(body,set(),{'offset'})
    offset=count(body.get('offset',0),0,2000)
    with connection(store.path) as db:
        db.execute('BEGIN');app_context(db,app_id)
        total=db.execute('SELECT count(*) FROM packaging_documents WHERE app_id=?',(app_id,)).fetchone()[0]
        rows=db.execute('SELECT id,kind,version,hash,created FROM packaging_documents WHERE app_id=? ORDER BY created,id,version LIMIT 100 OFFSET ?',
                        (app_id,offset)).fetchall()
        items=[dict(row) for row in rows]
    following=offset+len(items)
    return dict(items=items,total=total,offset=offset,limit=100,next_offset=following if following<total else None,
                source_status='NOT_CHECKED',execution_authority=False)


def reconcile(store, app_id, body):
    """Observe one expected revision without resubmission or caller attribution."""
    exact_keys(body,SAVE_FIELDS)
    identity=identifier(body['id']);revision=count(body['version'],0,99)+1
    kind=one(body['kind'],{'VARIANT','SHOTS'},'Packaging kind')
    manifest=count(body['manifest_version'],1,2147483647)
    definition=contract.variant(body['data']) if kind=='VARIANT' else contract.shotlist(body['data'])
    with connection(store.path) as db:
        db.execute('BEGIN');app_context(db,app_id)
        row=db.execute('SELECT * FROM packaging_documents WHERE app_id=? AND id=? AND version=?',
                       (app_id,identity,revision)).fetchone()
        status='NO_REVISION_OBSERVED';document=None
        if row is not None:
            item=decode(row)
            matches=item['kind']==kind and item['data']['manifest_version']==manifest and item['data']['definition']==definition
            status='MATCHING_REVISION_OBSERVED' if matches else 'DIFFERENT_REVISION_OBSERVED'
            document=readback(db,store,app_id,row)
    return dict(status=status,expected_revision=revision,document=document,
                request_hash=digest(dict(app_id=app_id,**body)),caller_commit_identity='NOT_PROVEN',
                automatic_retry=False,execution_authority=False)


def dispatch(store, app_id, action, body):
    """Existing owner/grant gateways provide exact authority for domain calls."""
    if action in {'taste-review','taste-read','taste-reconcile'}:
        from .creative_taste_store import dispatch as taste
        return taste(store,app_id,action,body)
    service=Packaging(store)
    if action=='checklist':
        from .packaging_handoff import preview
        return preview(store,app_id,body)
    if action=='save':return service.save(app_id,body)
    if action=='reconcile':return reconcile(store,app_id,body)
    if action=='read':
        exact_keys(body,{'id','kind'},{'version'})
        return service.read(app_id,body['id'],body['kind'],body.get('version'))
    if action=='history':
        return history(store,app_id,body)
    raise Invalid('Unknown packaging operation')
