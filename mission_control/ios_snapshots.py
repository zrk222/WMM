"""Fixed native snapshot transport; imported data never restores authority."""
import json
from .common import Invalid,canonical,digest,identifier
from .ios_bridge import _unique_object

MAX_SNAPSHOT_BYTES=33_554_432


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
        user=self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='snapshot.export',input={})
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):
                result=canonical(self.service.store.export(app_id)).encode('utf-8')
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
        def finalize(db,restored_app):
            if restored_app!=app_id:raise Invalid('Restore changed the selected app')
            self.identities.local(session,user['principal'],user['session_generation'])
            Access(self.service.store).write(db,app_id,user,'OWNER','ACTIVE',1,user['principal'])
            audit(db,app_id,'access.owner_established',dict(principal=user['principal'],policy='NATIVE_SNAPSHOT_RESTORE'))
            self.identities.local(session,user['principal'],user['session_generation'])
        result=self.service.store.restore(value,finalize=finalize)
        return encode_response(dict(app=result,status='LOCAL_SNAPSHOT_RESTORED',authority='NEW_LOCAL_OWNER_ONLY',
                                    credentials='NOT_IMPORTED',publication='NOT_RUN'))
