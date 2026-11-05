"""Fresh owner adoption of a reported discovery candidate into native research."""
import json
from datetime import datetime, timezone

from .common import Invalid, canonical, digest, iso_time, now, safe_data, uid
from .db import connection
from .operation_authority import PROTECTED, check, store_identity
from .organic_video_discovery import exact, qualify_submission
from .organic_video_collector import _row as task_row, _view as task_view
from .funnel_store import app_context
from .creative_library import reference_data, write_reference, latest_capture
from .creative_analysis import analysis_data, append as append_analysis, latest as latest_analysis
from .discovery_contract import review as review_data, query as query_data
from .discovery_query import evaluate, boundaries, coverage
from .discovery_store import append as append_discovery, latest as latest_discovery, review_times, authentic_proofs


def _schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS organic_video_intakes (
        id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), request_id TEXT NOT NULL,
        request_hash TEXT NOT NULL, data TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL,
        UNIQUE(app_id,request_id))''')
    for action in ('UPDATE','DELETE'):
        db.execute(f'''CREATE TRIGGER IF NOT EXISTS organic_video_intakes_no_{action.lower()}
            BEFORE {action} ON organic_video_intakes BEGIN SELECT RAISE(ABORT,'Intake history is immutable'); END''')
    db.execute('''CREATE TRIGGER IF NOT EXISTS organic_video_intakes_no_replace BEFORE INSERT ON organic_video_intakes
        WHEN EXISTS(SELECT 1 FROM organic_video_intakes WHERE id=NEW.id OR (app_id=NEW.app_id AND request_id=NEW.request_id) OR rowid=NEW.rowid)
        BEGIN SELECT RAISE(ABORT,'Intake history is immutable'); END''')


def _identity(db,store,app_id,actor,body):
    context=PROTECTED.get()
    if (not context or 'grant_id' in context or context.get('store')!=store_identity(store)
            or context.get('envelope')!=canonical(dict(app_id=app_id,operation='organic-video.intake',input=body))
            or check(db,context)!=actor):raise PermissionError('Fresh exact protected owner intake is required')
    return context


def _view(row):
    data=json.loads(row['data'])
    if digest(data)!=row['hash']:raise Invalid('Intake receipt integrity changed')
    return dict(id=row['id'],hash=row['hash'],data=data)


def _current_outputs(db,app_id,data):
    source=latest_capture(db,app_id,data['source']['id'])
    if (source['version'],source['hash'])!=(data['source']['version'],data['source']['hash']):raise Invalid('Intake source changed')
    for key,kind in (('review','REVIEW'),('collection','COLLECTION')):
        item=latest_discovery(db,app_id,data[key]['id'],kind)
        if (item['version'],item['hash'])!=(data[key]['version'],data[key]['hash']):raise Invalid('Intake research changed')
    item=latest_analysis(db,'creative_analyses',app_id,data['analysis']['id'])
    if (item['version'],item['hash'])!=(data['analysis']['version'],data['analysis']['hash']):raise Invalid('Intake analysis changed')


def adopt(store,app_id,actor,body):
    """Atomically adopt reported observations; no provider or publication effect occurs."""
    fields=('request_id','task_id','task_hash','submission_hash','result_hash','candidate_id','candidate_hash',
            'source_metadata','review','analysis','query')
    exact(body,fields);safe_data(body)
    if not isinstance(body['request_id'],str) or not 1<=len(body['request_id'])<=120:raise Invalid('Use a bounded intake request identity')
    stamp=now()
    with connection(store.path) as db:
        db.execute('BEGIN IMMEDIATE');context=_identity(db,store,app_id,actor,body);_schema(db)
        row=task_row(db,app_id,body['task_id']);view=task_view(row)
        if row['owner']!=actor:raise PermissionError('Only the task owner may adopt reported research')
        if row['status']!='SUBMITTED' or any(row[key]!=body[key] for key in ('task_hash','submission_hash','result_hash')):
            raise Invalid('Use the exact completed discovery submission')
        app=app_context(db,app_id)
        if (app['version'],app['hash'])!=(view['task']['app']['version'],view['task']['app']['hash']):raise Invalid('Discovery app context changed')
        submission=json.loads(row['submission']);qualified=qualify_submission(view['task'],submission)
        if digest(qualified)!=row['result_hash']:raise Invalid('Discovery qualification changed')
        matches=[item for item in submission['candidates'] if item['candidate']['post_id']==body['candidate_id']]
        if len(matches)!=1 or digest(matches[0]['candidate'])!=body['candidate_hash']:raise Invalid('Select the exact submitted candidate')
        candidate=matches[0];selected=[x for x in qualified['items'] if x['candidate_id']==body['candidate_id']]
        if len(selected)!=1 or selected[0]['status']!='COLLECTION_REVIEW_REQUIRED':raise Invalid('Select a qualified relevant research candidate')
        if not 0<=(iso_time(stamp)-iso_time(candidate['candidate']['observed_at'])).total_seconds()<=86400:raise Invalid('Submitted candidate is stale')
        prior=db.execute('SELECT * FROM organic_video_intakes WHERE app_id=? AND request_id=?',(app_id,body['request_id'])).fetchone()
        if prior:
            if prior['request_hash']!=digest(body):raise Invalid('Intake request identity was used for different input')
            result=_view(prior);_current_outputs(db,app_id,result['data']);_identity(db,store,app_id,actor,body);return result
        meta=body['source_metadata'];exact(meta,('title','locale','traffic_class','topic','relevance_note','permission_confirmed'))
        obs=candidate['candidate']
        source=reference_data(dict(meta,platform=obs['platform'],post_id=obs['post_id'],creator_id=obs['creator_id'],format=obs['format'],url=obs['url'],
            source='EXTERNAL_AGENT_REPORTED_NOT_INDEPENDENTLY_VERIFIED',captured_at=obs['observed_at'],published_at=obs['published_at'],
            metric_kind='VIEWS',metric_value=obs['views'],metric_at=obs['observed_at'],rights='REFERENCE_ONLY'))
        source_id=write_reference(db,app_id,source)['id'];capture=latest_capture(db,app_id,source_id)
        review=body['review'];exact(review,('taxonomy','duration_ms','transcript','card','metrics'))
        review=review_data(dict(review,baseline=candidate['history']))
        if review['card']['authentic_evidence_ids']:
            authentic_proofs(db,store,app_id,review['card']['authentic_evidence_ids'],app)
        review_times(review,capture,stamp)
        review_envelope=dict(manifest_version=app['version'],app_hash=app['hash'],reference_id=source_id,
            source_hash=capture['hash'],source_version=capture['version'],review=review,boundaries=boundaries())
        saved_review=append_discovery(db,app_id,uid(),0,'REVIEW',review_envelope,stamp)
        query=query_data(body['query']);decision=evaluate(capture,review,query,stamp)
        if decision['qualified'] is not True or decision['included'] is not True:raise Invalid('Reviewed candidate is not current and qualified for this query')
        decision['review']=dict(id=saved_review['id'],version=saved_review['version'],hash=saved_review['hash'])
        identity_id=uid()
        provenance=dict(intake_id=identity_id,task_id=row['id'],task_hash=row['task_hash'],submission_hash=row['submission_hash'],result_hash=row['result_hash'],
            candidate_hash=body['candidate_hash'],baseline_hash=digest(candidate['history']),evidence_hash=digest(candidate['evidence']),
            observation_receipt_hashes=[digest(item) for item in candidate['evidence']],owner=actor,owner_version=context['role_version'],
            classification='EXTERNAL_AGENT_REPORTED_NOT_INDEPENDENTLY_VERIFIED')
        collection=dict(manifest_version=app['version'],app_hash=app['hash'],query=query,observed_at=stamp,results=[decision],state='OBSERVED',
            coverage=coverage([decision],1,0),boundaries=boundaries(),collection_provenance=provenance)
        saved_collection=append_discovery(db,app_id,uid(),0,'COLLECTION',collection,stamp)
        analysis=body['analysis'];exact(analysis,('inspection_kind','inspection_confirmed','inspected_at','analyst','format_family','duration_seconds','observations','uncertainty'))
        analysis=analysis_data(dict(analysis,reference_id=source_id,capture_hash=capture['hash']),capture)
        if db.execute("SELECT 1 FROM creative_analyses WHERE app_id=? AND json_extract(data,'$.reference_id')=?",(app_id,source_id)).fetchone():
            raise Invalid('Source already has an inspection; review its existing history before intake')
        saved_analysis=append_analysis(db,'creative_analyses',app_id,analysis,{})
        def identity(item,key='id'):return dict(id=item[key],version=item['version'],hash=item['hash'])
        result=dict(schema='wmm.organic-video-intake.v1',provenance=provenance,source=identity(capture,'reference_id'),
                    review=identity(saved_review),collection=identity(saved_collection),analysis=identity(saved_analysis),
                    foreign_bytes='NOT_AUTHORIZED',publication='NOT_RUN')
        db.execute('INSERT INTO organic_video_intakes VALUES(?,?,?,?,?,?,?)',(identity_id,app_id,body['request_id'],digest(body),canonical(result),digest(result),stamp))
        _identity(db,store,app_id,actor,body)
        return _view(db.execute('SELECT * FROM organic_video_intakes WHERE id=?',(identity_id,)).fetchone())
