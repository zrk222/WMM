"""Fixed native snapshot transport; imported data never restores authority."""
import json
from .common import Invalid,canonical,digest,identifier
from .ios_bridge import _unique_object

MAX_SNAPSHOT_BYTES=33_554_432


def studio_projects(value):
    """Portable scene data carries no owner, credentials or execution receipts."""
    from .hypit_authoring import scene_contract
    if not isinstance(value,list) or len(value)>1000:raise Invalid('Use at most 1000 portable scene revisions')
    seen={};result=[]
    for row in value:
        if not isinstance(row,dict) or set(row)!={'project_id','revision','manifest_version','scene','source_hash'}:
            raise Invalid('Portable scene revision contains unsupported fields')
        identity=identifier(row['project_id'])
        revision=row['revision'];manifest=row['manifest_version']
        if type(revision) is not int or revision!=seen.get(identity,0)+1 or type(manifest) is not int or manifest<1:
            raise Invalid('Portable scene revisions must be consecutive and versioned')
        scene=scene_contract(row['scene'])
        if digest(scene)!=row['source_hash']:raise Invalid('Portable scene integrity changed')
        seen[identity]=revision;result.append(dict(row,project_id=identity,scene=scene))
    return result


def document(payload):
    if not isinstance(payload,bytes) or not 1<=len(payload)<=MAX_SNAPSHOT_BYTES:
        raise Invalid('Choose a snapshot within the 32 MiB portable limit')
    def nonfinite(value):raise ValueError('Nonfinite snapshot')
    try:
        value=json.loads(payload.decode('utf-8'),object_pairs_hook=_unique_object,parse_constant=nonfinite)
        canonical(value)
    except (UnicodeError,ValueError,RecursionError) as error:
        raise Invalid('Use a finite UTF-8 snapshot document') from error
    if not isinstance(value,dict):raise Invalid('Use a snapshot document object')
    return value


class NativeSnapshots:
    def __init__(self,service,identities):self.service=service;self.identities=identities

    def export(self,session,app_id):
        from .operation_authority import bound_owner,protected
        from .db import connection
        from .ios_studio import NativeStudio
        user=self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='snapshot.export',input={})
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                snapshot=self.service.store.export(app_id)
                with connection(self.service.store.path) as db:
                    rows=db.execute('SELECT * FROM ios_studio_projects WHERE app_id=? ORDER BY id,revision',(app_id,)).fetchall()
                    snapshot['payload']['ios_studio']=dict(schema='growth.ios-studio-portable.v1',
                        projects=studio_projects([NativeStudio._public(row) for row in rows]),
                        renders='EXPORT_VIDEOS_SEPARATELY',authority='NOT_EXPORTED')
                snapshot['sha256']=digest(snapshot['payload'])
                result=canonical(snapshot).encode('utf-8')
                self.identities.local(session,user['principal'],user['session_generation'])
        if len(result)>MAX_SNAPSHOT_BYTES:raise Invalid('Snapshot exceeds the portable limit')
        return result

    def restore(self,session,app_id,payload,confirmed):
        from .review_access import Access
        from .store import audit
        from .ios_bridge import encode_response
        if confirmed is not True:raise Invalid('Confirm restoring this snapshot as a new local workspace')
        user=self.identities.fresh(session)
        value=document(payload);app_id=identifier(app_id)
        content=value.get('payload')
        if not isinstance(content,dict) or value.get('sha256')!=digest(content):raise Invalid('Snapshot integrity check failed')
        app=content.get('app')
        if not isinstance(app,dict) or app.get('id')!=app_id:raise Invalid('Selected app differs from the snapshot')
        section=content.get('ios_studio',dict(schema='growth.ios-studio-portable.v1',projects=[],renders='EXPORT_VIDEOS_SEPARATELY',authority='NOT_EXPORTED'))
        if (not isinstance(section,dict) or set(section)!={'schema','projects','renders','authority'}
                or section['schema']!='growth.ios-studio-portable.v1' or section['renders']!='EXPORT_VIDEOS_SEPARATELY'
                or section['authority']!='NOT_EXPORTED'):raise Invalid('Portable Studio section is invalid')
        scenes=studio_projects(section['projects'])
        def finalize(db,restored_app):
            if restored_app!=app_id:raise Invalid('Restore changed the selected app')
            self.identities.local(session,user['principal'],user['session_generation'])
            Access(self.service.store).write(db,app_id,user,'OWNER','ACTIVE',1,user['principal'])
            from .common import now
            for row in scenes:
                # Restore creates a new manifest revision and new local owner.
                # Preserve scene revision history, never imported render authority.
                key='restore:'+row['project_id']+':'+str(row['revision'])
                db.execute('INSERT INTO ios_studio_projects VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (app_id,row['project_id'],row['revision'],1,canonical(row['scene']),row['source_hash'],
                     user['principal'],key,digest(row),now()))
            audit(db,app_id,'access.owner_established',dict(principal=user['principal'],policy='NATIVE_SNAPSHOT_RESTORE'))
            self.identities.local(session,user['principal'],user['session_generation'])
        result=self.service.store.restore(value,finalize=finalize)
        return encode_response(dict(app=result,status='LOCAL_SNAPSHOT_RESTORED',authority='NEW_LOCAL_OWNER_ONLY',
                                    credentials='NOT_IMPORTED',publication='NOT_RUN'))
