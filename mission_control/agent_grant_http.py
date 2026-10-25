"""Bearer gateway and separately authenticated owner controls; no human-approval tools."""
import re
from .common import Invalid
from .agent_grants import Grants
from .operator_client import strict_json,MAX_BYTES
from .http_body import read_exact

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
    if handler.headers.get_all('Content-Type')!=['application/json']:
        raise Invalid('Use exactly one application/json content type')
    lengths=handler.headers.get_all('Content-Length') or []
    if handler.headers.get_all('Transfer-Encoding') is not None or len(lengths)!=1:
        raise Invalid('Use one bounded content length')
    if not re.fullmatch(r'[0-9]{1,8}',lengths[0]) or not 1<=int(lengths[0])<=MAX_BYTES:
        raise Invalid('Use one bounded decimal content length')


def read_body(handler):
    """Reject stalled or truncated bearer payloads before any grant admission."""
    framing(handler)
    return read_exact(handler,MAX_BYTES,'Agent')


def call(handler):
    """Dispatch a scoped admitted operation without a browser/CSRF session."""
    token=gateway_token(handler)
    envelope=strict_json(read_body(handler))
    service=handler.server.service
    admission=Grants(service.store).admit(token,envelope)
    from .automation_execution import execute_admitted
    return handler.send(200,execute_admitted(service,envelope,admission))


def owner(store,app_id,action,user,body):
    """Only the HTTP adapter's freshly authenticated owner can manage credentials."""
    grants=Grants(store)
    from .complete_automation import Automation
    automation=Automation(store)
    if action==['automation-preview']:return automation.preview(app_id,user,body)
    if action==['automation-activate']:return automation.activate(app_id,user,body)
    if action==['automation-off']:return automation.off(app_id,user,body)
    if action==['automation-status'] and body=={}:return automation.status(app_id,user)
    if action==['issue']:return grants.issue(app_id,user,body)
    if action==['revoke']:return grants.revoke(app_id,user,body)
    if action==['list'] and body=={}:return grants.list(app_id,user)
    raise Invalid('Unknown owner grant-management action')
