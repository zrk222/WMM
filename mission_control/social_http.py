"""Finite app-scoped social commands; connection is not publication authority."""
from .common import Invalid
from .social_contract import exact
from .social_setup import Setup
from .social_flows import Flows,public
from .social_connections import Connections
from .social_renewal import Renewal
from .social_secrets import Secrets


def view(store,app_id):
    """Public status excludes secret references, renewal leases and OAuth state hashes."""
    return dict(setup=Setup(store).view(app_id),**Connections(store).view(app_id))


def post(store,app_id,parts,body,port):
    """Unknown commands and extra fields cannot become arbitrary provider actions."""
    store.app(app_id);setup=Setup(store,port);flows=Flows(store,port);accounts=Connections(store,port)
    if len(parts)==1:return single(store,app_id,parts[0],body,setup,flows,accounts)
    if len(parts)==2 and parts[1] in ('test','renew','disconnect'):
        exact(body,('version',))
        if parts[1]=='renew':return Renewal(store).run(app_id,parts[0],body['version'])
        if parts[1]=='test':return accounts.read_test(app_id,parts[0],body['version'])
        return accounts.disconnect(app_id,parts[0],body['version'])
    raise Invalid('Choose a supported social connection action; posting and ads are not implemented')


def single(store,app_id,action,body,setup,flows,accounts):
    """Closed method table keeps input contracts next to the permitted operations."""
    handlers={
        'save':(None,lambda:setup.save(app_id,body)),
        'approve-discovered':(None,lambda:setup.approve_discovered(app_id,body)),
        'packet':(('provider','native_enabled'),lambda:setup.packet(app_id,body['provider'],body['native_enabled'])),
        'discover':(('provider',),lambda:setup.discover(app_id,body['provider'])),
        'start':(('provider','version'),lambda:flows.start(app_id,body['provider'],body['version'])),
        'confirm':(None,lambda:accounts.confirm(app_id,body)),
        'cancel':(('flow_id',),lambda:flows.stop(app_id,body['flow_id'])),
        'cleanup':((),lambda:cleanup(store,app_id,flows))}
    if action not in handlers:raise Invalid('Choose a supported social action; posting and ads are not implemented')
    fields,execute=handlers[action]
    if fields is not None:exact(body,fields)
    return execute()


def cleanup(store,app_id,flows):
    """Expire abandoned consent stages before deleting only inactive protected keys."""
    flows.expire(app_id);return Secrets(store).cleanup(app_id)
