"""Immutable, app-scoped research evidence. Prepared packets never authorize execution."""
import sqlite3
import json
from datetime import datetime, timezone
from .common import Invalid, canonical, digest, identifier, iso_time, safe_data
from .db import connection
from .pmf_contract import count, exact, hashed, one
from .funnel_store import app_context
from .creative_library import latest_capture
from . import discovery_contract as contract
from .discovery_query import boundaries, evaluate, ordered, coverage, qualification


def decoded(row):
    """Read back exactly the immutable bytes that were reviewed."""
    if row is None:raise Invalid('Research document does not belong to this app')
    result=dict(row);result['data']=json.loads(result['data'])
    if digest(result['data'])!=result['hash']:raise Invalid('Research document integrity changed')
    return result


def latest(db, app_id, identity, kind):
    """Resolve a current app-owned revision without crossing document kinds."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    row=db.execute('SELECT * FROM discovery_documents WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1',(app_id,identifier(identity))).fetchone()
    result=decoded(row)
    if result['kind']!=kind:raise Invalid('Research document kind differs')
    return result


def append(db, app_id, identity, expected, kind, data, stamp):
    """Bound append-only history and reject stale writers inside their transaction."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    identity=identifier(identity);count(expected,0,99);safe_data(data)
    row=db.execute('SELECT version,kind FROM discovery_documents WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1',(app_id,identity)).fetchone()
    if (row['version'] if row else 0)!=expected:raise Invalid('Research revision changed; reload before saving')
    if row and row['kind']!=kind:raise Invalid('Research identity already has another kind')
    total=db.execute('SELECT count(*) FROM discovery_documents WHERE app_id=?',(app_id,)).fetchone()[0]
    if total>=2000:raise Invalid('Research history limit is 2000 documents per app')
    db.execute('INSERT INTO discovery_documents VALUES(?,?,?,?,?,?,?)',(app_id,identity,expected+1,kind,canonical(data),digest(data),stamp))
    db.execute('INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)',(app_id,'discovery.'+kind.lower(),canonical(dict(id=identity,version=expected+1,hash=digest(data))),stamp))
    return latest(db,app_id,identity,kind)


def capture(db, app_id, ref, expected=None):
    """Only current immutable source bytes may be attached to new research evidence."""
    result=latest_capture(db,app_id,ref)
    if digest(result['data'])!=result['hash'] or (expected is not None and result['hash']!=hashed(expected)):raise Invalid('Source capture hash changed')
    return result


def scoped(app, source, review, stamp):
    """Old app or source reviews remain in history but cannot drive a current decision."""
    if review is None:return None
    data=review['data']
    if data['manifest_version']!=app['version'] or data['app_hash']!=app['hash']:return None
    if data['source_hash']!=source['hash'] or data['source_version']!=source['version']:return None
    return data['review']


def review_times(data, source, stamp):
    """Reject future transcripts and mixed-time metrics that would invent comparability."""
    published=source['data']['published_at']
    for item in (data['transcript'],data['metrics']):
        if item and not (iso_time(published) if published else iso_time(source['data']['captured_at']))<=iso_time(item['observed_at'])<=iso_time(stamp):
            raise Invalid('Review observation chronology is invalid')
    metrics=data['metrics'];facts=source['data']
    if metrics and (facts['metric_kind']!='VIEWS' or facts['metric_value']!=metrics['views'] or facts['metric_at'] is None or iso_time(facts['metric_at'])!=iso_time(metrics['observed_at'])):
        raise Invalid('Engagement counts must share the source view observation')
    qualification(facts,data,stamp)


def reviews(db, app_id):
    """Choose the newest review per reference, retaining only exact app/source bindings later."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    result={}
    for row in db.execute("SELECT * FROM discovery_documents WHERE app_id=? AND kind='REVIEW' ORDER BY rowid",(app_id,)):
        item=decoded(row);result[item['data']['reference_id']]=item
    return result


def source_results(db, app_id, app, filters, stamp):
    """Inspect at most 1000 saved references once and freeze each reasoned decision."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    refs=db.execute('SELECT id FROM creative_references WHERE app_id=? ORDER BY identity LIMIT 1001',(app_id,)).fetchall()
    if len(refs)>1000:raise Invalid('Research supports at most 1000 sources')
    reviewed=reviews(db,app_id);result=[]
    for ref in refs:
        source=capture(db,app_id,ref['id']);item=reviewed.get(ref['id']);value=scoped(app,source,item,stamp)
        previous=db.execute('SELECT data FROM creative_captures WHERE app_id=? AND reference_id=? AND version<? ORDER BY version DESC LIMIT 1',(app_id,ref['id'],source['version'])).fetchone()
        decision=evaluate(source,value,filters,stamp,json.loads(previous['data']) if previous else None)
        decision['review']=dict(id=item['id'],hash=item['hash'],version=item['version']) if value else None
        result.append(decision)
    return ordered(result,filters['ranking'])


