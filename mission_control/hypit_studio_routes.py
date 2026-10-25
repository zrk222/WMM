"""Fresh-owner human transport to the same long-lived Studio operation manager."""
from .common import Invalid
from .operation_catalog import request_data
from .operation_authority import bound_owner
from .review_access import member
from .db import connection


def operation(parts,body):
    """Resolve only finite collection/session routes into a closed envelope."""
    if len(parts)==5:
        app,action=parts[2],parts[4];resource=None
        if action not in ('plan','start','sessions'):raise Invalid('Use the exact Studio action')
    elif len(parts)==6:
        app,resource,action=parts[2],parts[4],parts[5]
        if action not in ('read','edit','inspect','close'):raise Invalid('Use the exact selected-session action')
    else:raise Invalid('Use the exact Studio operation address')
    value=dict(app_id=app,operation='studio.'+action,input=body)
    if resource is not None:value['resource_id']=resource
    request_data(value)
    return value


def human(handler,parts,body):
    """Require exact route and origin plus fresh owner before manager admission."""
    expected='127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[expected] or handler.headers.get_all('Origin')!=['http://'+expected]:
        raise PermissionError('Use the exact local Studio origin')
    value=operation(parts,body)
    if handler.path!=request_data(value)['path']:raise Invalid('Use the exact Studio operation address')
    service=handler.server.service;session=handler.session()
    user=handler.server.identities.fresh(session)
    with connection(service.store.path) as db:member(db,value['app_id'],user['principal'],'OWNER')
    with bound_owner(service.store,value,handler.server.identities,session,user):
        return service.studio.dispatch(value)


def framing(handler):
    """Reject ambiguous content type, transfer coding or content-length framing."""
    if handler.headers.get_all('Content-Type')!=['application/json']:
        raise Invalid('Studio operations need exactly one application/json content type')
    if handler.headers.get_all('Transfer-Encoding') is not None or len(handler.headers.get_all('Content-Length') or [])!=1:
        raise Invalid('Studio operations need one bounded content length')


def read_body(handler):
    """Read at most one MiB within five seconds and reject truncation."""
    framing(handler)
    previous=handler.connection.gettimeout()
    try:
        handler.connection.settimeout(5)
        try:raw=handler.body(1048576)
        except (TimeoutError,OSError):raise Invalid('Studio request body did not arrive within 5 seconds') from None
    finally:handler.connection.settimeout(previous)
    if len(raw)!=int(handler.headers['Content-Length']):raise Invalid('Studio request body is truncated')
    return raw
