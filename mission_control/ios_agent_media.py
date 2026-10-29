"""Agent-only native scene operations and render authority provenance."""
import json
from datetime import datetime, timezone

from .common import Invalid, canonical, digest, now, required
from .db import connection


def record_authority(db, app_id, kind, job_id):
    from .operation_authority import REQUEST
    context=REQUEST.get()
    if not context or 'grant_id' not in context:raise PermissionError('Admitted agent authority is required')
    if context.get('execution_id') is not None:
        raise PermissionError('Standing media execution requires a dedicated native lifecycle binding')
    values=(app_id,kind,job_id,context['grant_id'],context['grant_version'],context['envelope'],
            canonical(context['review']) if context['review'] else None)
    old=db.execute('SELECT * FROM ios_agent_media_authority WHERE app_id=? AND kind=? AND job_id=?',(app_id,kind,job_id)).fetchone()
    if old:
        actual=tuple(old[k] for k in ('app_id','kind','job_id','grant_id','grant_version','envelope','review'))
        if actual!=values:raise PermissionError('Render belongs to a different agent admission')
    else:
        db.execute('INSERT INTO ios_agent_media_authority VALUES(?,?,?,?,?,?,?)',values)


def check_authority(db, app_id, kind, job_id):
    """Recheck current grant and completed exact independent review, if required."""
    from .agent_grants import current as grant_current
    from .agent_review_policy import ordinary_dispatch
    from .agent_checkpoints import current as checkpoint_current,read_row
    from .agent_review_dispatch import saved_request
    row=db.execute('SELECT * FROM ios_agent_media_authority WHERE app_id=? AND kind=? AND job_id=?',(app_id,kind,job_id)).fetchone()
    if row is None:
        if kind=='timeline':raise PermissionError('Agent render authority is unavailable')
        return  # Ordinary owner-created scene media has no agent provenance.
    envelope=json.loads(row['envelope']);grant=db.execute('SELECT * FROM agent_grants WHERE id=?',(row['grant_id'],)).fetchone()
    if not grant or grant['version']!=row['grant_version']:raise PermissionError('Agent render grant changed')
    observed=datetime.now(timezone.utc)
    grant_current(db,grant,envelope,observed,check_quota=False)
    if not row['review']:
        ordinary_dispatch(db,grant['id'],envelope['operation']);return
    review=json.loads(row['review']);request=saved_request(db,app_id,review['id']);checkpoint=read_row(db,app_id,review['id'])
    if (request['grant_id']!=grant['id'] or request['input_hash']!=review['input_hash']
            or canonical(request['envelope'])!=row['envelope'] or checkpoint['state']!='SUCCEEDED'
            or checkpoint['hash']!=review['packet_hash'] or checkpoint['packet']['input_hash']!=request['input_hash']
            or checkpoint['packet']['agent_id']!=grant['agent_id']):
        raise PermissionError('Agent render review is no longer current')
    checkpoint_current(db,checkpoint,observed)


