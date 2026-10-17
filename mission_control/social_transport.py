"""Fixed-provider pinned TLS transport; credential-bearing URLs never enter receipts."""
import http.client,secrets,time
from urllib.parse import urlsplit,urlencode
from .common import Invalid
from .aeo_transport import address,PinnedHTTPS,response_headers,response_body
from .aeo_tls import trust_context
from .payment_signature import strict_json
from .social_contract import provider_id,opaque,account_id
from .social_registry import PROVIDERS,META_VERSION


class SocialError(Invalid):
    def __init__(self,code):
        self.code=code
        messages={'ACCESS_DENIED':'Provider access was denied; reconnect or review developer-app permissions.',
          'RATE_LIMITED':'Provider rate limit reached. Preserve this connection and retry its read later.',
          'AUTHORIZATION_REJECTED':'Provider rejected the setup or grant. Review setup or start a new official login.',
          'UNCONFIRMED':'The provider result could not be confirmed. Do not repeat a token exchange automatically; reconnect or inspect the saved state.',
          'INVALID_RESPONSE':'Provider returned an invalid response; existing access is preserved.',
          'REDIRECT_REJECTED':'Provider redirect was rejected before any credential forwarding.'}
        super().__init__(messages.get(code,'Social provider operation failed; inspect setup and reconnect.'))


def endpoint(method,url,params=(),constants=None,optional=(),multipart=False):
    """An operation declares its complete destination and parameter surface."""
    return dict(method=method,url=url,params=params,constants=constants or {},optional=optional,multipart=multipart)


FB='https://graph.facebook.com/'+META_VERSION
OPERATIONS={
 ('facebook','code'):endpoint('GET',PROVIDERS['facebook']['token_url'],('client_id','client_secret','redirect_uri','code')),
 ('facebook','long'):endpoint('GET',PROVIDERS['facebook']['token_url'],('client_id','client_secret','fb_exchange_token'),{'grant_type':'fb_exchange_token'}),
 ('facebook','app_token'):endpoint('GET',PROVIDERS['facebook']['token_url'],('client_id','client_secret'),{'grant_type':'client_credentials'}),
 ('facebook','inspect'):endpoint('GET',FB+'/debug_token',('input_token','access_token')),
 ('facebook','identity'):endpoint('GET',PROVIDERS['facebook']['identity'],constants={'fields':'id,name'},optional=('appsecret_proof',)),
 ('facebook','permissions'):endpoint('GET',FB+'/me/permissions',optional=('appsecret_proof','after')),
 ('facebook','pages'):endpoint('GET',FB+'/me/accounts',constants={'fields':'id,name,tasks,access_token','limit':'50'},optional=('after','appsecret_proof')),
 ('facebook','page_identity'):endpoint('GET',FB+'/{account}',('account',),{'fields':'id,name'},optional=('appsecret_proof',)),
 ('instagram','code'):endpoint('POST',PROVIDERS['instagram']['token_url'],('client_id','client_secret','redirect_uri','code'),{'grant_type':'authorization_code'},multipart=True),
 ('instagram','long'):endpoint('GET','https://graph.instagram.com/access_token',('client_secret','access_token'),{'grant_type':'ig_exchange_token'}),
 ('instagram','refresh'):endpoint('GET','https://graph.instagram.com/refresh_access_token',('access_token',),{'grant_type':'ig_refresh_token'}),
 ('instagram','identity'):endpoint('GET',PROVIDERS['instagram']['identity'],('access_token',),{'fields':'id,user_id,username,account_type'}),
 ('tiktok','code'):endpoint('POST',PROVIDERS['tiktok']['token_url'],('client_key','client_secret','redirect_uri','code','code_verifier'),{'grant_type':'authorization_code'}),
 ('tiktok','refresh'):endpoint('POST',PROVIDERS['tiktok']['token_url'],('client_key','client_secret','refresh_token'),{'grant_type':'refresh_token'}),
 ('tiktok','identity'):endpoint('GET',PROVIDERS['tiktok']['identity'],constants={'fields':'open_id,display_name'}),
 ('linkedin','code'):endpoint('POST',PROVIDERS['linkedin']['token_url'],('client_id','client_secret','redirect_uri','code'),{'grant_type':'authorization_code'}),
 ('linkedin','code_native'):endpoint('POST',PROVIDERS['linkedin']['token_url'],('client_id','redirect_uri','code','code_verifier'),{'grant_type':'authorization_code'}),
 ('linkedin','refresh'):endpoint('POST',PROVIDERS['linkedin']['token_url'],('client_id','client_secret','refresh_token'),{'grant_type':'refresh_token'}),
 ('linkedin','identity'):endpoint('GET',PROVIDERS['linkedin']['identity'])}


