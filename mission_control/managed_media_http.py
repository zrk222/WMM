"""Fresh-owner local media transport; original inspection is separate from reuse."""
from contextlib import contextmanager
import re
from urllib.parse import unquote
import secrets
from .common import Invalid
from .http_body import read_exact
from .operation_authority import bound_owner, protected
from .operator_client import strict_json

MAX_BYTES=67108864


def singleton(handler, name):
    """Duplicate values cannot alter an upload or owner-bound request identity."""
    values=handler.headers.get_all(name)
    if not values or len(values)!=1:raise Invalid('Use exactly one '+name+' header')
    return values[0]


def route(handler, parts):
    """Reject encoded, repeated, queried or trailing path variants before access."""
    if len(parts) not in (4,5,6) or parts[:2]!=['api','apps'] or parts[3]!='media':
        raise Invalid('Use the exact app media address')
    if handler.path!='/'+'/'.join(parts):raise Invalid('Use the exact app media address')
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}',parts[2]):raise Invalid('Invalid media app identifier')


@contextmanager
def owner(handler, parts):
    """Recheck the admitted principal and role inside every guarded transaction."""
    route(handler,parts);origin='http://127.0.0.1:'+str(handler.server.server_port)
    if handler.headers.get_all('Host')!=[origin[7:]]:raise PermissionError('Use the exact local media host')
    origins=handler.headers.get_all('Origin')
    if (origins is not None or handler.command=='POST') and origins!=[origin]:
        raise PermissionError('Use the exact local media origin')
    session=handler.session();user=handler.server.identities.fresh(session)
    if handler.command=='POST' and not secrets.compare_digest(singleton(handler,'X-CSRF-Token'),session):
        raise PermissionError('Reload the current media session')
    store=handler.server.service.store
    envelope=dict(app_id=parts[2],operation='media.owner',input=dict(method=handler.command,path=handler.path))
    with bound_owner(store,envelope,handler.server.identities,session,user):
        with protected(store,envelope):yield store,user


def body(handler, content_type, limit):
    """Apply exact framing and a total deadline before inspecting any bytes."""
    if singleton(handler,'Content-Type')!=content_type:raise Invalid('Use '+content_type+' for media input')
    if handler.headers.get_all('Transfer-Encoding') is not None:raise Invalid('Media input cannot use transfer encoding')
    length=singleton(handler,'Content-Length')
    if not re.fullmatch(r'[0-9]{1,8}',length) or not 1<=int(length)<=limit:
        raise Invalid('Media input exceeds its bounded byte limit')
    return read_exact(handler,limit,'Media')


def post(handler, parts):
    """Upload immutable originals or append owner attestations, never publish."""
    from .managed_media_store import Media
    with owner(handler,parts) as (store,user):
        media=Media(store)
        if parts[4:]==['uploads']:
            name=singleton(handler,'X-Filename');version=singleton(handler,'X-WMM-Manifest-Version')
            key=singleton(handler,'X-WMM-Request-Key')
            if len(name)>2048 or not re.fullmatch(r'[1-9][0-9]{0,9}',version):raise Invalid('Reload the current media upload fields')
            raw=body(handler,'application/octet-stream',MAX_BYTES)
            result=media.upload(parts[2],unquote(name,errors='strict'),raw,dict(manifest_version=int(version),request_key=key))
            return handler.send(201,result)
        if len(parts)==6 and parts[5]=='reviews':
            value=strict_json(body(handler,'application/json',16384))
            return handler.send(200,media.review(parts[2],parts[4],value,user))
        raise Invalid('Use the exact media upload or review address')


def get(handler, parts):
    """Expose only verified app-owned originals, including partial byte reads."""
    from .managed_media_store import Media
    with owner(handler,parts) as (store,user):
        media=Media(store)
        if len(parts)==4:return handler.send(200,media.list(parts[2]))
        if len(parts)==5:return handler.send(200,media.read(parts[2],parts[4]))
        if parts[5] not in ('preview','download'):raise Invalid('Use the exact original media address')
        item,raw=media.original(parts[2],parts[4],user['principal'])
        from pathlib import Path
        return serve(handler,parts,item,raw,Path(item['filename']).suffix.lower())


def serve(handler, parts, item, raw, suffix):
    """Use internal download names and actual verified lengths for Range responses."""
    from .server import media_range
    mime={'.mp4':'video/mp4','.mov':'video/quicktime','.webm':'video/webm'}[suffix]
    filename=parts[4]+suffix if parts[5]=='download' else None
    headers={'Accept-Ranges':'bytes'};ranges=handler.headers.get_all('Range')
    if ranges is None:return handler.send(200,raw,mime,filename,headers)
    if len(ranges)!=1:raise Invalid('Use one media byte range')
    try:start,end=media_range(ranges[0],len(raw))
    except Invalid:return handler.send(416,b'',mime,headers=dict(headers,**{'Content-Range':f'bytes */{len(raw)}'}))
    headers['Content-Range']=f'bytes {start}-{end}/{len(raw)}'
    return handler.send(206,raw[start:end+1],mime,filename,headers)
