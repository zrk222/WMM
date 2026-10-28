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
        return execute(service, envelope)


class ScopedAgentAdapter:
    def __init__(self, service, clock=None):
        self.service = service
        self.clock = clock

    def call(self, token, payload):
        from .agent_grants import Grants
        from .automation_execution import dispatch_admitted
        from .operation_authority import bound_agent
        from .video_edit_projects import admitted_caller
        envelope = decode_request(payload)
        admission = Grants(self.service.store, self.clock).admit(token, envelope)
        # Preserve reservation, exact admission, standing authority and commit guards.
        with bound_agent(self.service.store, envelope, admission), admitted_caller(admission):
            value = dispatch_admitted(self.service, envelope, admission, guarded_execute)
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
        return encode_response(ReviewedDispatch(self.service, self.clock, executor=guarded_execute).resume(
            token, app_id, request_id, revision, packet_hash))
