"""Source-bound native render preparation and trusted renderer revalidation.

No render is performed here. Native output cannot be marked complete without
decoding and a final recheck of this exact saved project and source authority.
"""
from .common import Invalid, digest
from .ios_bridge import encode_response


class NativeProduction:
    def __init__(self, service, identities):
        self.service = service
        self.identities = identities

    def _current(self, app_id, project_id, revision, project_hash):
        from .video_edit_projects import Projects
        if type(revision) is not int or revision < 1 or not isinstance(project_hash,str):
            raise Invalid('Use the exact saved project revision and hash')
        project = Projects(self.service.store, 'LOCAL_SESSION').read(app_id,project_id)
        if (project['revision'] != revision or project['hash'] != project_hash or
                project['source_status'] != 'CURRENT'):
            raise Invalid('Project or source authority changed; prepare the current revision')
        return project

    def _authorized(self, session, app_id, action, body, execute):
        from .operation_authority import bound_owner, protected
        user = self.identities.fresh(session)
        envelope=dict(app_id=app_id,operation='native.production.'+action,input=body)
        with bound_owner(self.service.store,envelope,self.identities,session,user):
            with protected(self.service.store,envelope):return execute()

    def prepare(self, session, app_id, project_id, revision, project_hash):
        from .ios_render_plan import compile_plan
        body=dict(project_id=project_id,revision=revision,project_hash=project_hash)
        def execute():
            project=self._current(app_id,project_id,revision,project_hash)
            plan=compile_plan(project['data']['definition'])
            # Snapshot and shared read are checked again by the renderer before
            # each source and at output commit; this packet is never a receipt.
            packet=dict(schema='growth.ios-production-packet.v1',app_id=app_id,
                manifest_version=project['data']['manifest_version'],**body,plan=plan,
                status='PREPARED_NOT_RENDERED',execution_authority=False)
            return encode_response(dict(packet,packet_hash=digest(packet)))
        return self._authorized(session,app_id,'prepare',body,execute)

    def validate(self, session, app_id, project_id, revision, project_hash, packet_hash):
        import json
        packet=json.loads(self.prepare(session,app_id,project_id,revision,project_hash))
        if packet['packet_hash'] != packet_hash:
            raise Invalid('Native render packet changed; prepare it again')
        return packet

    def source(self, session, app_id, project_id, revision, project_hash, packet_hash, kind, source_id, sha256):
        from .managed_media_store import Media
        from .creative_rendering import artifact_file
        from .db import connection
        from .video_edit_projects import source_binding
        body=dict(project_id=project_id,revision=revision,project_hash=project_hash,
                  packet_hash=packet_hash,kind=kind,id=source_id,sha256=sha256)
        def execute():
            packet=self.validate(session,app_id,project_id,revision,project_hash,packet_hash)
            wanted=dict(kind=kind,id=source_id,sha256=sha256)
            if not any(c['source']==wanted for c in packet['plan']['clips']):
                raise Invalid('Source does not belong to the prepared timeline')
            with connection(self.service.store.path) as db:
                source_binding(db,self.service.store,app_id,wanted)
            if kind=='MANAGED':return Media(self.service.store).resolve(app_id,source_id,sha256,require_reuse=True)
            if kind=='NATIVE':return artifact_file(self.service.store,app_id,source_id)[0]
            raise Invalid('Unsupported native source')
        # Path is returned only to the trusted in-process native renderer. Never
        # include it in agent protocol responses, report exports or model prompts.
        return self._authorized(session,app_id,'source',body,execute)
