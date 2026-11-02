"""Strict owner campaign routes; ordinary agent calls use the fixed catalog."""
import secrets
from .common import Invalid, identifier
from .managed_media_http import singleton
from .discovery_http import json_body
from .operation_authority import bound_owner, protected
from .campaign_access import dispatch, FIELDS

SCHEDULE_FIELDS={'schedule-history':set(),'schedule-prepare':{'scope_id','items'},
                 'schedule-activate':{'batch_id','summary_hash'},'schedule-status':{'batch_id'},
                 'schedule-off':{'batch_id','version'}}

def schedule_dispatch(store,app_id,action,body):
    """Exact owner controls; scheduled worker capability is never issued to agents."""
    if not isinstance(body,dict) or set(body)!=SCHEDULE_FIELDS[action]:
        raise Invalid('Use the exact scheduled campaign fields')
    from .campaign_schedule import CampaignSchedules
    from .social_contract import reference
    service=CampaignSchedules(store)
    if action=='schedule-history':return service.history(app_id)
    if action=='schedule-prepare':return service.prepare(app_id,body)
    batch_id=reference(body['batch_id'])
    if action=='schedule-status':return service.status(app_id,batch_id)
    if action=='schedule-activate':return service.activate(app_id,batch_id,body['summary_hash'])
    return service.revoke(app_id,batch_id,body['version'])


def post(handler,parts):
    if len(parts)!=5 or parts[:2]!=['api','apps'] or parts[3]!='campaigns' or parts[4] not in {*FIELDS,*SCHEDULE_FIELDS}:
        raise Invalid('Use an exact campaign operation address')
    identifier(parts[2])
    if handler.command!='POST' or handler.path!='/'+'/'.join(parts):
        raise Invalid('Use an exact campaign POST without query')
    origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]] or handler.headers.get_all('Origin')!=[origin]:
        raise PermissionError('Use the exact local campaign origin')
    session=handler.session()
    identities=handler.server.identities
    user=identities.local(session,identities.public(session).get('principal')) if parts[4] in ('history','status','schedule-history','schedule-status') else identities.fresh(session)
    if not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):
        raise PermissionError('Reload the current campaign session')
    store=handler.server.service.store
    envelope=dict(app_id=parts[2],operation='campaign.owner.'+parts[4],input={})
    with bound_owner(store,envelope,handler.server.identities,session,user),protected(store,envelope):
        body=json_body(handler,'Campaign')
        result=schedule_dispatch(store,parts[2],parts[4],body) if parts[4] in SCHEDULE_FIELDS else dispatch(store,parts[2],parts[4],body)
        return handler.send(200,result)
