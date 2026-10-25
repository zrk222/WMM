"""Exact local HTTP payload reads with a cumulative wall-clock budget."""
import time
from .common import Invalid


def read_exact(handler, limit, label):
    """A trickle sender cannot renew the five-second total body-read deadline."""
    expected=int(handler.headers['Content-Length'])
    if not 0<expected<=limit:raise Invalid('Request is empty or exceeds the upload limit')
    previous=handler.connection.gettimeout();deadline=time.monotonic()+5;chunks=[];count=0
    try:
        while count<expected:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError()
            handler.connection.settimeout(remaining)
            chunk=handler.rfile.read1(min(65536,expected-count))
            if time.monotonic()>=deadline:raise TimeoutError()
            if not chunk:raise Invalid(label+' request body is truncated')
            chunks.append(chunk);count+=len(chunk)
    except (TimeoutError,OSError):
        handler.close_connection=True
        raise Invalid(label+' request body did not arrive within 5 seconds') from None
    except Invalid:
        handler.close_connection=True
        raise
    finally:handler.connection.settimeout(previous)
    return b''.join(chunks)
