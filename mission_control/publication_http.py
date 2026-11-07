"""Exact loopback owner routes for organic publication review."""
import secrets
from .common import Invalid,identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .operation_authority import bound_owner,protected
from .publication_service import dispatch,list_publications
from .social_contract import reference

def _route_target(handler,parts):
    """Validate the exact loopback resource path and choose a read or write action."""
    if len(parts)<4 or parts[:2]!=['api','apps'] or parts[3]!='publications':raise Invalid('Use an exact publication address')
    app_id=identifier(parts[2]); method=handler.command
    if handler.path!='/'+'/'.join(parts):raise Invalid('Use an exact publication address without query')
    if len(parts)==4 and method=='GET':action='list';identity=None;body={}
    elif len(parts)==5 and method=='GET':action='get';identity=reference(parts[4]);body={}
    elif len(parts)==5 and method=='POST' and parts[4] in ('draft','prepare','preflight','instagram-account','execute'):
        action=parts[4];identity=None;body=None
    elif len(parts)==6 and method=='POST' and parts[5] in ('activate','revoke','reconcile'):
        identity=reference(parts[4]);action=parts[5];body=None
    else:raise Invalid('Use an exact publication operation address')
    return app_id,method,action,identity,body

def _envelope(app_id,action,identity,body):
    """Bind route identity and exact payload to the canonical protected operation."""
    if action=='list':admitted={}
    elif action=='get':admitted={'id':identity}
    elif action=='activate':admitted={'id':identity,'body':body}
    elif action=='revoke' and isinstance(body,dict):admitted={'id':identity,'version':body.get('version')}
    else:admitted=body
    return {'app_id':app_id,'operation':'publication.'+action,'input':admitted}

def _authorize_local(handler,method):
    """Require the exact local host, same-origin writes, owner session and POST CSRF token."""
    origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]]:raise PermissionError('Use the exact local publication host')
    if method=='POST' and handler.headers.get_all('Origin')!=[origin]:raise PermissionError('Use the exact local publication origin')
    if handler.headers.get_all('Authorization') is not None:raise PermissionError('Publication controls require an owner session')
    session=handler.session();user=handler.server.identities.fresh(session)
    if method=='POST' and not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):raise PermissionError('Reload the current publication session')
    return session,user

def _resource(store,app_id,action,identity,body):
    """Dispatch only the fixed list, read-only report, or declared publication write."""
    if action=='list':return list_publications(store,app_id)
    if action=='get':
        from .publication_reports import report
        return report(store,app_id,identity)
    return dispatch(store,app_id,action,body,identity)

def route(handler,parts):
    """Serve an exact local publication route under existing owner guards."""
    app_id,method,action,identity,body=_route_target(handler,parts)
    store=handler.server.service.store
    session,user=_authorize_local(handler,method)
    if body is None:body=json_body(handler,'Publication')
    envelope=_envelope(app_id,action,identity,body)
    with bound_owner(store,envelope,handler.server.identities,session,user),protected(store,envelope):
        result=_resource(store,app_id,action,identity,body)
    return handler.send(200,result)
