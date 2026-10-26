"""Explicit Linux Secret Service storage; no prompts, collection creation or fallback."""
from contextlib import contextmanager
import hashlib
import importlib
import json
import time
from .common import Invalid, canonical
from .payment_signature import unique_pairs

MAX_BYTES = 2560


def address(name):
    """Keep metadata secret-free while preserving every byte of the caller's scope."""
    if not isinstance(name, str) or not name or len(name) > 2048 or any(ord(c) < 32 for c in name):
        raise Invalid('Protected credential address is invalid')
    return {'application':'WMM', 'schema':'native-vault-v1', 'address_sha256':hashlib.sha256(name.encode()).hexdigest()}


def encode(value):
    """Use the same bounded JSON payload as the Windows native adapter."""
    raw = canonical(value).encode()
    if len(raw) > MAX_BYTES:raise Invalid('Protected credential exceeds the native size limit')
    return raw


def attributes_match(actual,expected):
    """Allow only the exact optional GNOME generic-item metadata beside WMM scope."""
    return actual == expected or actual == expected | {'xdg:schema':'org.freedesktop.Secret.Generic'}


def decode(raw):
    """Reject oversized, duplicate-key or corrupt native bytes without echoing them."""
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:raise Invalid('Protected credential size is invalid')
    try:return json.loads(raw, object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError, RecursionError):raise Invalid('Protected credential is invalid; rotate this connection') from None


class BoundedBus:
    """Delegate D-Bus methods while bounding every reply to the operation deadline."""
    def __init__(self, bus):
        self.bus = bus; self.deadline = time.monotonic() + 15

    def send_and_get_reply(self, message, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:raise TimeoutError('Secret Service operation deadline')
        return self.bus.send_and_get_reply(message, timeout=remaining)

    def __getattr__(self, name):return getattr(self.bus, name)


class LinuxVault:
    def __init__(self):
        try:self.library = importlib.import_module('secretstorage')
        except ImportError:
            raise Invalid('Linux protected credentials need SecretStorage and an unlocked desktop Secret Service. Install the documented native dependency; no plaintext fallback is used.') from None

    @contextmanager
    def collection(self):
        """Open only an existing unlocked collection and require encrypted transport."""
        bus = None
        try:
            bus = self.library.dbus_init(); bounded = BoundedBus(bus)
            collection = self.library.Collection(bounded)
            if collection.is_locked():raise Invalid('Unlock the desktop keyring before using protected WMM connections')
            from secretstorage.util import open_session
            session = open_session(bounded)
            if not session.encrypted:raise Invalid('Secret Service encrypted transport is required')
            collection.session = session
            yield collection
        except Invalid:raise
        except Exception:
            raise Invalid('Linux protected credential service is unavailable or locked; unlock the desktop keyring and retry. Existing connection records are preserved.') from None
        finally:
            if bus is not None:bus.close()

    def item(self, collection, attributes):
        """Resolve at most one exact item; duplicates cannot silently choose a secret."""
        items = []
        for item in collection.search_items(attributes):
            items.append(item)
            if len(items) > 1:raise Invalid('Duplicate protected credential entries require native keyring review')
        if not items:return None
        item = items[0]
        if not attributes_match(item.get_attributes(),attributes):raise Invalid('Protected credential address differs; reconnect')
        if item.is_locked():raise Invalid('Unlock the desktop keyring before using this connection')
        return item

    def put(self, name, value):
        """Create or replace one exact native item in the existing unlocked keyring."""
        attributes = address(name); raw = encode(value)
        with self.collection() as collection:
            self.item(collection, attributes)
            collection.create_item('WMM protected connection', attributes, raw, replace=True, content_type='application/json')

    def get(self, name):
        """Read exact protected bytes without listing other application credentials."""
        attributes = address(name)
        with self.collection() as collection:
            item = self.item(collection, attributes)
            return None if item is None else decode(item.get_secret())

    def delete(self, name):
        """Idempotently delete one exact local item; no provider revocation is implied."""
        attributes = address(name)
        with self.collection() as collection:
            item = self.item(collection, attributes)
            if item is not None:item.delete()
