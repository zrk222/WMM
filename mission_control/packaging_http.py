"""Exact protected owner HTTP entry points for local packaging preparation."""
import secrets
from .common import Invalid, identifier
from .managed_media_http import singleton
from .operation_authority import bound_owner, protected
from .discovery_http import json_body
from .packaging_access import ACTIONS, dispatch


def route(handler, parts):
    """Reject alternate paths and verbs before any private domain access."""
    if len(parts)!=5 or parts[:2]!=['api','apps'] or parts[3]!='packaging':raise Invalid('Use the exact packaging operation address')
    identifier(parts[2])
    if parts[4] not in ACTIONS:raise Invalid('Unknown packaging operation')
    if handler.command!='POST' or handler.path!='/'+'/'.join(parts):raise Invalid('Use an exact packaging POST without query')
    return parts[4]


def post(handler, parts):
    """Fresh owner identity is checked again in each protected transaction."""
    action=route(handler,parts);origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]]:raise PermissionError('Use the exact local packaging host')
    if handler.headers.get_all('Origin')!=[origin]:raise PermissionError('Use the exact local packaging origin')
    session=handler.session();user=handler.server.identities.fresh(session)
    if not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):raise PermissionError('Reload the current packaging session')
    store=handler.server.service.store
    envelope=dict(app_id=parts[2],operation='packaging.owner',input=dict(method=handler.command,path=handler.path))
    with bound_owner(store,envelope,handler.server.identities,session,user),protected(store,envelope):
        return handler.send(200,dispatch(store,parts[2],action,json_body(handler,'Packaging')))
