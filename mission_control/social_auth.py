"""Official authorization/code/renewal flows, with no model-selected endpoints."""
import time,secrets,hashlib,hmac
from urllib.parse import urlencode
from .common import Invalid
from .social_contract import provider_id,opaque,challenge
from .social_registry import PROVIDERS,NATIVE_LINKEDIN
from .social_tokens import Grant,parse,same_subject
from .social_transport import request


def fresh_state():
    """Keep raw state only in the authorization handoff; persistence uses its hash."""
    state=secrets.token_urlsafe(32)
    return state,hashlib.sha256(state.encode()).hexdigest(),secrets.token_urlsafe(48)


def authorization(config,state,verifier,rerequest=False):
    """Generate the exact official URL from validated setup and fixed initial scopes."""
    provider=provider_id(config['provider']);entry=PROVIDERS[provider]
    opaque(state,'OAuth state',128,43)
    if config['scopes']!=entry['scopes']:raise Invalid('Social permission configuration changed; prepare setup again')
    fields={'client_key' if provider=='tiktok' else 'client_id':config['client_id'],
            'redirect_uri':config['redirect_uri'],'response_type':'code',
            'scope':entry['separator'].join(entry['scopes']),'state':state}
    native=provider=='linkedin' and config['native_enabled']
    if provider=='tiktok' or native:fields.update(code_challenge=challenge(provider,verifier),code_challenge_method='S256')
    if provider=='facebook' and rerequest:fields['auth_type']='rerequest'
    return (NATIVE_LINKEDIN if native else entry['authorize'])+'?'+urlencode(fields)


def code_fields(config,secret,code,verifier):
    """A native proof verifier never becomes a client secret or an arbitrary parameter."""
    provider=config['provider'];native=provider=='linkedin' and config['native_enabled']
    fields={'client_key' if provider=='tiktok' else 'client_id':config['client_id'],
            'redirect_uri':config['redirect_uri'],'code':opaque(code,'authorization code',4096)}
    if not native:fields['client_secret']=opaque(secret,'client secret')
    if provider=='tiktok' or native:
        challenge(provider,verifier);fields['code_verifier']=verifier
    return fields,'code_native' if native else 'code'


def exchange_code(config,secret,code,verifier,alive=lambda:None):
    """No automatic replay: an authorization code may already have been consumed."""
    provider=config['provider'];fields,operation=code_fields(config,secret,code,verifier)
    deadline=time.monotonic()+60
    raw=request(provider,operation,fields,alive=alive,deadline=deadline)
    if provider=='instagram':
        short=parse(provider,raw,time.time(),short=True)
        extended=request(provider,'long',{'client_secret':secret,'access_token':short.credentials['access_token']},alive=alive,deadline=deadline)
        return parse(provider,extended,time.time(),prior=short.facts)
    if provider=='facebook':
        short=parse(provider,raw,time.time())
        raw=request(provider,'long',dict(client_id=config['client_id'],client_secret=secret,
                    fb_exchange_token=short.credentials['access_token']),alive=alive,deadline=deadline)
    return parse(provider,raw,time.time())


def refresh(config,secret,credentials,facts,alive=lambda:None):
    """Only documented renewal grants run; absent entitlement offers reauthorization."""
    provider=config['provider'];clock=time.time()
    if facts['expires_at'] is None or facts['expires_at']<=clock:raise Invalid('Social access expired; reconnect through the official login')
    if provider=='instagram':
        if clock-facts['issued_at']<86400:raise Invalid('Instagram token renewal is not due until the long-lived token is at least24hours old')
        fields={'access_token':credentials['access_token']}
    else:fields=refresh_fields(config,secret,credentials,facts,clock)
    value=request(provider,'refresh',fields,alive=alive)
    grant=parse(provider,value,clock,prior=facts)
    if provider=='linkedin' and 'refresh_token' not in grant.credentials:
        grant=Grant({**grant.credentials,'refresh_token':credentials['refresh_token']},
                    {**grant.facts,'renewal':'REFRESH_TOKEN'})
    same_subject(grant,facts['subject_id']);return grant


def refresh_fields(config,secret,credentials,facts,clock):
    """Token presence and expiry, not a marketing label, determine refresh availability."""
    provider=config['provider']
    if provider not in ('tiktok','linkedin') or config['native_enabled']:
        raise Invalid('This connection needs official browser reauthorization; saved access is preserved')
    refresh_token=credentials.get('refresh_token')
    if not refresh_token:raise Invalid('Programmatic renewal is unavailable; reconnect through the official login')
    if facts.get('refresh_expires_at') is not None and facts['refresh_expires_at']<=clock:raise Invalid('Social refresh permission expired; reconnect this account')
    return {'client_key' if provider=='tiktok' else 'client_id':config['client_id'],
            'client_secret':secret,'refresh_token':refresh_token}


def app_secret_proof(access,secret):
    """Match Meta's server-side HMAC-SHA256 proof without exposing the app secret."""
    return hmac.new(opaque(secret).encode(),opaque(access).encode(),hashlib.sha256).hexdigest()
