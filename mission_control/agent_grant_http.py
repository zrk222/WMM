"""Bearer gateway and separately authenticated owner controls; no human-approval tools."""
from .common import Invalid
from .agent_grants import Grants
from .operator_client import strict_json,MAX_BYTES
from .operation_runtime import execute

CALL_PATH='/api/agent-operations/call'


def gateway_token(handler,path=CALL_PATH):
    """Require unambiguous exact loopback headers and one bearer credential."""
    expected='127.0.0.1:'+str(handler.server.server_port)
    required={'Host':expected,'Origin':'http://'+expected}
    for name,value in required.items():
        if handler.headers.get_all(name)!=[value]:raise PermissionError('Use the exact local agent operation origin')
    auth=handler.headers.get_all('Authorization') or []
    if len(auth)!=1 or not auth[0].startswith('Bearer '):raise PermissionError('A scoped agent bearer grant is required')
    if handler.path!=path:raise Invalid('Use the exact agent operation address')
    framing(handler)
    return auth[0][7:]


def framing(handler):
    """Reject alternate payload types and ambiguous HTTP body framing."""
    if handler.headers.get('Content-Type','').split(';')[0].strip()!='application/json':
        raise Invalid('Use JSON for agent operations')
    if len(handler.headers.get_all('Content-Length') or [])!=1 or handler.headers.get('Transfer-Encoding'):
        raise Invalid('Use one bounded content length')


def call(handler):
    """Dispatch a scoped admitted operation without a browser/CSRF session."""
    token=gateway_token(handler)
    envelope=strict_json(handler.body(MAX_BYTES))
    service=handler.server.service
    Grants(service.store).admit(token,envelope)
    return handler.send(200,execute(service,envelope))


def owner(store,app_id,action,user,body):
    """Only the HTTP adapter's freshly authenticated owner can manage credentials."""
    grants=Grants(store)
    if action==['issue']:return grants.issue(app_id,user,body)
    if action==['revoke']:return grants.revoke(app_id,user,body)
    if action==['list'] and body=={}:return grants.list(app_id,user)
    raise Invalid('Unknown owner grant-management action')