def parameters(spec,values):
    """No caller can override a grant type, private field selector or endpoint."""
    if not isinstance(values,dict):raise Invalid('Use the selected social operation parameters')
    if not set(spec['params'])<=set(values) or set(values)-set(spec['params'])-set(spec['optional']):
        raise Invalid('Social operation parameters do not match the fixed adapter')
    for key,value in values.items():opaque(value,'operation parameter',4096)
    result={**spec['constants'],**values};url=spec['url']
    if 'account' in result:
        identity=account_id(result.pop('account'))
        if not identity.isdigit():raise Invalid('Use the verified numeric Page identity')
        url=url.replace('{account}',identity)
    return url,result


def form_body(fields,multipart=False):
    """Use bounded form encoding, including Instagram's documented multipart fields."""
    if not multipart:return urlencode(fields).encode('ascii'),'application/x-www-form-urlencoded'
    boundary='SocialGrowth'+secrets.token_hex(16);parts=[]
    for key,value in fields.items():
        parts.append(('--'+boundary+'\r\nContent-Disposition: form-data; name="'+key+'"\r\n\r\n'+value+'\r\n').encode())
    return b''.join(parts)+('--'+boundary+'--\r\n').encode(),'multipart/form-data; boundary='+boundary


def status_code(status):
    """Classify recovery without reflecting a raw provider response or request URL."""
    if status in (401,403):raise SocialError('ACCESS_DENIED')
    if status==429:raise SocialError('RATE_LIMITED')
    if 300<=status<400:raise SocialError('REDIRECT_REJECTED')
    if status==400:raise SocialError('AUTHORIZATION_REJECTED')
    if status!=200:raise SocialError('UNCONFIRMED')


def request(provider,operation,values=None,bearer=None,alive=lambda:None,deadline=None):
    """One fixed TLS request, no redirects, no secret log or automatic mutation replay."""
    provider_id(provider)
    spec=OPERATIONS.get((provider,operation))
    if spec is None:raise Invalid('Choose a supported social read or authentication operation')
    url,fields=parameters(spec,{} if values is None else values);parts=urlsplit(url)
    headers={'Accept':'application/json','Accept-Encoding':'identity','Cache-Control':'no-store'}
    if bearer:headers['Authorization']='Bearer '+opaque(bearer)
    body=None;route=parts.path
    if spec['method']=='GET':route+=('?'+urlencode(fields)) if fields else ''
    else:body,headers['Content-Type']=form_body(fields,spec['multipart'])
    if body and len(body)>32768:raise Invalid('Social request exceeds its bounded input')
    return exchange(parts,spec['method'],route,body,headers,alive,deadline)


def exchange(parts,method,route,body,headers,alive,deadline):
    """Pin DNS and carry a single deadline through TLS, headers and response framing."""
    limit=min(deadline,time.monotonic()+30) if deadline is not None else time.monotonic()+30
    conn=None;alive()
    try:
        conn=PinnedHTTPS(parts.hostname,address(parts.hostname,limit),trust_context(),limit)
        conn.request(method,route,body=body,headers=headers);response=conn.getresponse();status_code(response.status)
        raw=response_body(response,response_headers(response),1048576,conn,limit)
        value=strict_json(raw)
        if not isinstance(value,dict):raise SocialError('INVALID_RESPONSE')
    except SocialError:raise
    except Invalid:raise SocialError('INVALID_RESPONSE') from None
    except (OSError,ValueError,TimeoutError,RecursionError,http.client.HTTPException):raise SocialError('UNCONFIRMED') from None
    finally:
        if conn is not None:conn.close()
    alive();return value
