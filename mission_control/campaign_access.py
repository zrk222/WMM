"""Fresh owner or scoped-agent access to finite external campaign effects."""
import json
from .common import Invalid
from .db import connection
from .operation_authority import REQUEST, PROTECTED, check, store_identity
from .social_contract import reference

OWNER_ACTIONS={'prepare','activate','revoke'}
FIELDS={'history':set(),'prepare':{'scope'},'activate':{'scope_id','approval_hash'},
        'revoke':{'scope_id'},'status':{'scope_id'},'publish':{'scope_id','request'},
        'ad-launch':{'scope_id','request'},'pause':{'scope_id','intent_id'},
        'reconcile':{'scope_id','intent_id'}}


def identity(store,app_id):
    """Body identities and local cookies alone cannot approve external effects."""
    context=REQUEST.get()
    if context is None or PROTECTED.get() is not context or context['store']!=store_identity(store):
        raise PermissionError('Current protected campaign authority is required')
    if json.loads(context['envelope'])['app_id']!=app_id:
        raise PermissionError('Campaign authority belongs to another app')
    with connection(store.path) as db:
        actor=check(db,context)
    return context,actor


def policy_checker(store):
    """Recheck the live gateway and owner relationship at every effect boundary."""
    def verify(app_id,actor,scope,action):
        context,current_actor=identity(store,app_id)
        if actor!=current_actor:raise PermissionError('Campaign actor changed')
        if action in {'PREPARE','ACTIVATE','REVOKE'} and 'principal' not in context:
            raise PermissionError('Only the authenticated owner may approve campaign scope')
        if 'grant_id' in context:
            with connection(store.path) as db:
                grant=db.execute('SELECT owner FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
                if grant is None or scope.get('owner_principal')!=grant['owner']:
                    raise PermissionError('Campaign scope belongs to another owner')
        elif scope.get('owner_principal',current_actor)!=current_actor:
            raise PermissionError('Campaign scope belongs to another owner')
    return verify


def scope_owner(store,context,actor):
    """Resolve only the authenticated owner behind the currently admitted grant."""
    if 'grant_id' not in context:return actor
    with connection(store.path) as db:
        row=db.execute('SELECT owner FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
        if row is None:raise PermissionError('Campaign grant is unavailable')
        return row['owner']


def dispatch(store,app_id,action,body):
    """All clients share the same scope, budget, idempotency and provider checks."""
    if action not in FIELDS or not isinstance(body,dict) or set(body)!=FIELDS[action]:
        raise Invalid('Use the exact campaign operation fields')
    context,actor=identity(store,app_id)
    if action in OWNER_ACTIONS and 'principal' not in context:
        raise PermissionError('Agents cannot create, activate or widen campaign authority')
    from .campaign_execution import CampaignExecutionService
    service=CampaignExecutionService(store,policy_checker(store))
    if action=='history':
        return dict(scopes=service.list_scopes(app_id,scope_owner(store,context,actor)))
    if action=='prepare':return service.prepare_scope(app_id,actor,body['scope'])
    scope_id=reference(body['scope_id'])
    if 'intent_id' in body:reference(body['intent_id'])
    with connection(store.path) as db:
        owned=db.execute('SELECT 1 FROM campaign_scopes WHERE app_id=? AND id=? AND owner=?',
                         (app_id,scope_id,scope_owner(store,context,actor))).fetchone()
        if owned is None:raise PermissionError('Campaign scope is unavailable for this owner')
    scope=service.get_scope(app_id,scope_id)
    policy_checker(store)(app_id,actor,scope,'ACCESS')
    routes={'activate':lambda:service.activate_scope(app_id,actor,scope_id,body['approval_hash']),
            'revoke':lambda:service.revoke_scope(app_id,actor,scope_id),
            'status':lambda:dict(scope=scope,intents=service.list_intents(app_id,scope_id)),
            'publish':lambda:service.run_post(app_id,actor,scope_id,body['request']),
            'ad-launch':lambda:service.run_ad(app_id,actor,scope_id,body['request']),
            'pause':lambda:service.run_pause(app_id,actor,scope_id,body['intent_id']),
            'reconcile':lambda:service.reconcile(app_id,actor,scope_id,body['intent_id'])}
    return routes[action]()
