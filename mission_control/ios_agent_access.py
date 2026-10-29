"""Trusted native owner grant controls and scoped calls; never a model authority API."""
import json
from .common import Invalid
from .ios_bridge import decode_document, decode_request, encode_response


class NativeAgentAccess:
    def __init__(self, service, identities):
        self.service = service
        self.identities = identities

    def manage(self, session, app_id, action, payload):
        from .agent_grants import Grants
        from .operation_authority import bound_owner, protected
        from .operation_catalog import OPERATIONS
        body = decode_document(payload)
        if not isinstance(body, dict) or action not in ('list', 'issue', 'revoke'):
            raise Invalid('Choose a fixed native owner grant action')
        if action == 'list' and body:
            raise Invalid('Grant listing accepts no body fields')
        if action == 'issue' and (set(body) != {'confirm_scope', 'grant'} or body['confirm_scope'] is not True):
            raise Invalid('Explicit owner confirmation of the exact grant scope is required')
        if action == 'revoke' and (set(body) != {'id', 'version', 'confirm_revoke'} or body['confirm_revoke'] is not True):
            raise Invalid('Confirm the exact current grant revocation')
        user = self.identities.fresh(session)
        envelope = dict(app_id=app_id, operation='native.agent-access.' + action, input=body)
        grants = Grants(self.service.store)
        with bound_owner(self.service.store, envelope, self.identities, session, user):
            with protected(self.service.store, envelope):
                if action == 'list':
                    result = dict(grants.list(app_id, user), operations=OPERATIONS,
                                  native_execution_acceptance='INCOMPLETE')
                elif action == 'issue':
                    result = grants.issue(app_id, user, body['grant'])
                else:
                    result = grants.revoke(app_id, user, {key: body[key] for key in ('id', 'version')})
        return encode_response(result)

    def call(self, session, credential, payload):
        from .agent_grants import token_digest
        from .db import connection
        from .ios_operation_adapter import ScopedAgentAdapter
        envelope = decode_request(payload)
        user = self.identities.fresh(session)
        with connection(self.service.store.path) as db:
            grant = db.execute('SELECT owner FROM agent_grants WHERE token_hash=? AND app_id=?',
                               (token_digest(credential), envelope['app_id'])).fetchone()
            if grant is None or grant['owner'] != user['principal']:
                raise PermissionError('Use this native owner\'s app-scoped agent grant')
        def current_host():
            self.identities.local(session, user['principal'], user['session_generation'])
        # Agent admission, quotas, review and standing authority remain shared.
        # The native unlock check is additive and runs again at business commit.
        return ScopedAgentAdapter(self.service, host_check=current_host).call(credential, payload)

    def review(self,session,credential,action,payload):
        from .agent_grants import token_digest
        from .db import connection
        from .ios_operation_adapter import ScopedAgentAdapter
        from .operation_authority import bound_owner,protected
        body=decode_document(payload)
        fields={'prepare':{'id','envelope'},'inspect':{'id','app_id'},
                'resume':{'id','app_id','revision','packet_hash'}}
        if action not in fields or not isinstance(body,dict) or set(body)!=fields[action]:
            raise Invalid('Use an exact native reviewed-agent request')
        if action=='prepare':
            from .operation_catalog import request_data
            request_data(body['envelope']);app_id=body['envelope']['app_id']
        else:app_id=body['app_id']
        user=self.identities.fresh(session)
        with connection(self.service.store.path) as db:
            grant=db.execute('SELECT owner FROM agent_grants WHERE token_hash=? AND app_id=?',
                             (token_digest(credential),app_id)).fetchone()
            if grant is None or grant['owner']!=user['principal']:
                raise PermissionError('Use this native owner\'s app-scoped agent grant')
        def current_host():
            self.identities.local(session,user['principal'],user['session_generation'])
        adapter=ScopedAgentAdapter(self.service,host_check=current_host)
        envelope=dict(app_id=app_id,operation='native.agent-review.'+action,input={})
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                if action=='prepare':result=adapter.prepare_review(credential,body['id'],
                    json.dumps(body['envelope']).encode())
                elif action=='inspect':result=adapter.inspect_review(credential,app_id,body['id'])
                else:result=adapter.resume_review(credential,app_id,body['id'],body['revision'],body['packet_hash'])
        current_host()
        return result
