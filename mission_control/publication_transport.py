"""Bounded fixed-provider HTTP, using WMM's pinned TLS and response framing.

No redirects, automatic retries, credential diagnostics or arbitrary media fetches.
Upload URLs are private capabilities; only documented provider destinations pass.
"""
from dataclasses import dataclass, field
import http.client
import json
import re
import time
from urllib.parse import urlencode, urlsplit, unquote

from .aeo_transport import address, PinnedHTTPS, response_headers, response_body
from .aeo_tls import trust_context
from .common import Invalid
from .payment_signature import strict_json
from .social_contract import opaque

MAX_UPLOAD_BYTES=64*1024*1024
API_BASES={'instagram':'https://graph.instagram.com','tiktok':'https://open.tiktokapis.com',
           'youtube':'https://www.googleapis.com','linkedin':'https://api.linkedin.com'}
UPLOAD_PATHS={
    'instagram':{'rupload.facebook.com':('/ig-api-upload/',)},
    'tiktok':{'open-upload.tiktokapis.com':('/video/',), 'upload.us.tiktokapis.com':('/video/',)},
    'youtube':{'www.googleapis.com':('/upload/youtube/',)},
    'linkedin':{'www.linkedin.com':('/dms-uploads/',)},
}
CUSTOM_HEADERS={'content-type','content-range','linkedin-version','x-restli-protocol-version',
                'x-upload-content-type','x-upload-content-length','offset','file_size'}
RESPONSE_HEADERS={'location','etag','x-restli-id','range','retry-after','content-type'}


@dataclass(frozen=True, repr=False)
class Context:
    provider: str
    destination_id: str
    token: str=field(repr=False)
    before_call: object=field(repr=False)
    heartbeat: object=field(repr=False)
    login_family: str='default'


@dataclass(frozen=True, repr=False)
class Response:
    status: int
    headers: dict=field(repr=False)
    data: dict=field(repr=False)


class PublicationError(Invalid):
    def __init__(self,code):
        self.code=code
        messages={'ACCESS_DENIED':'Reconnect this channel and review its publishing permissions.',
                  'RATE_LIMITED':'The channel rate limit was reached. Keep the saved intent and check its retry time.',
                  'REJECTED':'The channel rejected this action. Review its saved requirements before retrying.',
                  'REDIRECT_REJECTED':'An unexpected upload redirect was rejected without forwarding credentials.',
                  'UNKNOWN':'The channel response could not be confirmed. Reconcile the saved intent before another action.'}
        super().__init__(messages.get(code,messages['UNKNOWN']))


def checked_context(context):
    if (type(context) is not Context or context.provider not in API_BASES
            or not callable(context.before_call) or not callable(context.heartbeat)):
        raise Invalid('Use a server-owned channel transport context')
    opaque(context.token,'channel credential')
    opaque(context.destination_id,'channel destination',200)
    if context.login_family not in ('default','instagram','facebook'):
        raise Invalid('Choose a supported channel login family')
    if context.login_family=='facebook' and context.provider!='instagram':
        raise Invalid('The Facebook login family applies only to the Instagram adapter')
    return context


def checked_path(path):
    if (not isinstance(path,str) or not path.startswith('/') or path.startswith('//')
            or len(path)>4096 or re.search(r'[\s\\?#\x00-\x1f\x7f]',path)
            or re.search(r'%(?![0-9A-Fa-f]{2})|%2f|%5c',path,re.I)):
        raise Invalid('Use a fixed channel API path')
    decoded=unquote(path)
    if any(part in ('.','..') for part in decoded.split('/')) or re.search(r'[\s\\?#\x00-\x1f\x7f]',decoded):
        raise Invalid('Use a fixed channel API path')
    return path


def api_url(context,path):
    context=checked_context(context)
    base=API_BASES[context.provider]
    if context.provider=='instagram' and context.login_family=='facebook':
        base='https://graph.facebook.com'
    return base+checked_path(path)


def upload_target(context,url):
    context=checked_context(context)
    if not isinstance(url,str) or len(url)>8192 or re.search(r'[\s\\\x00-\x1f\x7f]',url):
        raise Invalid('Use the current protected provider upload session')
    parts=urlsplit(url)
    try: port=parts.port
    except ValueError: raise Invalid('Use the current protected provider upload session') from None
    prefixes=UPLOAD_PATHS[context.provider].get(parts.hostname,())
    if not _upload_origin(parts,port) or not prefixes or not parts.path.startswith(prefixes):
        raise Invalid('Use the current protected provider upload session')
    checked_path(parts.path)
    return parts


def _upload_origin(parts,port):
    return parts.scheme=='https' and not parts.username and not parts.password and port in (None,443) and not parts.fragment


def _custom_header(key,value):
    if not isinstance(key,str) or key.lower() not in CUSTOM_HEADERS:
        raise Invalid('Use the documented channel headers')
    if not isinstance(value,str) or len(value)>256 or re.search(r'[^ -~]',value):
        raise Invalid('Use the documented channel headers')


