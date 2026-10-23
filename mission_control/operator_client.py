"""Bounded local HTTP transport. No proxy, redirect, credential loading or auto retry."""
from http.cookiejar import CookieJar
from http.client import HTTPException
import json
import re
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener,ProxyHandler,HTTPCookieProcessor,HTTPRedirectHandler
from .common import Invalid,canonical
from .operation_catalog import request_data

MAX_BYTES=16777216
TIMEOUT_SECONDS=15


class ClientError(Exception):
    """Stable failure classification without dumping raw server responses or credentials."""
    def __init__(self,code,message,status=None):
        super().__init__(message)
        self.code=code
        self.status=status


class NoRedirect(HTTPRedirectHandler):
    """Never forward a session or POST to a redirected destination."""
    def redirect_request(self,request,fp,code,message,headers,newurl):
        raise ClientError('REDIRECT_REJECTED','The local server redirected the request; no follow-up was sent',code)


def origin_data(value):
    """Allow only a literal canonical IPv4 loopback origin with an explicit valid port."""
    if not isinstance(value,str):
        raise Invalid('Use http://127.0.0.1:PORT as the WMM origin')
    match=re.fullmatch(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})',value)
    if not match or int(match[1])>65535:
        raise Invalid('Use http://127.0.0.1:PORT with a port from 1 through 65535')
    return value


def unique_pairs(pairs):
    """Reject duplicate keys instead of accepting a different caller/server interpretation."""
    value={}
    for key,item in pairs:
        if key in value:
            raise Invalid('Duplicate JSON keys are forbidden')
        value[key]=item
    return value


def invalid_constant(value):
    """Keep NaN and infinity out of transport data."""
    raise Invalid('Nonfinite JSON values are forbidden')


def strict_json(raw):
    """Bound bytes and reject malformed UTF-8, duplicate keys, constants and deep trees."""
    if len(raw)>MAX_BYTES:
        raise Invalid('JSON exceeds the 16777216 bytes limit')
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_pairs,parse_constant=invalid_constant)
        # Re-encoding also rejects values overflowing JSON's finite numeric range.
        canonical(value)
        return value
    except (UnicodeError,ValueError,RecursionError) as error:
        raise Invalid('Invalid strict UTF-8 JSON: '+type(error).__name__) from error


def response_data(response):
    """Require bounded JSON; do not print a remote HTML error document."""
    if response.headers.get_content_type()!='application/json':
        raise ClientError('INVALID_RESPONSE','WMM returned a non-JSON response')
    raw=response.read(MAX_BYTES+1)
    try:
        return strict_json(raw)
    except Invalid as error:
        raise ClientError('INVALID_RESPONSE',str(error)) from error


class OperatorClient:
    """Use existing trusted-local API semantics; this client grants no extra authority."""
    def __init__(self,origin):
        self.origin=origin_data(origin)
        self.csrf=None
        self.cookies=CookieJar()
        self.opener=build_opener(ProxyHandler({}),HTTPCookieProcessor(self.cookies),NoRedirect())

    def bootstrap(self):
        """Retain the session in RAM only and discard every other bootstrap field."""
        result=self.request('GET','/api/bootstrap')
        token=result.get('csrf') if isinstance(result,dict) else None
        if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,256}',token):
            raise ClientError('INVALID_SESSION','WMM bootstrap did not provide a valid CSRF token')
        self.csrf=token

    def call(self,envelope):
        """Resolve the fixed catalog before networking; retry policy is always caller controlled."""
        value=request_data(envelope)
        # Validate serialization and size before creating a session.
        encode_body(value['body'])
        if self.csrf is None:
            self.bootstrap()
        return self.request(value['method'],value['path'],value['body'])

    def request(self,method,path,body=None):
        """Execute one internal fixed route with exact origin, cookie and CSRF boundaries."""
        payload=encode_body(body)
        headers={'Accept':'application/json','Origin':self.origin}
        if payload is not None:
            headers.update({'Content-Type':'application/json','X-CSRF-Token':self.csrf or ''})
        request=Request(self.origin+path,data=payload,headers=headers,method=method)
        try:
            with self.opener.open(request,timeout=TIMEOUT_SECONDS) as response:
                return response_data(response)
        except HTTPError as error:
            error.close()
            raise ClientError('HTTP_REJECTED','WMM rejected the operation; HTTP '+str(error.code)+'. Refresh current app/source data before retrying.',error.code) from error
        except (URLError,TimeoutError,OSError,HTTPException) as error:
            raise ClientError('TRANSPORT_UNAVAILABLE','The local WMM operation did not return a confirmed result. Inspect saved history before retrying a write.') from error


def encode_body(value):
    """Validate finite bounded payloads before any network activity."""
    if value is None:
        return None
    try:
        raw=canonical(value).encode('utf-8')
    except (ValueError,TypeError,RecursionError) as error:
        raise Invalid('Operation input must be finite serializable JSON') from error
    if len(raw)>MAX_BYTES:
        raise Invalid('Operation input exceeds 16777216 bytes')
    return raw
