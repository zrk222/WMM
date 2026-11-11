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
    result=execute_admitted(service,envelope,admission)
    if envelope['operation']=='operations.read':
        result=dict(result,agent_authority=Grants(service.store).authority_status(admission['grant_id'],envelope['app_id']))
    return handler.send(200,result)


def owner(store,app_id,action,user,body,*,runtime_origin=None,runtime_executable=None):
    """Only the HTTP adapter's freshly authenticated owner can manage credentials."""
    if action==['setup']:
        if body != {} or runtime_origin is None:
            raise Invalid('Use the exact owner agent setup request')
        from .db import connection
        from .review_access import member
        with connection(store.path) as db:
            member(db,app_id,user['principal'],'OWNER')
        from .agent_setup import report
        return report(runtime_origin,runtime_executable=runtime_executable)
    grants=Grants(store)
    from .agent_handoffs import Handoffs
    handoffs=Handoffs(store)
    if action==['handoff-create']:return handoffs.create(app_id,user,body)
    if action==['handoff-list'] and body=={}:return handoffs.list(app_id,user)
    if action==['handoff-revoke']:return handoffs.revoke(app_id,user,body)
    from .complete_automation import Automation
    automation=Automation(store)
    from .automation_agreement import Agreement
    controls={'agreement-preview':lambda:Agreement(store).preview(app_id,user,body),
              'automation-readiness':lambda:goal_readiness(store,app_id,user,body),
              'automation-preview':lambda:automation.preview(app_id,user,body),
              'automation-activate':lambda:automation.activate(app_id,user,body),
              'automation-off':lambda:automation.off(app_id,user,body)}
    if len(action)==1 and action[0] in controls:return controls[action[0]]()
    if action==['automation-status'] and body=={}:return automation.status(app_id,user)
    if action==['issue']:return grants.issue(app_id,user,body)
    if action==['revoke']:return grants.revoke(app_id,user,body)
    if action==['list'] and body=={}:return grants.list(app_id,user)
    raise Invalid('Unknown owner grant-management action')


def facebook_credential_repair(store, app_id, account):
    """Check only the selected Page's local credential fields; return no secret material."""
    from .credential_vault import Vault
    from .social_connections import Connections
    from .social_contract import opaque
    from .social_secrets import name

    connections = Connections(store)
    try:
        saved = connections.get(app_id, account['id'])
        config = connections.setup.get(app_id, 'facebook')
        if (saved['provider'], saved['version'], config['version']) != (
            'facebook', account['version'], account['config_version']
        ):
            return 'RECONNECT_REQUIRED'
        names = (
            name(store, app_id, 'facebook', saved['secret_ref'], 'access_token'),
            name(store, app_id, 'facebook', config['secret_ref'], 'client_secret'),
        )
    except Invalid:
        return 'RECONNECT_REQUIRED'
    try:
        vault = Vault()
        for address in names:
            record = vault.get(address)
            if not isinstance(record, dict) or set(record) != {'value'}:
                return 'RECONNECT_REQUIRED'
            try:
                opaque(record['value'])
            except Invalid:
                return 'RECONNECT_REQUIRED'
    except Invalid:
        return 'PROTECTED_STORAGE_UNAVAILABLE'
    return None


def goal_readiness(store,app_id,user,body):
    """Keep the saved inventory intact and add a local repair observation for the owner."""
    from .automation_requirements import Readiness
    report=Readiness(store).report(app_id,user,body)
    inventory = report['inventory']
    repairs = {}
    if {'social_publish', 'paid_effects', 'organic_publication'}.intersection(
        inventory['selection']['workflows']
    ):
        for account in inventory['accounts']:
            if account['provider'] == 'facebook' and account['status'] == 'TESTED_FRESH':
                repair = facebook_credential_repair(store, app_id, account)
                if repair:
                    repairs[account['id']] = repair
    ready = inventory['scope_status'] == 'READY_FOR_SCOPE_REVIEW' and not repairs
    return dict(report,status='success' if ready else 'warning',credential_repairs=repairs,
                summary='Selected requirements are ready for scope review.' if ready else 'Selected requirements need repair before scope review.',
                next_actions=['Review the current exact scope with the owner; this inventory grants no authority.'] if ready else
                             ['Repair the listed workflow and connection blockers, then check readiness again.'],
                artifacts=[],authority_issued=False)
