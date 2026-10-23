"""Explicit numeric-loopback inference; a local server may itself use cloud services."""
import http.client
import re
import socket
import time
from urllib.parse import urlsplit,urlunsplit
from .common import Invalid,canonical
from .aeo_transport import DeadlineResponse,remaining,response_body,response_headers
from .payment_signature import strict_json
from .agent_contract import draft


def endpoint(value):
    """Normalize only named localhost or numeric loopback, never resolving a host."""
    if not isinstance(value,str) or len(value)>2400 or re.search(r'[\x00-\x20\x7f\\?#]',value):
        raise Invalid('Use an HTTP loopback API base URL without query, credentials or fragment')
    try:
        parts=urlsplit(value)
        return urlunsplit(('http',local_authority(parts),base_path(parts.path),'',''))
    except (ValueError,AttributeError):
        raise Invalid('Use localhost, 127.0.0.1 or [::1] with an explicit local server port and API base path') from None


def local_authority(parts):
    """Close host, scheme, port and credential authority before socket creation."""
    if parts.scheme!='http' or parts.username is not None or parts.password is not None:raise ValueError()
    host={'localhost':'127.0.0.1','127.0.0.1':'127.0.0.1','::1':'::1'}.get(parts.hostname)
    if not host or parts.port is None or not 1<=parts.port<=65535:raise ValueError()
    return ('['+host+']' if ':' in host else host)+':'+str(parts.port)


def base_path(value):
    """Permit literal API base segments without traversal or encoded separators."""
    path=value.rstrip('/')
    if not re.fullmatch(r'(?:/[A-Za-z0-9_.~-]+)*',path) or any(p in ('.','..') for p in path.split('/')):raise ValueError()
    return path


class LocalConnection(http.client.HTTPConnection):
    """Connect to an already validated numeric loopback without proxy or DNS lookup."""
    def __init__(self,parts,deadline):
        """Reuse the existing total-deadline response parser and bounded reader."""
        super().__init__(parts.hostname,parts.port,timeout=remaining(deadline))
        self.deadline=deadline;self.receiving=False
        self.response_class=lambda sock,**kwargs:DeadlineResponse(sock,deadline,**kwargs)

    def connect(self):
        """Own one literal-address socket; close it on an unsuccessful connection."""
        raw=socket.socket(socket.AF_INET6 if ':' in self.host else socket.AF_INET,socket.SOCK_STREAM)
        try:
            raw.settimeout(remaining(self.deadline));raw.connect((self.host,self.port))
            self.sock=raw;self.stream_socket=raw
        except BaseException:
            raw.close();raise

    def getresponse(self):
        """Retain the owned socket through HTTP/1.0 close-framed body consumption."""
        self.receiving=True
        try:return super().getresponse()
        finally:self.receiving=False

    def close(self):
        """Detach only during response framing, then close every owned handle finally."""
        if self.receiving:
            self.sock=None
            return
        super().close()
        stream=getattr(self,'stream_socket',None)
        if stream:stream.close()


def request(profile,key,prompt,max_tokens=2048,alive=lambda:None):
    """Send one reviewed text request with no redirects, tools, fallback or replay."""
    parts=urlsplit(endpoint(profile['endpoint']))
    body=request_body(profile,key,prompt,max_tokens)
    headers={'Content-Type':'application/json','Accept':'application/json','Accept-Encoding':'identity'}
    if key:headers['Authorization']='Bearer '+key
    deadline=time.monotonic()+30;alive();conn=LocalConnection(parts,deadline)
    try:
        conn.request('POST',parts.path+'/chat/completions',body=canonical(body).encode(),headers=headers)
        raw=read_response(conn,deadline)
    except Invalid:raise
    except (OSError,ValueError,http.client.HTTPException):
        raise Invalid('Local inference result could not be confirmed. Inspect the selected server before retrying') from None
    finally:conn.close()
    alive()
    return result(raw,key)


def request_body(profile,key,prompt,max_tokens):
    """Bound reviewed text, output allowance and optional key before any network IO."""
    if not isinstance(prompt,str) or len(prompt.encode())>32768:raise Invalid('Local prompt exceeds 32768 bytes')
    if type(max_tokens) is not int or not 1<=max_tokens<=2048:raise Invalid('Use a local output allowance from 1 through 2048 tokens')
    if key is not None and (not isinstance(key,str) or not re.fullmatch(r'[!-~]{1,1800}',key)):
        raise Invalid('Use an optional local bearer key without whitespace')
    return dict(model=profile['model'],messages=[dict(role='user',content=prompt)],stream=False,max_tokens=max_tokens)


def read_response(conn,deadline):
    """Reject redirects and unsupported framing before reading a bounded JSON body."""
    response=conn.getresponse()
    if response.status!=200:raise Invalid('Local model server rejected the request; no redirect, fallback or replay was attempted')
    meta=response_headers(response)
    if len(meta.get('content-type',[]))!=1 or meta['content-type'][0].split(';')[0].strip().lower()!='application/json':
        raise Invalid('Local model server must return JSON')
    return response_body(response,meta,1048576,conn,deadline)


def result(raw,key):
    """Accept only a plain final structured draft, rejecting protected-key echoes."""
    from .agent_api import message
    value=strict_json(raw);text=message(value,False)
    if key and key in text:raise Invalid('Local model server echoed a protected key; output was rejected')
    return draft(strict_json(text.encode())),value.get('usage')
