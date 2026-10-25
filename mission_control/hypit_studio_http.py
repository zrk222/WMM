"""Direct loopback session reads with a total deadline, including streamed headers."""
from http.client import HTTPConnection,HTTPException
import socket
import threading
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from .common import Invalid

CHUNK_BYTES=65536


class OwnedConnection(HTTPConnection):
    def connect(self):
        super().connect()
        self.owned_socket=self.sock

    def expire(self):
        self.expired=True
        try:self.owned_socket.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        finally:self.owned_socket.close()


def connection_for(origin,deadline):
    """Construct only the canonical owned loopback connection before its deadline."""
    target=urlsplit(origin)
    if target.hostname!='127.0.0.1' or target.port is None or origin!='http://127.0.0.1:'+str(target.port):
        raise Invalid('Studio requires its owned IPv4 loopback origin')
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Studio observation deadline expired')
    return OwnedConnection('127.0.0.1',target.port,timeout=remaining)


def session_bytes(origin,observe,deadline,maximum):
    """No proxy or redirect handler; a watchdog interrupts even slow header reads."""
    connection=connection_for(origin,deadline)
    connection.expired=False;timer=None
    try:
        connection.connect()
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Studio observation deadline expired')
        timer=threading.Timer(remaining,connection.expire);timer.daemon=True;timer.start()
        connection.request('GET','/__studio/session',headers={'Origin':origin})
        with connection.getresponse() as response:
            if response.status!=200:
                raise HTTPError(origin,response.status,'Studio session unavailable',response.headers,None)
            if response.headers.get_content_type()!='application/json':
                raise Invalid('Studio returned an unsupported session response')
            return bounded_body(response,observe,deadline,maximum)
    except HTTPError:raise
    except PermissionError:raise
    except (OSError,HTTPException) as error:
        if connection.expired or time.monotonic()>=deadline:
            raise TimeoutError('Studio observation deadline expired') from None
        raise URLError('Studio loopback connection is unavailable') from error
    finally:
        if timer is not None:timer.cancel();timer.join()
        connection.close()


def bounded_body(response,observe,deadline,maximum):
    """read1 returns available chunks; authority is checked between network reads."""
    body=bytearray()
    while True:
        observe()
        if time.monotonic()>=deadline:raise TimeoutError('Studio observation deadline expired')
        chunk=response.read1(min(CHUNK_BYTES,maximum-len(body)+1))
        if not chunk:
            if response.length not in (None,0):raise Invalid('Studio session response ended before its declared size')
            break
        body.extend(chunk)
        if len(body)>maximum:raise Invalid('Studio session response exceeded its bound')
    observe()
    if time.monotonic()>=deadline:raise TimeoutError('Studio observation deadline expired')
    return bytes(body)


def parameter_bytes(origin,body,observe,deadline,maximum,before_send=None):
    """A single fixed mutation send; its caller persists intent before entering."""
    if not isinstance(body,bytes) or not 0<len(body)<=1048576:
        raise Invalid('Studio parameter request exceeds its byte bound')
    connection=connection_for(origin,deadline);connection.expired=False;timer=None
    try:
        observe();connection.connect();observe()
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Studio mutation deadline expired')
        timer=threading.Timer(remaining,connection.expire);timer.daemon=True;timer.start()
        if before_send is not None:before_send()
        connection.request('POST','/__studio/mutation',body=body,
            headers={'Origin':origin,'Content-Type':'application/json'})
        with connection.getresponse() as response:
            if response.headers.get_content_type()!='application/json':
                raise Invalid('Studio mutation response is not JSON')
            status=response.status;raw=bounded_body(response,observe,deadline,maximum)
        observe();return status,raw
    except PermissionError:raise
    except (OSError,HTTPException) as error:
        if connection.expired or time.monotonic()>=deadline:
            raise TimeoutError('Studio mutation deadline expired') from None
        raise URLError('Studio mutation connection is unavailable') from error
    finally:
        if timer is not None:timer.cancel();timer.join()
        connection.close()
