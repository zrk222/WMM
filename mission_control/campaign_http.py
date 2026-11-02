"""Strict owner campaign routes; ordinary agent calls use the fixed catalog."""
import secrets
from .common import Invalid, identifier
from .managed_media_http import singleton
from .discovery_http import json_body
from .operation_authority import bound_owner, protected
from .campaign_access import dispatch, FIELDS


def post(handler,parts):
    if len(parts)!=5 or parts[:2]!=['api','apps'] or parts[3]!='campaigns' or parts[4] not in FIELDS:
        raise Invalid('Use an exact campaign operation address')
    identifier(parts[2])
    if handler.command!='POST' or handler.path!='/'+'/'.join(parts):
        raise Invalid('Use an exact campaign POST without query')
    origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]] or handler.headers.get_all('Origin')!=[origin]:
        raise PermissionError('Use the exact local campaign origin')
    session=handler.session()
    identities=handler.server.identities
    user=identities.local(session,identities.public(session).get('principal')) if parts[4] in ('history','status') else identities.fresh(session)
    if not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):
        raise PermissionError('Reload the current campaign session')
    store=handler.server.service.store
    envelope=dict(app_id=parts[2],operation='campaign.owner.'+parts[4],input={})
    with bound_owner(store,envelope,handler.server.identities,session,user),protected(store,envelope):
        return handler.send(200,dispatch(store,parts[2],parts[4],json_body(handler,'Campaign')))