def dispatch_scene(service,envelope):
    """Run the shared scene transaction inside admitted agent protection."""
    from .ios_studio import NativeStudio
    from .operation_authority import REQUEST
    context=REQUEST.get()
    if not context or 'grant_id' not in context or not callable(context.get('host_check')):
        raise PermissionError('An admitted native owner and agent authority are required')
    action=envelope['operation'].removeprefix('ios.scene.')
    if action not in ('projects','read','save','plan','start','inspect','cancel'):
        raise Invalid('Choose a native scene operation')
    with connection(service.store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        grant=db.execute('SELECT owner FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
        if not grant:raise PermissionError('Agent grant is unavailable')
        if action=='start':
            old=db.execute('SELECT id FROM ios_studio_jobs WHERE app_id=? AND request_key=?',
                           (envelope['app_id'],envelope['input']['request_key'])).fetchone()
            if old:
                origin=db.execute('SELECT grant_id FROM ios_agent_media_authority WHERE app_id=? AND kind=? AND job_id=?',
                                  (envelope['app_id'],'scene',old['id'])).fetchone()
                if not origin or origin['grant_id']!=context['grant_id']:
                    raise PermissionError('An agent cannot adopt another render')
        if action in ('inspect','cancel'):
            origin=db.execute('SELECT grant_id FROM ios_agent_media_authority WHERE app_id=? AND kind=? AND job_id=?',
                              (envelope['app_id'],'scene',envelope['input']['job_id'])).fetchone()
            if origin is None or origin['grant_id']!=context['grant_id']:
                raise PermissionError('Use the originating grant for this native render')
        result=NativeStudio(service,None)._dispatch(db,envelope['app_id'],grant['owner'],action,envelope['input'],None)
        if action=='start':record_authority(db,envelope['app_id'],'scene',result['job']['job_id'])
        if action=='projects':
            result['projects']=[{k:v for k,v in row.items() if k!='scene'} for row in result['projects']]
        return result


def timeline_packet(service,app_id,body):
    from .ios_production import NativeProduction
    from .ios_render_plan import compile_plan
    project=NativeProduction(service,None)._current(app_id,body['project_id'],body['revision'],body['project_hash'])
    packet=dict(schema='growth.ios-production-packet.v1',app_id=app_id,
                manifest_version=project['data']['manifest_version'],project_id=body['project_id'],
                revision=body['revision'],project_hash=body['project_hash'],
                plan=compile_plan(project['data']['definition']),status='PREPARED_NOT_RENDERED',execution_authority=False)
    return dict(packet,packet_hash=digest(packet))


def timeline_row(db,app_id,owner,job_id):
    from uuid import UUID
    try:
        if str(UUID(job_id))!=job_id:raise ValueError()
    except (ValueError,TypeError,AttributeError):raise Invalid('Choose a valid native timeline job') from None
    row=db.execute('SELECT * FROM ios_agent_timeline_jobs WHERE app_id=? AND id=?',(app_id,job_id)).fetchone()
    if not row or row['owner']!=owner:raise PermissionError('Native timeline job is unavailable to this owner')
    return row


def timeline_public(row):
    packet=json.loads(row['packet'])
    return dict(job_id=row['id'],project_id=packet['project_id'],revision=packet['revision'],
                project_hash=packet['project_hash'],packet_hash=row['packet_hash'],status=row['status'],
                result=json.loads(row['result']) if row['result'] else None)


def expected_timeline_audio(db,store,app_id,packet):
    """Resolve audio only from verified app-owned source metadata, not output claims."""
    from .creative_rendering import artifact_file
    from .managed_media_store import derivative_snapshot
    from .video_edit_projects import source_binding
    for clip in packet['plan']['clips']:
        if clip['audio']!='RETAIN':continue
        source=clip['source'];binding=source_binding(db,store,app_id,source)
        if binding['sha256']!=source['sha256']:raise Invalid('Timeline source hash changed')
        if source['kind']=='MANAGED':
            metadata=derivative_snapshot(db,store,app_id,source['id'],source['sha256'])[0]['metadata']
        elif source['kind']=='NATIVE':
            metadata=artifact_file(store,app_id,source['id'])[1]['artifact']['metadata']
        else:raise Invalid('Unsupported native timeline source')
        if type(metadata.get('audio')) is not bool:raise Invalid('Timeline source audio evidence is unavailable')
        if metadata['audio']:return True
    return False


def dispatch_timeline(service,envelope):
    from uuid import uuid4
    from .operation_authority import REQUEST
    context=REQUEST.get()
    if not context or 'grant_id' not in context or not callable(context.get('host_check')):
        raise PermissionError('An admitted native owner and agent authority are required')
    action=envelope['operation'].removeprefix('ios.timeline.');body=envelope['input'];app=envelope['app_id']
    if action not in ('queue','inspect','cancel'):raise Invalid('Choose a native timeline operation')
    with connection(service.store.path) as db:
        db.execute('BEGIN IMMEDIATE')
        grant=db.execute('SELECT owner FROM agent_grants WHERE id=?',(context['grant_id'],)).fetchone()
        if not grant:raise PermissionError('Agent grant is unavailable')
        if action=='queue':
            required(body['request_key'],'Request key',100)
            packet=timeline_packet(service,app,body);request_hash=digest(body)
            row=db.execute('SELECT * FROM ios_agent_timeline_jobs WHERE app_id=? AND request_key=?',(app,body['request_key'])).fetchone()
            if row:
                if row['request_hash']!=request_hash or row['owner']!=grant['owner'] or row['packet_hash']!=packet['packet_hash']:
                    raise Invalid('Request key belongs to another native timeline')
            else:
                stamp=now();identity=str(uuid4())
                db.execute('INSERT INTO ios_agent_timeline_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (app,identity,grant['owner'],body['request_key'],request_hash,canonical(packet),packet['packet_hash'],
                            'PREPARED',None,stamp,stamp))
                row=timeline_row(db,app,grant['owner'],identity)
            record_authority(db,app,'timeline',row['id'])
            return {'job':timeline_public(row),'packet':packet}
        row=timeline_row(db,app,grant['owner'],body['job_id'])
        origin=db.execute('SELECT grant_id FROM ios_agent_media_authority WHERE app_id=? AND kind=? AND job_id=?',(app,'timeline',row['id'])).fetchone()
        if not origin or origin['grant_id']!=context['grant_id']:raise PermissionError('Use the originating grant for this native render')
        if action=='cancel':
            if row['status']=='PREPARED':
                db.execute("UPDATE ios_agent_timeline_jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=?",(now(),app,row['id']))
            elif row['status']!='CANCELLED':raise Invalid('Completed render cannot be cancelled')
            row=timeline_row(db,app,grant['owner'],row['id'])
        return timeline_public(row)


class NativeAgentTimeline:
    """Trusted host-only timeline controls; no model-supplied decoder evidence."""
    def __init__(self,service,identities):self.service=service;self.identities=identities

    def call(self,session,app_id,action,payload,*,inspection=None):
        from .ios_bridge import decode_document,encode_response
        from .operation_authority import bound_owner,protected
        body=decode_document(payload)
        fields={'history':set(),'artifact':{'job_id'},'inspect':{'job_id'},'validate':{'job_id','packet_hash'},'cancel':{'job_id'},'finish':{'job_id','packet_hash'}}
        if action not in fields or not isinstance(body,dict) or set(body)!=fields[action] or ((action=='finish')!=(inspection is not None)):
            raise Invalid('Use an exact trusted native timeline action')
        user=self.identities.fresh(session);envelope=dict(app_id=app_id,operation='native.agent-timeline.'+action,input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                with connection(self.service.store.path) as db:
                    db.execute('BEGIN IMMEDIATE')
                    if action=='history':
                        rows=db.execute('SELECT * FROM ios_agent_timeline_jobs WHERE app_id=? AND owner=? ORDER BY created DESC,id DESC LIMIT 100',
                                        (app_id,user['principal'])).fetchall()
                        return encode_response({'items':[timeline_public(row) for row in rows]})
                    row=timeline_row(db,app_id,user['principal'],body['job_id'])
                    if action=='inspect':return encode_response(timeline_public(row))
                    if action=='artifact':
                        if row['status']!='SUCCEEDED' or row['result'] is None:raise Invalid('This render has no verified output')
                        saved=json.loads(row['packet'])
                        if timeline_packet(self.service,app_id,saved)!=saved:raise Invalid('Artifact source or app revision changed')
                        return encode_response(timeline_public(row))
                    if action=='cancel':
                        if row['status']=='PREPARED':db.execute("UPDATE ios_agent_timeline_jobs SET status='CANCELLED',updated=? WHERE app_id=? AND id=?",(now(),app_id,row['id']))
                        elif row['status']!='CANCELLED':raise Invalid('Completed render cannot be cancelled')
                        return encode_response(timeline_public(timeline_row(db,app_id,user['principal'],row['id'])))
                    if action=='finish' and row['status']=='SUCCEEDED':
                        saved=json.loads(row['packet'])
                        if (body['packet_hash']!=row['packet_hash'] or inspection!=json.loads(row['result'])
                                or timeline_packet(self.service,app_id,saved)!=saved):
                            raise Invalid('Completed timeline retry differs from its current source or decoded evidence')
                        return encode_response(timeline_public(row))
                    if row['status']!='PREPARED' or body['packet_hash']!=row['packet_hash']:raise Invalid('Timeline render is no longer current')
                    check_authority(db,app_id,'timeline',row['id'])
                    saved=json.loads(row['packet']);current=timeline_packet(self.service,app_id,saved)
                    if current!=saved or current['packet_hash']!=row['packet_hash']:raise Invalid('Timeline packet changed')
                    if action=='validate':return encode_response(saved)
                    self.validate_inspection(row,saved,inspection,expected_timeline_audio(db,self.service.store,app_id,saved))
                    db.execute("UPDATE ios_agent_timeline_jobs SET status='SUCCEEDED',result=?,updated=? WHERE app_id=? AND id=?",(canonical(inspection),now(),app_id,row['id']))
                    return encode_response(timeline_public(timeline_row(db,app_id,user['principal'],row['id'])))

    def source(self,session,app_id,payload):
        """Return one approved source only through the fixed trusted host bridge."""
        from .ios_bridge import decode_document,encode_response
        from .ios_production import NativeProduction
        from .operation_authority import bound_owner,protected
        body=decode_document(payload)
        if not isinstance(body,dict) or set(body)!={'job_id','packet_hash','kind','source_id','sha256'}:
            raise Invalid('Use exact native timeline source fields')
        user=self.identities.fresh(session);envelope=dict(app_id=app_id,operation='native.agent-timeline.source',input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                with connection(self.service.store.path) as db:
                    db.execute('BEGIN IMMEDIATE');row=timeline_row(db,app_id,user['principal'],body['job_id'])
                    if row['status']!='PREPARED' or row['packet_hash']!=body['packet_hash']:
                        raise Invalid('Timeline render is no longer current')
                    check_authority(db,app_id,'timeline',row['id']);packet=json.loads(row['packet'])
                    if timeline_packet(self.service,app_id,packet)!=packet:raise Invalid('Timeline packet changed')
                    path=NativeProduction(self.service,self.identities).source(session,app_id,packet['project_id'],
                        packet['revision'],packet['project_hash'],packet['packet_hash'],body['kind'],body['source_id'],body['sha256'])
                    check_authority(db,app_id,'timeline',row['id'])
                    return encode_response({'path':str(path)})

    @staticmethod
    def validate_inspection(row,packet,inspection,expected_audio):
        import re
        fields={'artifact_id','sha256','bytes','frames','width','height','audio'}
        plan=packet['plan']
        if (not isinstance(inspection,dict) or set(inspection)!=fields or inspection['artifact_id']!=row['id']
                or not isinstance(inspection['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',inspection['sha256'])
                or type(inspection['bytes']) is not int or not 0<inspection['bytes']<=67108864
                or type(inspection['frames']) is not int or inspection['frames']!=plan['output_frame_count']
                or type(inspection['width']) is not int or inspection['width']!=plan['width']
                or type(inspection['height']) is not int or inspection['height']!=plan['height']
                or type(inspection['audio']) is not bool or inspection['audio']!=expected_audio):
            raise Invalid('Decoded artifact does not match the prepared timeline')
