"""Verify actual provider subjects and read permissions, without returning tokens."""
import time
from dataclasses import dataclass
from .common import Invalid
from .social_auth import app_secret_proof
from .social_contract import account_id,display,reported_scopes,opaque
from .social_registry import PROVIDERS
from .social_transport import request,SocialError


@dataclass(frozen=True)
class Identity:
    """Only public facts cross the service boundary; credentials remain separate."""
    subject_id:str
    name:str
    destinations:list
    permissions:list|None
    expires_at:float|None=None


def one(value):
    """Instagram may wrap exactly one account; competing identities are rejected."""
    if not isinstance(value,dict) or value.get('error'):raise SocialError('INVALID_RESPONSE')
    if 'data' not in value:return value
    data=value['data']
    if 'id' in value or not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):raise SocialError('INVALID_RESPONSE')
    return data[0]


def verify(config,secret,grant,alive=lambda:None):
    """Identity comes from the provider, never a supplied name or decoded JWT."""
    provider=config['provider'];access=grant.credentials['access_token']
    if provider=='facebook':return facebook(config,secret,access,alive)
    raw=request(provider,'identity',{'access_token':access} if provider=='instagram' else {},
                bearer=None if provider=='instagram' else access,alive=alive)
    if provider=='tiktok':return tiktok(raw,grant)
    if provider=='instagram':return instagram(raw,grant)
    if provider=='linkedin':
        subject=account_id(raw.get('sub'));name=display(raw.get('name'))
        return Identity(subject,name,[destination(subject,name,'PROFILE')],grant.facts['reported_scopes'])
    raise Invalid('Choose a supported social provider')


def destination(identity,name,kind,tasks=None):
    """Closed public selection fields cannot carry a Page or user access token."""
    return dict(id=account_id(identity),name=display(name),kind=kind,tasks=tasks or [])


def tiktok(raw,grant):
    """Check both the API error envelope and the open_id returned by the grant."""
    error=raw.get('error');data=raw.get('data')
    if not isinstance(error,dict) or error.get('code')!='ok' or not isinstance(data,dict):raise SocialError('INVALID_RESPONSE')
    user=data.get('user')
    if not isinstance(user,dict):raise SocialError('INVALID_RESPONSE')
    subject=account_id(user.get('open_id'));name=display(user.get('display_name'))
    if subject!=grant.facts['subject_id']:raise Invalid('TikTok account differs from the authorized grant; reconnect')
    return Identity(subject,name,[destination(subject,name,'PROFILE')],grant.facts['reported_scopes'])


def instagram(raw,grant):
    """Keep app-scoped profile ID distinct from the professional user ID."""
    user=one(raw);scoped=account_id(user.get('id'));subject=account_id(user.get('user_id'));name=display(user.get('username'))
    if user.get('account_type') not in ('BUSINESS','MEDIA_CREATOR'):raise Invalid('Instagram requires a professional Business or Creator account')
    if subject!=grant.facts['subject_id']:raise Invalid('Instagram account differs from the authorized grant; reconnect')
    selected=destination(subject,name,'PROFESSIONAL');selected['app_scoped_id']=scoped
    return Identity(subject,name,[selected],grant.facts['reported_scopes'])


