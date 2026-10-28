"""Native protected provider setup reusing shared profiles and cleanup semantics."""
from .common import Invalid, canonical
from .ios_bridge import decode_document, encode_response


class NativeVault:
    """The embedding callback is trusted host code, never an agent request field."""
    def __init__(self, callback, prefix):
        if not callable(callback):raise Invalid('Native protected storage is unavailable')
        self.callback = callback
        self.prefix = prefix

    def invoke(self, action, target, value=None):
        from uuid import UUID
        if not isinstance(target,str) or not target.startswith(self.prefix):
            raise Invalid('Native credential target escaped its app namespace')
        suffix=target[len(self.prefix):]
        try:
            if str(UUID(suffix)) != suffix:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise Invalid('Native credential reference is malformed') from None
        result=decode_document(self.callback(canonical(dict(action=action,target=target,value=value)).encode()))
        if not isinstance(result,dict) or set(result)!={'ok','value'} or result['ok'] is not True:
            raise Invalid('Native protected storage did not confirm the requested action')
        return result['value']

    def put(self,target,value):self.invoke('put',target,value)
    def get(self,target):return self.invoke('get',target)
    def delete(self,target):self.invoke('delete',target)


class NativeProviderAccess:
    SUPPORTED = ('openai_api','anthropic_api','compatible_api')

    def __init__(self,service,identities,vault_callback):
        self.service=service;self.identities=identities;self.vault_callback=vault_callback

    def call(self,session,app_id,action,payload):
        from .agent_access import AgentAccess,target
        from .operation_authority import bound_owner,protected
        body=decode_document(payload)
        if not isinstance(body,dict) or action not in ('view','save','disconnect','cleanup'):
            raise Invalid('Use a fixed native provider setup action')
        if action in ('view','cleanup') and body:raise Invalid('This provider action accepts no fields')
        if action=='save':
            if set(body)!={'confirm_storage','profile'} or body['confirm_storage'] is not True:
                raise Invalid('Confirm protected credential storage for the selected profile')
            if not isinstance(body['profile'],dict) or body['profile'].get('provider') not in self.SUPPORTED:
                raise Invalid('Use a supported native HTTPS API adapter; desktop subscription tools are unavailable')
        if action=='disconnect' and (set(body)!={'id','version','confirm_disconnect'} or body['confirm_disconnect'] is not True):
            raise Invalid('Confirm disconnection of the exact saved provider version')
        prefix=target(self.service.store,app_id,'placeholder').rsplit('/',1)[0]+'/'
        access=AgentAccess(self.service.store,vault_factory=lambda:NativeVault(self.vault_callback,prefix))
        user=self.identities.fresh(session)
        # Secret values are transient input only. No body is copied into audit data.
        envelope=dict(app_id=app_id,operation='native.providers.'+action,input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                if action=='save':result=access.save(app_id,body['profile'])
                elif action=='disconnect':result=access.disconnect(app_id,body['id'],dict(version=body['version']))
                elif action=='cleanup':result=access.cleanup(app_id)
                else:result=access.view(app_id)
        if action=='view':
            result['providers']={key:value for key,value in result['providers'].items() if key in self.SUPPORTED}
            result['native_inference']='NOT_RUN'
            result['oauth']='PROVIDER_APPROVED_NATIVE_ADAPTER_REQUIRED'
        return encode_response(result)
