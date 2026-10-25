"""Exact owner-bound local funnel routes share the authoritative domain service."""
from contextlib import contextmanager
import secrets
import re
from .common import Invalid,identifier
from .managed_media_http import singleton
from .http_body import read_exact
from .operator_client import strict_json
from .operation_authority import bound_owner,protected
from .funnel_store import Funnels


def offset(handler,parts):
    """Only selected GET collections accept one canonical bounded decimal offset."""
    base='/'+'/'.join(parts)
    if handler.path==base:return 0
    allowed=getattr(handler,'command','GET')=='GET' and (len(parts)==4 or (len(parts)==6 and parts[5]=='observations'))
    if not allowed:raise Invalid('Use the exact funnel address without a query')
    match=re.fullmatch(re.escape(base)+r'\?offset=(0|[1-9][0-9]{0,4})',handler.path)
    if not match or int(match[1])>10000:raise Invalid('Use one canonical funnel offset from 0 through 10000')
    return int(match[1])


def route(handler,parts):
    """Close raw path variants before looking up private app state."""
    if len(parts) not in (4,5,6) or parts[:2]!=['api','apps'] or parts[3]!='funnels':
        raise Invalid('Use the exact app funnel address')
    identifier(parts[2])
    if len(parts)>4:identifier(parts[4])
    if len(parts)==6 and parts[5] not in ('observations','report'):raise Invalid('Use the exact funnel operation')
    return offset(handler,parts)


@contextmanager
def owner(handler,parts):
    """Bind fresh owner identity to every transaction without accepting body authority."""
    start=route(handler,parts);origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]]:raise PermissionError('Use the exact local funnel host')
    supplied=handler.headers.get_all('Origin')
    if supplied is not None or handler.command=='POST':
        if supplied!=[origin]:raise PermissionError('Use the exact local funnel origin')
    session=handler.session();user=handler.server.identities.fresh(session)
    if handler.command=='POST' and not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):
        raise PermissionError('Reload the current funnel session')
    store=handler.server.service.store
    envelope=dict(app_id=parts[2],operation='funnel.owner',input=dict(method=handler.command,path=handler.path))
    with bound_owner(store,envelope,handler.server.identities,session,user),protected(store,envelope):
        yield Funnels(store),start


def json_body(handler):
    """One bounded JSON request and absolute deadline; no alternate transfer framing."""
    if singleton(handler,'Content-Type')!='application/json':raise Invalid('Use application/json for funnel input')
    if handler.headers.get_all('Transfer-Encoding') is not None:raise Invalid('Funnel input cannot use transfer encoding')
    length=singleton(handler,'Content-Length')
    if not length.isascii() or not length.isdecimal() or not 1<=int(length)<=1048576:
        raise Invalid('Funnel input exceeds its bounded byte limit')
    return strict_json(read_exact(handler,1048576,'Funnel'))


def get(handler,parts):
    """Read only exact current authorized app-owned definitions or selected evidence."""
    with owner(handler,parts) as (flow,start):
        if len(parts)==4:return handler.send(200,flow.list(parts[2],start))
        if len(parts)==5:return handler.send(200,flow.read(parts[2],parts[4]))
        if parts[5]=='observations':return handler.send(200,flow.observations(parts[2],parts[4],start))
        return handler.send(200,flow.report(parts[2],parts[4]))


def post(handler,parts):
    """Only immutable plan save and observation import are local write operations."""
    with owner(handler,parts) as (flow,start):
        if len(parts)==5:raise Invalid('Save a new immutable funnel at the collection address')
        if len(parts)==6 and parts[5]!='observations':raise Invalid('This funnel address is read-only')
        value=json_body(handler)
        if len(parts)==4:return handler.send(201,flow.save(parts[2],value))
        if not isinstance(value,dict) or 'funnel_id' in value:raise Invalid('The exact path selects the funnel')
        return handler.send(200,flow.ingest(parts[2],dict(value,funnel_id=parts[4])))