def collection_state(results, failed):
    """Empty, stale, partial and failed are visible states rather than success substitutes."""
    if not results:return 'FAILED' if failed else 'EMPTY'
    if all('OBSERVATION_STALE_OR_FUTURE' in row['reasons'] for row in results):return 'STALE'
    return 'PARTIAL' if failed else 'OBSERVED'


def authentic_proofs(db, store, app_id, ids, app):
    """Reuse native authentic-scene verification; freeze exact app-owned asset hashes."""
    from .creative_briefs import bound_record, asset_checked
    if not ids:raise Invalid('Select authentic app proof before preparing a production handoff')
    result=[]
    for identity in ids:
        record=bound_record(db,app_id,identity,'asset',app['data']);asset_checked(store,app_id,record['data'])
        if digest(dict(kind=record['kind'],data=record['data'],source=record['source']))!=record['hash']:raise Invalid('Authentic app evidence integrity changed')
        result.append(dict(id=identity,version=record['version'],hash=record['hash']))
    return result


def source_outcomes(rows):
    """Validate unique source-level read outcomes without inventing collector execution."""
    seen=set()
    for row in contract.items(rows,1000,'Source outcomes'):
        exact(row,{'source','status','detail'});source=contract.texts([row['source']],1,2000,'Source')[0]
        if source in seen:raise Invalid('Duplicate collection outcome source')
        seen.add(source);one(row['status'],{'OBSERVED','FAILED','EMPTY','STALE'},'Read status');contract.texts([row['detail']],1,2000,'Read detail')
    return seen


def selected_review(db, app_id, app, saved, body, stamp):
    """Resolve exactly the collection-selected source and review in one SQL transaction."""
    if saved['hash']!=hashed(body['collection_hash']) or saved['data']['app_hash']!=app['hash'] or saved['data']['manifest_version']!=app['version']:raise Invalid('Collection or app changed')
    selected=[r for r in saved['data']['results'] if r['reference_id']==body['reference_id']]
    if not selected or not selected[0]['included'] or not selected[0]['review']:raise Invalid('Select an included reviewed research candidate')
    frozen=selected[0];source=capture(db,app_id,body['reference_id'],frozen['source_hash']);review=latest(db,app_id,frozen['review']['id'],'REVIEW')
    if source['version']!=frozen['source_version']:raise Invalid('Source capture version changed')
    if review['hash']!=hashed(body['review_hash']) or review['hash']!=frozen['review']['hash']:raise Invalid('Review changed after collection')
    return source,review