def facebook(config,secret,access,alive):
    """Inspect the app binding, user identity, actual permissions and owned Pages."""
    app=request('facebook','app_token',dict(client_id=config['client_id'],client_secret=secret),alive=alive)
    app_access=opaque(app.get('access_token'))
    inspection=request('facebook','inspect',dict(input_token=access,access_token=app_access),alive=alive).get('data')
    if not isinstance(inspection,dict) or inspection.get('is_valid') is not True:raise Invalid('Facebook grant is no longer valid; reconnect')
    if account_id(inspection.get('app_id'))!=config['client_id']:raise Invalid('Facebook grant belongs to a different developer app')
    subject=account_id(inspection.get('user_id'))
    scopes=reported_scopes(inspection.get('scopes'),PROVIDERS['facebook']['scopes'])
    proof={'appsecret_proof':app_secret_proof(access,secret)}
    user=request('facebook','identity',proof,bearer=access,alive=alive)
    if account_id(user.get('id'))!=subject:raise Invalid('Facebook account differs from the inspected grant; reconnect')
    permissions=page_rows('permissions',access,proof,alive)
    granted=reported_scopes([row.get('permission') for row in permissions if row.get('status')=='granted'],PROVIDERS['facebook']['scopes'])
    if not set(scopes)<=set(granted):raise Invalid('Facebook permission inspection changed; reconnect')
    pages=page_rows('pages',access,proof,alive);choices=[];seen=set()
    for page in pages:
        selected=facebook_page(page)
        if selected['id'] in seen:raise SocialError('INVALID_RESPONSE')
        seen.add(selected['id']);choices.append(selected)
    expiry=facebook_expiry(inspection)
    return Identity(subject,display(user.get('name')),choices,granted,expiry)


def facebook_expiry(inspection):
    """Zero or absent Page lifetime is unknown, never a permanent-login promise."""
    values=[]
    for key in ('expires_at','data_access_expires_at'):
        value=inspection.get(key)
        if value is None or value==0:continue
        if type(value) is not int or value<=time.time():raise Invalid('Facebook access expired; reconnect')
        values.append(value)
    return min(values) if values else None


def facebook_page(page):
    """Return sanitized choices; access tokens are never included in selection JSON."""
    tasks=page.get('tasks')
    if not isinstance(tasks,list) or len(tasks)>50:raise SocialError('INVALID_RESPONSE')
    tasks=[opaque(task,'Page task',80) for task in tasks]
    return destination(page.get('id'),page.get('name'),'PAGE',tasks)


def page_rows(operation,access,proof,alive):
    """Follow cursor values only, never a provider-supplied next URL; cap at500."""
    rows=[];seen=set();fields=dict(proof)
    for _ in range(10):
        raw=request('facebook',operation,fields,bearer=access,alive=alive)
        data=raw.get('data')
        if raw.get('error') or not isinstance(data,list) or any(not isinstance(row,dict) for row in data):raise SocialError('INVALID_RESPONSE')
        rows.extend(data)
        if len(rows)>500:raise Invalid('Too many Facebook destinations; narrow Page access in the official consent screen')
        after=next_cursor(raw)
        if after is None:return rows
        if after in seen:raise SocialError('INVALID_RESPONSE')
        seen.add(after);fields={**proof,'after':after}
    raise Invalid('Facebook Page selection exceeded its bounded read; narrow consent and reconnect')


def next_cursor(raw):
    """Only a cursor selects the next fixed-host request; the next URL is ignored."""
    paging=raw.get('paging') or {}
    if not isinstance(paging,dict):raise SocialError('INVALID_RESPONSE')
    if not paging.get('next'):return None
    cursors=paging.get('cursors');after=cursors.get('after') if isinstance(cursors,dict) else None
    return opaque(after,'Page cursor',2048)


def selected_page(secret,access,selected,alive=lambda:None):
    """Recheck ownership immediately before retaining only the approved Page grant."""
    proof={'appsecret_proof':app_secret_proof(access,secret)}
    matches=[row for row in page_rows('pages',access,proof,alive) if str(row.get('id'))==selected]
    if len(matches)!=1:raise Invalid('Selected Facebook Page is no longer available; reconnect and choose again')
    row=matches[0];public=facebook_page(row);token=opaque(row.get('access_token'),'Page access token')
    identity=request('facebook','page_identity',dict(account=selected,appsecret_proof=app_secret_proof(token,secret)),bearer=token,alive=alive)
    if account_id(identity.get('id'))!=selected:raise Invalid('Selected Facebook Page could not be verified')
    public['name']=display(identity.get('name'))
    return public,token
