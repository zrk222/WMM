"""Consume one official callback; token results never enter browser responses."""
from dataclasses import asdict
from .common import Invalid
from .social_contract import exact,provider_id,opaque
from .social_auth import exchange_code
from .social_profiles import verify
from .social_flows import Flows,public


def callback(store,body,port=8765):
    """No persistence of raw state/code and no blind authorization-code retry."""
    exact(body,('provider','state','code','error'));provider=provider_id(body['provider'])
    opaque(body['state'],'OAuth state',128,43)
    if body['error']:
        opaque(body['error'],'provider error code',100)
        if body['code']!='':raise Invalid('Callback contains competing code and denial; start a fresh login')
    else:opaque(body['code'],'authorization code',4096)
    flows=Flows(store,port);row=flows.claim(provider,body['state'])
    if body['error']:
        return flows.finish(row,'DECLINED',dict(next_action='REVIEW_PERMISSIONS_AND_RECONNECT',existing_connection='PRESERVED'))
    return exchange(flows,row,body['code'])


def exchange(flows,row,code):
    """Commit identity and staged grant only after actual provider reads succeed."""
    app_id=row['app_id'];provider=row['provider'];staged=None
    try:
        flows.alive(row);config=flows.setup.get(app_id,provider)
        settings=flows.secrets.load(app_id,provider,config['secret_ref']) if config['secret_ref'] else {}
        proof=flows.secrets.load(app_id,provider,row['secret_ref'])['verifier']
        alive=lambda:flows.alive(row)
        grant=exchange_code(config['data'],settings.get('client_secret',''),code,proof,alive)
        identity=verify(config['data'],settings.get('client_secret',''),grant,alive);alive()
        facts={**grant.facts,'subject_id':identity.subject_id}
        if identity.expires_at is not None:facts['expires_at']=min(facts['expires_at'],identity.expires_at)
        staged=flows.secrets.stage(app_id,provider,grant.credentials)
        data=dict(identity=asdict(identity),facts=facts)
        return flows.finish(row,'AWAITING_DESTINATION',dict(next_action='CONFIRM_DESTINATION',publishing_implemented=False),staged,data)
    except Exception:
        if staged:flows.secrets.retire(app_id,provider,staged)
        flows.stop(app_id,row['id'],'UNCONFIRMED')
        return public(flows.get(app_id,row['id']))
