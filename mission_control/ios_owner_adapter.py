"""In-process owner gateway; authenticated identity comes only from the native host.

The embedding host supplies fresh/local identity verification backed by Keychain
and a live native session, with the same interface as the shared identity store.
No request can supply a principal, role, session generation or Python function.
This module does not itself authenticate a device user or enroll a checker.
"""
from .ios_bridge import decode_request, encode_response


class OwnerAdapter:
    def __init__(self, service, identities):
        self.service = service
        self.identities = identities

    def enroll(self, session, app_id, confirmation):
        """Explicit first-owner enrollment; no replacement or implicit enrollment."""
        from .review_access import Access
        user = self.identities.fresh(session)
        admitted = self.identities.local(session, user['principal'])
        def current():
            self.identities.local(session, user['principal'], admitted['session_generation'])
        result = Access(self.service.store).bootstrap(
            app_id, user, confirmation, commit_check=current)
        current()
        # Shared desktop presentation must not label a native host as GitHub.
        result = dict(result, identity_provider=user.get('provider') or 'NATIVE_HOST',
                      bootstrap='First authenticated owner on this local device')
        return encode_response(result)

    def call(self, session, payload):
        """Bind current owner and role version to each exact domain transaction."""
        from .operation_authority import bound_owner, protected
        from .operation_runtime import execute
        envelope = decode_request(payload)
        user = self.identities.fresh(session)
        with bound_owner(self.service.store, envelope, self.identities, session, user):
            with protected(self.service.store, envelope):
                result = execute(self.service, envelope, caller='LOCAL_SESSION')
        return encode_response(result)
