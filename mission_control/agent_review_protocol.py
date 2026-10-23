"""Finite agent review actions shared by HTTP, CLI and optional MCP."""
import re
from .common import Invalid
from .operation_catalog import exact_keys,path_segment,request_data

PATHS={name:'/api/agent-operations/reviews/'+name for name in ('prepare','status','resume')}
FIELDS={'prepare':('id','envelope'),'status':('app_id','id'),'resume':('app_id','id','revision','packet_hash')}


def validate(action,body):
    """Reject authority fields or replacement input on resume before transport."""
    if action not in FIELDS:raise Invalid('Unknown agent review action')
    exact_keys(body,FIELDS[action]);path_segment(body['id'])
    if action=='prepare':request_data(body['envelope'])
    else:path_segment(body['app_id'])
    if action=='resume':
        if type(body['revision']) is not int or body['revision']<1:raise Invalid('Use a positive exact checkpoint revision')
        if not isinstance(body['packet_hash'],str) or not re.fullmatch('[a-f0-9]{64}',body['packet_hash']):
            raise Invalid('Use the exact checkpoint hash')
    return PATHS[action]


def schema(action):
    """Advertise closed tool fields; full operation envelope checks remain shared."""
    properties={name:dict(type='string') for name in FIELDS[action]}
    if action=='prepare':properties['envelope']=dict(type='object',additionalProperties=True)
    if action=='resume':
        properties['revision']=dict(type='integer',minimum=1)
        properties['packet_hash']=dict(type='string',pattern='^[a-f0-9]{64}$')
    return dict(type='object',properties=properties,required=list(FIELDS[action]),additionalProperties=False)


def tools():
    """Review preparation and resume never include human approval capabilities."""
    return [dict(name='wmm_review_'+action,description='Agent reviewed request '+action+'. Requires a scoped grant. Human approval is separate; no automatic replay after uncertain results.',
        inputSchema=schema(action),annotations=dict(readOnlyHint=action=='status',idempotentHint=action=='status',destructiveHint=action!='status',openWorldHint=False)) for action in FIELDS]
