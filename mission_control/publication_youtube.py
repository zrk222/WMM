"""YouTube Data API resumable video upload; no implicit mutation replay."""
import re
from datetime import datetime,timezone
from .common import Invalid
from . import publication_transport as http


def _bound(draft, context):
    if draft['provider'] != 'youtube' or context.provider != 'youtube' or draft['destination_id'] != context.destination_id:
        raise Invalid('YouTube destination changed')


def _artifact(artifact):
    if not isinstance(artifact.get('raw'),bytes) or not artifact['raw'] or artifact.get('bytes')!=len(artifact['raw']):raise Invalid('Video is not eligible for the selected YouTube Short')
    if not isinstance(artifact.get('duration_seconds'),(int,float)) or not 0<artifact['duration_seconds']<=180:raise Invalid('Video is not eligible for the selected YouTube Short')
    _artifact_picture(artifact)


def _artifact_picture(artifact):
    if type(artifact.get('width')) is not int or type(artifact.get('height')) is not int or artifact['width']<=0 or artifact['height']<artifact['width']:
        raise Invalid('Video is not eligible for the selected YouTube Short')
    if artifact.get('content_type') not in ('video/mp4','video/quicktime','video/webm'):raise Invalid('Video is not eligible for the selected YouTube Short')


def _state(status, remote_id=None, session=None, observation=None):
    return dict(status=status, remote_id=remote_id, asset_id=remote_id, session=session, observation=observation or {})


def create(draft, artifact, context):
    _bound(draft,context); _artifact(artifact)
    settings=draft['settings']; description=draft['caption'] + ('\n\n'+draft['link'] if draft.get('link') else '')
    if len(description)>5000: raise Invalid('YouTube description exceeds provider limit')
    body={'snippet':{'title':draft['title'],'description':description},
          'status':{'privacyStatus':settings['privacy_status'],
                    'selfDeclaredMadeForKids':settings['self_declared_made_for_kids'],
                    'containsSyntheticMedia':settings['contains_synthetic_media']}}
    result=http.request(context,'POST','/upload/youtube/v3/videos',query={'uploadType':'resumable','part':'snippet,status'},
                        json_body=body,headers={'X-Upload-Content-Length':str(artifact['bytes']),
                                                'X-Upload-Content-Type':artifact['content_type']},response_json=False)
    url=result.headers.get('location')
    if not isinstance(url,str) or not url: raise Invalid('YouTube did not return a resumable session; effect is unknown')
    return _state('CREATED',session={'url':url,'bytes':artifact['bytes'],'offset':0},observation={'phase':'SESSION_CREATED'})


def _uploaded(result, session):
    if result.status in (200,201):
        video=result.data.get('id')
        if not isinstance(video,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',video):
            raise Invalid('YouTube upload result has no verified video ID')
        return _state('UPLOADED',video,session,{'phase':'UPLOAD_ACCEPTED'})
    if result.status != 308: raise Invalid('YouTube upload response could not be reconciled')
    value=result.headers.get('range')
    if value is None: offset=0
    else:
        match=re.fullmatch(r'bytes=0-(\d+)',value)
        if not match: raise Invalid('YouTube upload range is invalid')
        offset=int(match.group(1))+1
    if not 0<=offset<=session['bytes']: raise Invalid('YouTube upload range exceeds artifact')
    return _state('UPLOAD_IN_PROGRESS',session={**session,'offset':offset},observation={'phase':'UPLOAD_IN_PROGRESS','uploaded_bytes':offset})


def upload(draft,artifact,state,context):
    _bound(draft,context); _artifact(artifact)
    session=state.get('session') or {}; offset=session.get('offset'); total=artifact['bytes']
    if session.get('bytes')!=total or type(offset) is not int or not 0<=offset<total or not session.get('url'):
        raise Invalid('YouTube upload session requires reconciliation')
    end=min(offset+64*1024*1024,total)
    result=http.upload(context,session['url'],artifact['raw'][offset:end],content_type=artifact['content_type'],
                       content_range=f'bytes {offset}-{end-1}/{total}',expected=(200,201,308),bearer=True,response_json=True)
    return _uploaded(result,session)


def publish(draft,state,context):
    _bound(draft,context)
    if not state.get('remote_id'): raise Invalid('YouTube upload is not confirmed')
    # The approved privacy status was submitted at initialization; no second publish mutation.
    return _state('PROCESSING',state['remote_id'],state.get('session'),{'phase':'AWAITING_PROCESSING'})


def _statistics(item):
    stats=item.get('statistics')
    if stats is None:stats={}
    if not isinstance(stats,dict):raise Invalid('YouTube statistics could not be verified')
    counts={}
    for name,field in (('views','viewCount'),('likes','likeCount'),('comments','commentCount')):
        value=stats.get(field)
        if value is not None and (not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,16}',value) or int(value)>9007199254740991):raise Invalid('YouTube statistic is invalid')
        counts[name]=int(value) if value is not None else None
    return {'source':'youtube.videos.list.statistics','scope':'this_video','unit':'count','counts':counts,
            'observed_at':datetime.now(timezone.utc).isoformat(),'missing':'NOT_RETURNED'}


def _single_video(result):
    items=result.data.get('items')
    if not isinstance(items,list) or len(items)!=1 or not isinstance(items[0],dict):raise Invalid('YouTube video readback unavailable')
    return items[0]


def _checked_video(result,draft,remote):
    item=_single_video(result);snippet=item.get('snippet') or {};status=item.get('status') or {};processing=item.get('processingDetails') or {}
    if item.get('id')!=remote or snippet.get('channelId')!=draft['destination_id']:raise Invalid('YouTube video belongs to another channel')
    process=processing.get('processingStatus');privacy=status.get('privacyStatus')
    if process not in ('processing','succeeded','failed','terminated') or privacy not in ('public','unlisted','private'):
        raise Invalid('YouTube status could not be verified')
    return item,process,privacy


def _read_video(draft,remote,session,context):
    result=http.request(context,'GET','/youtube/v3/videos',query={'part':'snippet,status,processingDetails,statistics','id':remote})
    item,process,privacy=_checked_video(result,draft,remote)
    result_status='FAILED' if process in ('failed','terminated') else ('PUBLISHED' if process=='succeeded' else 'PROCESSING')
    return _state(result_status,remote,session,{'phase':'VIDEO_READ','processing_status':process,'privacy_status':privacy,
        'requested_privacy_status':draft['settings']['privacy_status'],
        'requires_attention':privacy!=draft['settings']['privacy_status'],
        'next_action':'Inspect the existing video visibility in YouTube Studio; do not upload a duplicate.' if privacy!=draft['settings']['privacy_status'] else None,
        'shorts_classification':'NOT_VERIFIED','public_visibility':'NOT_INDEPENDENTLY_VERIFIED','metrics':_statistics(item)})


def read(draft,state,context):
    _bound(draft,context); remote=state.get('remote_id');session=state.get('session') or {}
    if remote:return _read_video(draft,remote,session,context)
    if not session.get('url') or type(session.get('bytes')) is not int:raise Invalid('YouTube session is unavailable; owner reconciliation is required')
    result=http.upload(context,session['url'],b'',content_range=f"bytes */{session['bytes']}",expected=(200,201,308),bearer=True,response_json=True)
    return _uploaded(result,session)
