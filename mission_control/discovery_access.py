"""Currentness and bounded research history shared by every authorized client."""
from .common import Invalid
from .db import connection
from .pmf_contract import exact, count, one
from .funnel_store import app_context
from .discovery_store import Discovery, decoded, latest, capture, scoped
from .discovery_query import boundaries

KINDS={'REVIEW','COLLECTION','WATCH','ATTEMPT'}
WRITES={'review':'save_review','collect':'collect','watch':'save_watch','attempt':'attempt','handoff':'handoff'}


def current_source(db,app_id,app,row):
    """Never rewrite a historical snapshot when current source or review evidence changes."""
    try:
        source=capture(db,app_id,row['reference_id'],row['source_hash'])
        if source['version']!=row['source_version']:return False
        if row.get('review'):
            saved=latest(db,app_id,row['review']['id'],'REVIEW')
            if saved['hash']!=row['review']['hash'] or saved['version']!=row['review']['version']:return False
            if scoped(app,source,saved,None) is None:return False
        return True
    except (Invalid,KeyError):return False


def currentness(db,app_id,app,item):
    """Report app and source checks separately; historical status is not current approval."""
    data=item['data'];app_ok=data['manifest_version']==app['version'] and data['app_hash']==app['hash']
    rows=[data] if item['kind']=='REVIEW' else data.get('results',[])
    checks=[dict(reference_id=r['reference_id'],current=current_source(db,app_id,app,r)) for r in rows]
    return dict(current_app_context=app_ok,current_sources=checks,all_checked_sources_current=all(r['current'] for r in checks),
                freshness='RECHECK_REQUIRED_AT_HANDOFF',authority='NOT_GRANTED',boundaries=boundaries())


def read(store,app_id,body):
    """Read one immutable revision and independently assess its current context."""
    if not isinstance(body,dict):raise Invalid('Use a research read object')
    exact(body,set(body)&{'id','kind','version'})
    if not {'id','kind'}<=set(body):raise Invalid('Select research identity and kind')
    one(body['kind'],KINDS,'Research kind')
    with connection(store.path) as db:
        db.execute('BEGIN');app=app_context(db,app_id);item=latest(db,app_id,body['id'],body['kind'])
        if 'version' in body:
            count(body['version'],1,100)
            item=decoded(db.execute('SELECT * FROM discovery_documents WHERE app_id=? AND id=? AND version=?',(app_id,body['id'],body['version'])).fetchone())
            if item['kind']!=body['kind']:raise Invalid('Research kind differs')
        return dict(item,currentness=currentness(db,app_id,app,item))


def history(store,app_id,body):
    """Page summaries without loading transcripts or private research prose into a list."""
    if not isinstance(body,dict):raise Invalid('Use a research history object')
    exact(body,set(body)&{'kind','offset'})
    if 'kind' not in body:raise Invalid('Select a research history kind')
    one(body['kind'],KINDS,'Research kind');offset=count(body.get('offset',0),0,2000)
    with connection(store.path) as db:
        db.execute('BEGIN');app_context(db,app_id)
        args=(app_id,body['kind']);total=db.execute('SELECT count(*) FROM discovery_documents WHERE app_id=? AND kind=?',args).fetchone()[0]
        rows=db.execute('SELECT app_id,id,kind,version,hash,created FROM discovery_documents WHERE app_id=? AND kind=? ORDER BY rowid DESC LIMIT 100 OFFSET ?',(*args,offset)).fetchall()
        return dict(items=[dict(r) for r in rows],total=total,offset=offset,limit=100,next_offset=offset+100 if offset+100<total else None,boundaries=boundaries())


def dispatch(store,app_id,action,body):
    """The calling owner or grant gateway supplies authority; research cannot create it."""
    if action=='read':return read(store,app_id,body)
    if action=='history':return history(store,app_id,body)
    if action not in WRITES:raise Invalid('Unknown research operation')
    return getattr(Discovery(store),WRITES[action])(app_id,body)
