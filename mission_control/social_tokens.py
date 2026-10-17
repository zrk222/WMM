"""Provider token responses become protected credentials plus non-secret facts."""
from dataclasses import dataclass
from .common import Invalid
from .social_contract import opaque,seconds,reported_scopes,account_id,provider_id
from .social_registry import PROVIDERS
from .social_transport import SocialError


@dataclass(frozen=True)
class Grant:
    credentials:dict
    facts:dict


def token_object(raw):
    """Accept one Instagram wrapper or one flat response, never ambiguous subjects."""
    if not isinstance(raw,dict):raise SocialError('INVALID_RESPONSE')
    if raw.get('error'):raise SocialError('AUTHORIZATION_REJECTED')
    if 'data' in raw:
        data=raw['data']
        if 'access_token' in raw or not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):raise SocialError('INVALID_RESPONSE')
        return data[0]
    return raw


def parse(provider,raw,issued_at,prior=None,short=False):
    """Preserve actual lifetime/scope reporting and require a usable protected token."""
    provider_id(provider);value=token_object(raw);prior=prior or {}
    credentials=credential_fields(value)
    expires=None if short else issued_at+seconds(value.get('expires_in'))
    subject=account_id(value['open_id']) if provider=='tiktok' else prior.get('subject_id')
    if provider=='instagram' and short:subject=account_id(value.get('user_id'))
    scopes=parse_scopes(provider,value,prior)
    refresh_expiry=refresh_lifetime(provider,value,issued_at,prior)
    facts=dict(provider=provider,subject_id=subject,issued_at=issued_at,expires_at=expires,
               refresh_expires_at=refresh_expiry,reported_scopes=scopes,
               requested_scopes=list(PROVIDERS[provider]['scopes']),renewal=renewal(provider,credentials,short))
    if provider=='tiktok' and 'refresh_token' not in credentials:raise SocialError('INVALID_RESPONSE')
    return Grant(credentials,facts)


def credential_fields(value):
    """Validate token type and retain only the actual access and refresh grants."""
    credentials={'access_token':opaque(value.get('access_token'),'access token')}
    if 'token_type' in value and str(value['token_type']).lower()!='bearer':raise SocialError('INVALID_RESPONSE')
    if 'refresh_token' in value:credentials['refresh_token']=opaque(value['refresh_token'],'refresh token')
    return credentials


def parse_scopes(provider,value,prior):
    """Only reported permissions are labelled granted; missing reports stay unknown."""
    field='permissions' if provider=='instagram' else 'scope'
    if field in value:return reported_scopes(value[field],PROVIDERS[provider]['scopes'])
    if provider=='tiktok':raise SocialError('INVALID_RESPONSE')
    return prior.get('reported_scopes')


def refresh_lifetime(provider,value,issued_at,prior):
    """LinkedIn's refresh window is fixed; other durations follow provider reporting."""
    field='refresh_token_expires_in' if provider=='linkedin' else 'refresh_expires_in'
    previous=prior.get('refresh_expires_at')
    if field not in value:return previous
    expiry=issued_at+seconds(value[field],'refresh expiry')
    if provider=='linkedin' and previous is not None:return min(expiry,previous)
    return expiry


def renewal(provider,credentials,short=False):
    """Do not present absent refresh entitlement as permanent or automatic login."""
    if short:return 'LONG_TOKEN_EXCHANGE_REQUIRED'
    if provider=='instagram':return 'LONG_LIVED_TOKEN_REFRESH'
    if provider in ('tiktok','linkedin') and credentials.get('refresh_token'):return 'REFRESH_TOKEN'
    return 'OFFICIAL_REAUTHORIZATION'


def same_subject(grant,expected):
    """A provider-reported subject cannot silently change during renewal."""
    subject=grant.facts.get('subject_id')
    if subject is not None and subject!=expected:raise Invalid('Social account changed during renewal; reconnect and confirm the account')
