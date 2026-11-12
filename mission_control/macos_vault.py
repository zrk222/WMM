"""Explicit macOS Keychain storage; no backend discovery or file fallback."""
import hashlib
import importlib
import json

from .common import Invalid, canonical
from .payment_signature import unique_pairs

SERVICE = 'Wize Marketing Machine'
MAX_BYTES = 2560
UNAVAILABLE = 'Unlock macOS Keychain and open WMM again. Existing connection records are preserved.'


def address(name: str) -> str:
    """Keep app, workspace and provider names out of native item metadata."""
    if not isinstance(name, str) or not name or len(name) > 2048 or any(ord(c) < 32 for c in name):
        raise Invalid('Protected credential address is invalid')
    return hashlib.sha256(name.encode('utf-8')).hexdigest()


def encode(value) -> str:
    """Apply the existing Windows and Linux credential payload ceiling."""
    raw = canonical(value)
    if len(raw.encode('utf-8')) > MAX_BYTES:
        raise Invalid('Protected credential exceeds the native size limit')
    return raw


def decode(raw: str):
    """Reject corrupt native values without including them in an error."""
    if not isinstance(raw, str):
        raise Invalid('Protected credential is invalid; rotate this connection')
    try:
        if len(raw.encode('utf-8')) > MAX_BYTES:
            raise Invalid('Protected credential size is invalid')
        return json.loads(raw, object_pairs_hook=unique_pairs,
                          parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid('Protected credential is invalid; rotate this connection') from None


def reject_constant(_value: str):
    """Keep native reads as strict as canonical JSON writes."""
    raise ValueError('Non-finite values are not JSON')


class MacOSVault:
    """Use only keyring's native Security-framework adapter for the current user."""
    def __init__(self):
        try:
            adapter = importlib.import_module('keyring.backends.macOS')
            self.backend = adapter.Keyring()
            # Do not adopt KEYCHAIN_PATH or keyring's configurable backend selection.
            self.backend.keychain = None
        except Exception:
            raise Invalid('macOS protected credentials need the native Keychain adapter; no plaintext fallback is used.') from None

    def put(self, name: str, value) -> None:
        account, raw = address(name), encode(value)
        try:
            self.backend.set_password(SERVICE, account, raw)
        except Exception:
            raise Invalid(UNAVAILABLE) from None

    def get(self, name: str):
        account = address(name)
        try:
            raw = self.backend.get_password(SERVICE, account)
        except Exception:
            raise Invalid(UNAVAILABLE) from None
        return None if raw is None else decode(raw)

    def delete(self, name: str) -> None:
        account = address(name)
        try:
            if self.backend.get_password(SERVICE, account) is None:
                return
            try:
                self.backend.delete_password(SERVICE, account)
            except Exception:
                # An exact concurrent deletion is idempotent; denied reads still fail.
                if self.backend.get_password(SERVICE, account) is not None:
                    raise
        except Exception:
            raise Invalid(UNAVAILABLE) from None
