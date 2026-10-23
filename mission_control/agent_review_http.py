"""Separate bearer agent transport and fresh-identity human review endpoints."""
from .common import Invalid
from .db import connection
from .operation_catalog import exact_keys,path_segment
from .agent_grant_http import gateway_token
from .operator_client import strict_json,MAX_BYTES
from .agent_review_protocol import PATHS,validate
from .agent_review_dispatch import ReviewedDispatch,saved_request,request_view
from .agent_checkpoints import Checkpoints
from .review_access import member

PAGE_SIZE=100


def agent(handler):
    """Route only closed agent actions without browser session creation."""
    action=next((name for name,path in PATHS.items() if handler.path==path),None)
    if action is None:raise Invalid('Unknown exact agent review address')
    token=gateway_token(handler,PATHS[action])
    body=strict_json(handler.body(MAX_BYTES));validate(action,body)
    dispatch=ReviewedDispatch(handler.server.service)
    if action=='prepare':value=dispatch.prepare(token,body['id'],body['envelope'])
    elif action=='status':value=dispatch.inspect(token,body['app_id'],body['id'])
    else:value=dispatch.resume(token,body['app_id'],body['id'],body['revision'],body['packet_hash'])
    return handler.send(200,value)


def queue(store,app_id,user,body):
    """Page bounded metadata; exact private input requires a separate detail request."""
    exact_keys(body,(),('offset',));offset=body.get('offset',0)
    if type(offset) is not int or offset<0:raise Invalid('Use a nonnegative queue offset')
    with connection(store.path) as db:
        member(db,app_id,user['principal'])
        total=db.execute('SELECT count(*) FROM agent_review_requests WHERE app_id=?',(app_id,)).fetchone()[0]
        if offset>total:raise Invalid('Queue offset exceeds the current request count')
        ids=[row['id'] for row in db.execute('SELECT id FROM agent_review_requests WHERE app_id=? ORDER BY id LIMIT ? OFFSET ?',(app_id,PAGE_SIZE,offset))]
        items=[queue_item(request_view(db,saved_request(db,app_id,identity))) for identity in ids]
    return dict(items=items,total=total,offset=offset,next_offset=offset+PAGE_SIZE if offset+PAGE_SIZE<total else None)


def queue_item(view):
    """Keep large business inputs and credentials out of queue metadata."""
    checkpoint=view['checkpoint']
    return dict(id=view['id'],operation=view['envelope']['operation'],input_hash=view['input_hash'],
        checkpoint_hash=checkpoint['hash'],revision=checkpoint['revision'],state=checkpoint['state'],
        agent_id=checkpoint['packet']['agent_id'],maker=checkpoint['packet']['maker'],
        expires=checkpoint['packet']['expires'],reconciliation_required=view['reconciliation_required'])


def human(store,app_id,action,user,body):
    """Use only the human adapter's verified principal, never supplied actor names."""
    if action==['list']:return queue(store,app_id,user,body)
    fields={'inspect':('id',),'approve':('id','revision','packet_hash'),'cancel':('id','revision'),
        'reconcile':('id','revision','outcome','evidence_hash')}
    if len(action)!=1 or action[0] not in fields:raise Invalid('Unknown human review action')
    command=action[0];exact_keys(body,fields[command]);path_segment(body['id'])
    with connection(store.path) as db:
        member(db,app_id,user['principal'])
        view=request_view(db,saved_request(db,app_id,body['id']))
    if command=='inspect':return view
    checkpoints=Checkpoints(store);principal=user['principal']
    if command=='approve':return checkpoints.approve(app_id,body['id'],principal,body['revision'],body['packet_hash'])
    if command=='cancel':return checkpoints.cancel(app_id,body['id'],principal,body['revision'])
    return checkpoints.reconcile(app_id,body['id'],principal,body['revision'],body['outcome'],body['evidence_hash'])
