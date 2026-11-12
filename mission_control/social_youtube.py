"""Validate a provider-read YouTube channel without trusting decoded identity tokens."""

from .common import Invalid
from .social_contract import account_id, display
from .social_transport import SocialError


def channel(raw, expected=None):
    """Exactly one unpaginated channel is the stable subject and destination.

    Multi-channel responses are rejected until a stable provider-verified account
    identity and channel-selection protocol exists; order is never authority.
    """
    if not isinstance(raw, dict) or raw.get("error") or raw.get("nextPageToken"):
        raise SocialError("INVALID_RESPONSE")
    items = raw.get("items")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise Invalid("YouTube requires exactly one verified channel; choose an account with one channel")
    item = items[0]
    snippet = item.get("snippet")
    if not isinstance(snippet, dict):
        raise SocialError("INVALID_RESPONSE")
    subject = account_id(item.get("id"))
    name = display(snippet.get("title"))
    if expected is not None and subject != expected:
        raise Invalid("YouTube channel changed; reconnect and confirm the account")
    return subject, name