class Discovery:
    """Local research service; HTTP/UI/CLI adapters must retain their exact authority gates."""
    def __init__(self,store,clock=None):self.store=store;self.clock=clock or (lambda:datetime.now(timezone.utc))

    def save_review(self,app_id,body):
        """Save separate observations and interpretations against exact current app/source bytes."""
        exact(body,{'id','version','manifest_version','reference_id','source_hash','data'});value=contract.review(body['data']);stamp=self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app=app_context(db,app_id,body['manifest_version']);source=capture(db,app_id,body['reference_id'],body['source_hash'])
            if body['version']:
                prior=latest(db,app_id,body['id'],'REVIEW')
                if prior['data']['reference_id']!=body['reference_id']:raise Invalid('A review identity cannot change source')
            review_times(value,source,stamp)
            data=dict(manifest_version=app['version'],app_hash=app['hash'],reference_id=body['reference_id'],source_hash=source['hash'],source_version=source['version'],review=value,boundaries=boundaries())
            return append(db,app_id,body['id'],body['version'],'REVIEW',data,stamp)

    def collect(self,app_id,body):
        """Snapshot only permitted locally saved sources; this method never initiates a read."""
        exact(body,{'id','version','manifest_version','query','attempted_sources','failed_sources'})
        filters=contract.query(body['query']);attempted=count(body['attempted_sources'],0,1000);failed=count(body['failed_sources'],0,attempted);stamp=self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app=app_context(db,app_id,body['manifest_version']);results=source_results(db,app_id,app,filters,stamp)
            data=dict(manifest_version=app['version'],app_hash=app['hash'],query=filters,observed_at=stamp,results=results,
                      state=collection_state(results,failed),coverage=coverage(results,attempted,failed),boundaries=boundaries(),collection_provenance='OPERATOR_REPORTED_READ_COVERAGE')
            return append(db,app_id,body['id'],body['version'],'COLLECTION',data,stamp)

    def read(self,app_id,identity,kind,version=None):
        """Historical content is immutable; currentness is returned separately."""
        with connection(self.store.path) as db:
            app=app_context(db,app_id);item=latest(db,app_id,identity,kind)
            if version is not None:
                count(version,1,100);item=decoded(db.execute('SELECT * FROM discovery_documents WHERE app_id=? AND id=? AND version=?',(app_id,identity,version)).fetchone())
                if item['kind']!=kind:raise Invalid('Research document kind differs')
            current=item['data']['app_hash']==app['hash'] and item['data']['manifest_version']==app['version']
            return dict(item,current_app_context=current,boundaries=boundaries())

    def save_watch(self,app_id,body):
        """Persist authorized collection intent; scheduling is explicitly not activated here."""
        exact(body,{'id','version','manifest_version','data'});value=contract.watch(body['data']);stamp=self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app=app_context(db,app_id,body['manifest_version'])
            data=dict(manifest_version=app['version'],app_hash=app['hash'],definition=value,schedule='NOT_ACTIVATED',boundaries=boundaries())
            return append(db,app_id,body['id'],body['version'],'WATCH',data,stamp)

    def attempt(self,app_id,body):
        """Append exact source-level outcomes without treating a supplied report as an actual read."""
        exact(body,{'id','manifest_version','watch_id','watch_hash','collection_id','collection_hash','source_results'})
        rows=body['source_results'];seen=source_outcomes(rows);stamp=self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app=app_context(db,app_id,body['manifest_version'])
            watch=latest(db,app_id,body['watch_id'],'WATCH');collection=latest(db,app_id,body['collection_id'],'COLLECTION')
            if watch['hash']!=hashed(body['watch_hash']) or collection['hash']!=hashed(body['collection_hash']):raise Invalid('Watch or collection changed')
            for item in (watch,collection):
                if item['data']['app_hash']!=app['hash'] or item['data']['manifest_version']!=app['version']:raise Invalid('Research app context changed')
            if watch['data']['definition']['query']!=collection['data']['query']:raise Invalid('Collection query differs from watch')
            if not seen.issubset(set(watch['data']['definition']['subjects'])):raise Invalid('Read outcomes must name selected watch subjects')
            data=dict(manifest_version=app['version'],app_hash=app['hash'],watch_id=watch['id'],watch_hash=watch['hash'],collection_id=collection['id'],collection_hash=collection['hash'],source_results=rows,provenance='OPERATOR_REPORTED_NOT_INDEPENDENTLY_VERIFIED',observed_at=stamp,boundaries=boundaries())
            return append(db,app_id,body['id'],0,'ATTEMPT',data,stamp)

    def handoff(self,app_id,body):
        """Prepare exact evidence for existing brief/editor controls, without approving any action."""
        exact(body,{'manifest_version','collection_id','collection_hash','reference_id','review_hash'});stamp=self.clock().isoformat()
        with connection(self.store.path) as db:
            db.execute('BEGIN IMMEDIATE');app=app_context(db,app_id,body['manifest_version']);saved=latest(db,app_id,body['collection_id'],'COLLECTION')
            source,review=selected_review(db,app_id,app,saved,body,stamp)
            value=scoped(app,source,review,stamp)
            if value is None:raise Invalid('Review app or source context changed')
            decision=evaluate(source,value,saved['data']['query'],stamp)
            if not decision['included'] or decision['rights_missing']:raise Invalid('Fresh eligibility and explicit rights evidence are required')
            proof=authentic_proofs(db,self.store,app_id,value['card']['authentic_evidence_ids'],app)
            data=dict(schema='wmm.discovery-handoff.v1',manifest_version=app['version'],app_hash=app['hash'],collection_hash=saved['hash'],
                      reference_id=body['reference_id'],source_hash=source['hash'],review_hash=review['hash'],card=value['card'],authentic_proofs=proof,
                      policy=decision['policy'],state='PREPARED',boundaries=boundaries())
            return dict(data,packet_hash=digest(data))
