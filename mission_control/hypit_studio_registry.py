"""Durable session reservations; metadata never restores native execution rights."""
import json
import re
from datetime import datetime
from .common import Invalid,canonical,digest,identifier,now,required,uid
from .db import connection

MAX_APP_ACTIVE=2
MAX_STORE_ACTIVE=4
MAX_APP_HISTORY=100
MAX_STORE_HISTORY=1000
MAX_TRANSITIONS=50
NEXT={'PREPARED':('ACTIVE','UNKNOWN','CLEANUP_REQUIRED','CLOSED'),
      'ACTIVE':('CLOSING','UNKNOWN','CLEANUP_REQUIRED','CLOSED'),
      'CLOSING':('UNKNOWN','CLEANUP_REQUIRED','CLOSED'),
      'UNKNOWN':('CLEANUP_REQUIRED','CLOSED'),
      'CLEANUP_REQUIRED':('CLEANUP_REQUIRED','CLOSED'),'CLOSED':()}
CODES={'PREPARED':'RESERVED','ACTIVE':'START_CONFIRMED','CLOSING':'CLOSE_STARTED',
       'UNKNOWN':'RESULT_UNCONFIRMED','CLEANUP_REQUIRED':'CLEANUP_UNCONFIRMED','CLOSED':'STOP_CONFIRMED'}
INTENT=('manifest_version','app_hash','source_job_id','source_hash','summary_hash','installation_id')


def hashed(value):
    if type(value) is not str or re.fullmatch('[a-f0-9]{64}',value) is None:
        raise Invalid('Studio registry needs exact lowercase SHA256 references')
    return value


def startup(value):
    """Freeze only finite immutable source and execution references."""
    if type(value) is not dict or set(value)!=set(INTENT):raise Invalid('Use exact Studio reservation fields')
    if type(value['manifest_version']) is not int or value['manifest_version']<1:
        raise Invalid('Use the exact positive manifest version')
    identifier(value['source_job_id'])
    for key in ('app_hash','source_hash','summary_hash','installation_id'):hashed(value[key])
    return dict(value)


def stopped(value):
    """Validate a trusted inspector's proof envelope, not actual native liveness."""
    keys={'kind','child','worker','evidence_hash'}
    if type(value) is not dict or set(value)!=keys:raise Invalid('Confirmed cleanup proof is required')
    if value['kind'] not in ('OWNED_CLEANUP','RESTART_OBSERVATION') or value['child']!='STOPPED' or value['worker']!='STOPPED':
        raise Invalid('Both private child and worker must be confirmed stopped')
    hashed(value['evidence_hash']);return dict(value)


def event(state,version,previous,proof=None):
    value=dict(state=state,version=version,previous_hash=previous,code=CODES[state],observed_at=now(),proof=proof)
    return dict(value,hash=digest(value))


def checked(row):
    if row is None:raise Invalid('Studio session does not belong to the selected app')
    row=dict(row)
    identifier(row['app_id']);identifier(row['id'])
    if required(row['request_key'],'Studio startup request key',120)!=row['request_key']:
        raise Invalid('Studio startup retry identity changed')
    try:data=json.loads(row['data'])
    except (ValueError,TypeError):raise Invalid('Studio registry is unreadable') from None
    if digest(dict(app_id=row['app_id'],id=row['id'],request_key=row['request_key'],data=data))!=row['hash']:
        raise Invalid('Studio registry integrity changed')
    if type(data) is not dict or set(data)!={'intent','history'}:raise Invalid('Studio registry envelope changed')
    startup(data['intent']);history=data['history']
    if type(history) is not list or not 1<=len(history)<=MAX_TRANSITIONS:raise Invalid('Studio history bound changed')
    previous=None;state=None
    for index,item in enumerate(history,1):
        check_event(item,index,previous,state)
        previous=item['hash'];state=item['state']
    return dict(row,data=data)


def check_event(item,index,previous,state):
    keys={'state','version','previous_hash','code','observed_at','proof','hash'}
    if type(item) is not dict or set(item)!=keys:raise Invalid('Studio transition shape changed')
    if item['hash']!=digest({k:v for k,v in item.items() if k!='hash'}):raise Invalid('Studio transition hash changed')
    if type(item['version']) is not int or item['version']!=index or item['previous_hash']!=previous:
        raise Invalid('Studio transition chain changed')
    try:stamp=datetime.fromisoformat(item['observed_at'])
    except (TypeError,ValueError):raise Invalid('Studio transition timestamp changed') from None
    if stamp.tzinfo is None:raise Invalid('Studio transition timestamp needs a timezone')
    allowed=('PREPARED',) if state is None else NEXT[state]
    if item['state'] not in allowed or item['code']!=CODES[item['state']]:raise Invalid('Studio transition is illegal')
    if item['state']=='CLOSED':stopped(item['proof'])
    elif item['proof'] is not None:raise Invalid('Only stopped-resource evidence belongs in terminal cleanup')