def extra_headers(values):
    if values is None:return {}
    if not isinstance(values,dict) or len(values)>12:raise Invalid('Use the documented channel headers')
    result={}
    for key,value in values.items():
        _custom_header(key,value)
        if key.lower() in {name.lower() for name in result}:raise Invalid('Duplicate channel header')
        result[key]=value
    return result


def _headers(context,custom,bearer=True,scheme='Bearer'):
    result={'Accept':'application/json','Accept-Encoding':'identity','Cache-Control':'no-store'}
    result.update(extra_headers(custom))
    if bearer:result['Authorization']=scheme+' '+context.token
    return result


def _status(status,expected):
    if status in expected:return
    if status in (401,403):raise PublicationError('ACCESS_DENIED')
    if status==429:raise PublicationError('RATE_LIMITED')
    if 300<=status<400:raise PublicationError('REDIRECT_REJECTED')
    if 400<=status<500:raise PublicationError('REJECTED')
    raise PublicationError('UNKNOWN')


def _exchange(context,parts,method,route,body,headers,expected,response_json,seconds):
    context.before_call()
    deadline=time.monotonic()+seconds
    conn=None
    try:
        conn=PinnedHTTPS(parts.hostname,address(parts.hostname,deadline),trust_context(),deadline)
        context.heartbeat()
        conn.request(method,route,body=body,headers=headers)
        response=conn.getresponse()
        _status(response.status,expected)
        framing=response_headers(response)
        raw=response_body(response,framing,1048576,conn,deadline)
        data=strict_json(raw) if response_json and raw else {}
        if not isinstance(data,dict):raise PublicationError('UNKNOWN')
        retained={}
        for key,value in response.getheaders():
            if key.lower() in RESPONSE_HEADERS:
                if key.lower() in retained:raise PublicationError('UNKNOWN')
                if not isinstance(value,str) or len(value)>8192 or re.search(r'[\r\n\x00]',value):
                    raise PublicationError('UNKNOWN')
                retained[key.lower()]=value
        return Response(response.status,retained,data)
    except PublicationError:raise
    except (OSError,ValueError,TimeoutError,RecursionError,http.client.HTTPException):
        raise PublicationError('UNKNOWN') from None
    finally:
        if conn is not None:conn.close()


def request(context,method,path,*,query=None,json_body=None,form=None,headers=None,
            expected=(200,),response_json=True):
    url=api_url(context,path)
    if method not in ('GET','POST','PUT'):raise Invalid('Use a supported channel API method')
    if json_body is not None and form is not None:raise Invalid('Use one channel request encoding')
    body=None
    custom=extra_headers(headers)
    if json_body is not None:
        body=json.dumps(json_body,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')
        custom['Content-Type']='application/json; charset=utf-8'
    if form is not None:
        body=urlencode(form).encode('ascii');custom['Content-Type']='application/x-www-form-urlencoded'
    if body is not None and len(body)>65536:raise Invalid('Channel metadata exceeds 65536 bytes')
    route=path
    if query:
        encoded=urlencode(query)
        if len(encoded)>32768:raise Invalid('Channel query exceeds 32768 characters')
        route+='?'+encoded
    return _exchange(context,urlsplit(url),method,route,body,_headers(context,custom),expected,response_json,30)


def _chunks(raw,context):
    for offset in range(0,len(raw),65536):
        context.heartbeat()
        yield raw[offset:offset+65536]


def _upload_options(context,data,method,auth_scheme,bearer):
    if type(data) is not bytes or len(data)>MAX_UPLOAD_BYTES:raise Invalid('Use a bounded immutable upload chunk')
    if method not in ('PUT','POST') or (method=='POST' and context.provider!='instagram'):
        raise Invalid('Use the provider upload method')
    if auth_scheme not in ('Bearer','OAuth') or (auth_scheme=='OAuth' and context.provider!='instagram'):
        raise Invalid('Use the provider upload authorization scheme')
    if bearer and context.provider not in ('youtube','instagram'):
        raise Invalid('Do not forward account credentials to this upload host')


def _upload_headers(headers,content_type,content_range):
    custom=extra_headers(headers)
    if content_type not in ('video/mp4','video/webm','video/quicktime','application/octet-stream'):
        raise Invalid('Use the supported video content type')
    custom['Content-Type']=content_type
    if content_range is not None:
        if not isinstance(content_range,str) or not re.fullmatch(r'bytes (?:\d+-\d+|\*)/\d+',content_range):
            raise Invalid('Use an exact provider upload byte range')
        custom['Content-Range']=content_range
    return custom


def upload(context,url,data,*,content_type='video/mp4',content_range=None,headers=None,
           expected=(200,),bearer=False,method='PUT',auth_scheme='Bearer',response_json=True):
    """Transfer one approved bounded chunk to a pinned provider upload host."""
    parts=upload_target(context,url)
    _upload_options(context,data,method,auth_scheme,bearer)
    custom=_upload_headers(headers,content_type,content_range)
    outgoing=_headers(context,custom,bearer,auth_scheme)
    outgoing['Content-Length']=str(len(data))
    route=parts.path+('?'+parts.query if parts.query else '')
    return _exchange(context,parts,method,route,_chunks(data,context),outgoing,expected,response_json,300)
