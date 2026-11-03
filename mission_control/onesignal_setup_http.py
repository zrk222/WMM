"""Finite owner-only setup gateway; host owns route registration and session identity."""
import secrets
from .common import Invalid
from .ios_bridge import decode_document, encode_response
from .operation_authority import bound_owner, protected
from .onesignal_setup import OneSignalSetup

FIELDS={'status':set(),'history':set(),'save-key':{'kind','key','version'},'read':{'selected_id'},
        'bind':{'provider_app_id','expected_name','expected_org','version'},
        'prepare':{'action','details','request_key'},'execute':{'effect_id','source_hash','confirmed'},
        'reconcile':{'effect_id','provider_app_id','expected_name','expected_org','confirmed'},
        'recovery-prepare':{'effect_id','provider_app_id','key_kind','key'},
        'recovery-confirm':{'recovery_id','source_hash','confirmed'},'cleanup':set()}


class OneSignalSetupGateway:
    """Authenticated host calls this exact gateway; no caller-provided actor identity."""
    def __init__(self,store,identities,vault_factory=None,transport=None):
        self.store=store;self.identities=identities
        self.setup=OneSignalSetup(store,vault_factory,transport) if transport else OneSignalSetup(store,vault_factory)

    def call(self,session,app_id,action,payload):
        if action not in FIELDS or not isinstance(payload,bytes) or len(payload)>65536:
            raise Invalid('Choose a bounded OneSignal setup action')
        body=decode_document(payload)
        if not isinstance(body,dict) or set(body)!=FIELDS[action]:raise Invalid('Use exact OneSignal setup fields')
        user=self.identities.fresh(session)
        envelope={'app_id':app_id,'operation':'onesignal.'+action,'input':body}
        method=getattr(self.setup,action.replace('-','_'))
        with bound_owner(self.store,envelope,self.identities,session,user):
            with protected(self.store,envelope):return encode_response(method(app_id,**body))


def post(handler,parts):
    """Require exact loopback framing and fresh owner before accepting private input."""
    from .common import identifier
    from .managed_media_http import body, singleton
    if (len(parts)!=5 or parts[:2]!=['api','apps'] or parts[3]!='onesignal' or parts[4] not in FIELDS
            or handler.command!='POST' or handler.path!='/'+ '/'.join(parts)):
        raise Invalid('Use the exact OneSignal setup POST address')
    identifier(parts[2]);origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]] or handler.headers.get_all('Origin')!=[origin]:
        raise PermissionError('Use the exact local OneSignal setup origin')
    session=handler.session()
    if not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):raise PermissionError('Reload the current OneSignal session')
    raw=body(handler,'application/json',65536)
    gateway=OneSignalSetupGateway(handler.server.service.store,handler.server.identities)
    result=gateway.call(session,parts[2],parts[4],raw)
    return handler.send(200,result)
