"""In-process scoped-agent gateway reusing the shared admission and review paths.

The embedding host supplies a configured domain service. Native owner enrollment,
Keychain integration and media/provider adapters are separate required packets.
No owner, checker, arbitrary function or identity is accepted in a request body.
"""
from .ios_bridge import decode_request, encode_response


def guarded_execute(service, envelope):
    """Bind the actual domain transactions to the shared current commit checks."""
    from .operation_authority import protected
    from .operation_runtime import execute
    with protected(service.store, envelope):
        if envelope['operation'] in ('pipeline.prepare', 'job.cancel'):
            from .ios_jobs import PIPELINE_HOST, queue_scoped_pipeline, cancel_scoped_pipeline
            from .automation_execution import ACTIVE
            from .complete_automation import ACCESS_VERIFIER
            if ACTIVE.get() is not None and ACCESS_VERIFIER.get() is not None:
                if PIPELINE_HOST.get() is None:
                    raise PermissionError('Trusted native pipeline host is unavailable')
                if envelope['operation'] == 'pipeline.prepare':
                    return queue_scoped_pipeline(service, envelope)
                return cancel_scoped_pipeline(service, envelope)
        return execute(service, envelope)


class ScopedAgentAdapter:
    def __init__(self, service, clock=None, host_check=None):
        self.service = service
        self.clock = clock
        self.host_check = host_check

    def call(self, token, payload):
        from .agent_grants import Grants
        from .automation_execution import dispatch_admitted
        from .operation_authority import bound_agent
        from .video_edit_projects import admitted_caller
        envelope = decode_request(payload)
        if self.host_check is not None:self.host_check()
        admission = Grants(self.service.store, self.clock).admit(token, envelope)
        # Preserve reservation, exact admission, standing authority and commit guards.
        with bound_agent(self.service.store, envelope, admission, host_check=self.host_check), admitted_caller(admission):
            value = dispatch_admitted(self.service, envelope, admission, guarded_execute)
        if self.host_check is not None:self.host_check()
        return encode_response(value)

    def prepare_review(self, token, request_id, payload):
        from .agent_review_dispatch import ReviewedDispatch
        return encode_response(ReviewedDispatch(self.service, self.clock).prepare(
            token, request_id, decode_request(payload)))

    def inspect_review(self, token, app_id, request_id):
        from .agent_review_dispatch import ReviewedDispatch
        return encode_response(ReviewedDispatch(self.service, self.clock).inspect(
            token, app_id, request_id))

    def resume_review(self, token, app_id, request_id, revision, packet_hash):
        from .agent_review_dispatch import ReviewedDispatch
        return encode_response(ReviewedDispatch(self.service, self.clock, executor=guarded_execute,host_check=self.host_check).resume(
            token, app_id, request_id, revision, packet_hash))