def rows(db):
    """Validate every capacity-bearing record before computing datastore ceilings."""
    saved=db.execute('SELECT * FROM studio_sessions LIMIT ?',(MAX_STORE_HISTORY+1,)).fetchall()
    if len(saved)>MAX_STORE_HISTORY:raise Invalid('Studio registry exceeds its retained history bound')
    return [checked(row) for row in saved]


def public(row,launch=False):
    last=row['data']['history'][-1]
    return dict(app_id=row['app_id'],id=row['id'],version=last['version'],state=last['state'],
        intent=dict(row['data']['intent']),history=row['data']['history'],launch_allowed=launch,
        capacity_reserved=last['state']!='CLOSED',live_ownership='NOT_ESTABLISHED_BY_REGISTRY',
        inspection_required=last['state']!='CLOSED')


def persist(db,row):
    data=row['data'];encoded=canonical(data)
    checksum=digest(dict(app_id=row['app_id'],id=row['id'],request_key=row['request_key'],data=data))
    db.execute('INSERT INTO studio_sessions VALUES(?,?,?,?,?) ON CONFLICT(app_id,id) DO UPDATE SET data=excluded.data,hash=excluded.hash',
        (row['app_id'],row['id'],row['request_key'],encoded,checksum))
    return dict(row,hash=checksum)


def capacity(saved,app_id):
    own=[r for r in saved if r['app_id']==app_id]
    active=[r for r in saved if r['data']['history'][-1]['state']!='CLOSED']
    if len(own)>=MAX_APP_HISTORY or len(saved)>=MAX_STORE_HISTORY:raise Invalid('Studio retained history is full')
    if len(active)>=MAX_STORE_ACTIVE or sum(r['app_id']==app_id for r in active)>=MAX_APP_ACTIVE:
        raise Invalid('Studio unresolved session capacity is full; inspect and confirm cleanup')


class Registry:
    def __init__(self,store):self.store=store

    def reserve(self,app_id,request_key,intent):
        """Return one launch permission only after immutable startup intent commits."""
        intent=startup(intent);key=required(request_key,'Studio startup request key',120)
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');saved=rows(db)
            old=next((r for r in saved if r['app_id']==app_id and r['request_key']==key),None)
            if old:
                if old['data']['intent']!=intent:raise Invalid('Startup retry input changed')
                return public(old)
            app=db.execute('SELECT version,data FROM apps WHERE id=?',(app_id,)).fetchone()
            if app is None or app['version']!=intent['manifest_version'] or digest(json.loads(app['data']))!=intent['app_hash']:
                raise Invalid('Startup manifest changed')
            capacity(saved,app_id)
            row=dict(app_id=app_id,id=uid(),request_key=key,data=dict(intent=intent,history=[event('PREPARED',1,None)]))
            return public(persist(db,row),True)

    def read(self,app_id,identity):
        with connection(self.store.path) as db:
            row=checked(db.execute('SELECT * FROM studio_sessions WHERE app_id=? AND id=?',(app_id,identity)).fetchone())
            return public(row)

    def list(self,app_id):
        self.store.app(app_id)
        with connection(self.store.path) as db:
            return [public(r) for r in rows(db) if r['app_id']==app_id]

    def transition(self,app_id,identity,version,state,proof=None):
        """Internal caller establishes actual ownership/proof; no native effects here."""
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=checked(db.execute('SELECT * FROM studio_sessions WHERE app_id=? AND id=?',(app_id,identity)).fetchone())
            history=row['data']['history'];last=history[-1]
            if type(version) is not int or version!=last['version']:raise Invalid('Studio registry revision changed')
            if type(state) is not str or state not in NEXT[last['state']]:raise Invalid('Studio transition is illegal')
            if len(history)>=MAX_TRANSITIONS:raise Invalid('Studio transition history is full')
            if len(history)==MAX_TRANSITIONS-1 and state!='CLOSED':raise Invalid('Final Studio transition is reserved for cleanup')
            if state=='CLOSED':proof=stopped(proof)
            elif proof is not None:raise Invalid('Unexpected Studio transition proof')
            history.append(event(state,version+1,last['hash'],proof))
            return public(persist(db,row))
