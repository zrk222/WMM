"""Closed social configuration and response primitives; never reflect provider secrets."""
import base64,hashlib,re,uuid
from urllib.parse import urlsplit
from .common import Invalid,identifier
from .aeo_transport import public_url
from .social_registry import PROVIDERS


def exact(value,keys):
    """Reject extra authority or command fields before using social request data."""
    if not isinstance(value,dict) or set(value)!=set(keys):raise Invalid('Use only the documented social connection fields')


def provider_id(value):
    """Only registered social providers can select hosts, scopes or protected names."""
    if not isinstance(value,str) or value not in PROVIDERS:raise Invalid('Choose Facebook, Instagram, TikTok or LinkedIn')
    return value


def reference(value):
    """Use canonical opaque identities, never free-form credential-store addresses."""
    try:
        if str(uuid.UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise Invalid('Use the current social connection identity') from None
    return value


def opaque(value,label='provider credential',maximum=2048,minimum=1):
    """Credential text is bounded printable ASCII; it never becomes a diagnostic."""
    if not isinstance(value,str) or not minimum<=len(value)<=maximum or re.search(r'[^!-~]',value):
        raise Invalid('Invalid '+label+'; check the selected provider setup')
    return value


def display(value,label='account name',maximum=200):
    """Retain international names but reject control and bidi-spoofing characters."""
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:
        raise Invalid('Provider returned an invalid '+label)
    if re.search(r'[\x00-\x1f\x7f-\x9f\u202a-\u202e\u2066-\u2069]',value):raise Invalid('Provider returned an unsafe '+label)
    return value.strip()


def account_id(value):
    """Accept exact opaque subjects without floating point or boolean coercion."""
    if type(value) is int:value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.:@-]{1,160}',value):
        raise Invalid('Provider account identity could not be verified')
    return value


def callback(provider,native,port):
    """Local callbacks are derived from the actual private server, never client URLs."""
    if type(port) is not int or not 1<=port<=65535:raise Invalid('Private callback port is unavailable')
    if provider=='tiktok' or (provider=='linkedin' and native):return f'http://127.0.0.1:{port}/social/callback/{provider}'
    return None


def redirect(provider,native,value,port):
    """Require exact loopback or registered HTTPS relay paths, without URL credentials."""
    local=callback(provider,native,port)
    if local:
        if value not in ('',local):raise Invalid('Use the displayed private callback exactly')
        return local
    target=public_url(value)
    if urlsplit(target).path!='/cb/'+provider:raise Invalid('Use the reviewed HTTPS relay callback ending /cb/'+provider)
    return target


def relay_base(value):
    """An optional app-owned deployed relay is a public origin, never a return URL."""
    if value=='':return ''
    target=public_url(value)
    if urlsplit(target).path not in ('','/'):raise Invalid('Use only the deployed relay HTTPS origin, without a callback path')
    return target.rstrip('/')


def configuration(body,port=8765):
    """Validate one app-owned developer setup with read-only initial permissions."""
    exact(body,('provider','client_id','client_secret','redirect_uri','native_enabled','version'))
    provider=provider_id(body['provider']);native=body['native_enabled']
    if type(native) is not bool or (native and provider!='linkedin'):raise Invalid('Native enablement applies only to an approved LinkedIn app')
    client=opaque(body['client_id'],'client ID',128,3)
    if not re.fullmatch(r'[A-Za-z0-9_-]+',client):raise Invalid('Use the provider client ID without URL or command characters')
    if provider in ('facebook','instagram') and not client.isdigit():raise Invalid('Use the numeric provider app ID')
    configuration_secret(provider,native,body['client_secret'])
    if type(body['version']) is not int or body['version']<0:raise Invalid('Use the current setup version, or zero for new setup')
    return dict(provider=provider,client_id=client,native_enabled=native,
                redirect_uri=redirect(provider,native,body['redirect_uri'],port),scopes=list(PROVIDERS[provider]['scopes']))


def configuration_secret(provider,native,secret):
    """Native LinkedIn must not carry a client secret; confidential flows require one."""
    if provider=='linkedin' and native:
        if secret!='':raise Invalid('LinkedIn native PKCE does not accept a client secret')
    else:opaque(secret,'client secret',2048,8)


def challenge(provider,verifier):
    """TikTok documents hex SHA256; LinkedIn native documents base64url SHA256."""
    if not isinstance(verifier,str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',verifier):raise Invalid('OAuth proof verifier is invalid')
    raw=hashlib.sha256(verifier.encode('ascii')).digest()
    if provider=='tiktok':return raw.hex()
    if provider=='linkedin':return base64.urlsafe_b64encode(raw).decode().rstrip('=')
    raise Invalid('This provider does not use the native proof-key flow')


def reported_scopes(value,required=()):
    """Return only validated scope names; do not infer grants from requested values."""
    if isinstance(value,str):value=re.split(r'[, ]+',value.strip())
    if not isinstance(value,list) or len(value)>50:raise Invalid('Provider did not report a supported permission list')
    if any(not isinstance(s,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}',s) for s in value):raise Invalid('Provider returned invalid permission names')
    result=sorted(set(value))
    if not set(required)<=set(result):raise Invalid('Required read permissions were declined; reconnect and review the requested access')
    return result


def seconds(value,label='access expiry'):
    """Record provider-reported duration, never a fabricated permanent login."""
    if type(value) is not int or not 1<=value<=5*366*86400:raise Invalid('Provider returned invalid '+label)
    return value
