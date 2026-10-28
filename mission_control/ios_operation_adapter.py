"""In-process scoped-agent gateway reusing the shared admission and review paths.

The embedding host supplies a configured domain service. Native owner enrollment,
Keychain integration and media/provider adapters are separate required packets.
No owner, checker, arbitrary function or identity is accepted in a request body.
"""
from .ios_bridge import decode_request, encode_response


class ScopedAgentAdapter:
    def __init__(self, service, clock=None):
        self.service = service
        self.clock = clock

    def call(self, token, payload):
        from .agent_grants import Grants
        from .automation_execution import dispatch_admitted
        from .operation_authority import bound_agent, protected
        from .operation_runtime import execute
        from .video_edit_projects import admitted_caller
        envelope = decode_request(payload)
        admission = Grants(self.service.store, self.clock).admit(token, envelope)
        # Preserve reservation, exact admission, standing authority and commit guards.
        def guarded_execute(service, exact_envelope):
            with protected(service.store, exact_envelope):
                return execute(service, exact_envelope)
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
        # A broader protection scope rejected cancellation in the shared tests.
        # Do not expose native resume until cancellation and commit guards coexist.
        raise NotImplementedError('Native reviewed resume requires cancellation-safe commit protection')
