"""Bounded JSON framing for the bundled engine, independent of desktop imports.

The native authority dispatcher is injected by the embedding host. This module
does not manufacture identity, call the unauthenticated internal dispatcher,
start an HTTP server or treat a caller-supplied role as an admission decision.
"""
import json

from .common import Invalid, canonical
from .operation_catalog import request_data


MAX_REQUEST_BYTES = 1048576
MAX_RESPONSE_BYTES = 16777216


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Invalid('Duplicate JSON fields are not permitted')
        value[key] = item
    return value


def decode_document(payload):
    """Decode bounded finite JSON; each fixed entry point validates its own schema."""
    if not isinstance(payload, bytes) or not 1 <= len(payload) <= MAX_REQUEST_BYTES:
        raise Invalid('Use bounded UTF-8 request bytes')
    try:
        value = json.loads(payload.decode('utf-8'), object_pairs_hook=_unique_object,
                           parse_constant=lambda value: _reject_constant())
        canonical(value)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise Invalid('Invalid finite UTF-8 JSON request') from error
    return value


def decode_request(payload):
    """Reject oversized, ambiguous and nonfinite operation envelopes."""
    value = decode_document(payload)
    request_data(value)
    return value


def _reject_constant():
    raise Invalid('Nonfinite JSON is not permitted')


def encode_response(value):
    """Encode only finite shared JSON results; never stringify arbitrary objects."""
    try:
        payload = canonical(value).encode('utf-8')
    except (TypeError, ValueError, RecursionError) as error:
        raise Invalid('Domain result is not finite JSON') from error
    if len(payload) > MAX_RESPONSE_BYTES:
        raise Invalid('Domain result exceeds the bridge response limit')
    return payload


class DomainBridge:
    """Inject a trusted native gateway, not a caller-selected Python function."""

    def __init__(self, authority_dispatcher):
        if not callable(authority_dispatcher):
            raise TypeError('A native authority dispatcher is required')
        self._dispatch = authority_dispatcher

    def call(self, payload):
        envelope = decode_request(payload)
        # Gateway must admit owner/agent identity and recheck authority at commit.
        # Reuse of operation_runtime.execute directly here would bypass admission.
        return encode_response(self._dispatch(envelope))
