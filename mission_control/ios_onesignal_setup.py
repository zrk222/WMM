"""Scoped host-Keychain bridge for OneSignal secret chunks; no fallback storage."""

import re
from .common import Invalid, canonical, digest, identifier
from .credential_vault import namespace
from .ios_bridge import decode_document
from .onesignal_transport import uuid_text


class OneSignalNativeVault:
    def __init__(self, callback, store, app_id, principal):
        if not callable(callback):
            raise Invalid("Native protected storage is unavailable")
        identifier(app_id)
        self.callback = callback
        self.prefix = "/".join(("OneSignal", namespace(store.path), app_id, digest(principal)[:24])) + "/"

    def invoke(self, action, target, value=None):
        if not isinstance(target, str) or not target.startswith(self.prefix):
            raise Invalid("OneSignal credential target escaped its owner namespace")
        segments = target[len(self.prefix) :].split("/")
        if len(segments) != 2:
            raise Invalid("OneSignal credential target is malformed")
        uuid_text(segments[0])
        if segments[1] != "manifest" and not re.fullmatch(r"[a-f0-9]{16}", segments[1]):
            raise Invalid("OneSignal credential chunk is malformed")
        result = decode_document(self.callback(canonical(dict(action=action, target=target, value=value)).encode()))
        if not isinstance(result, dict) or set(result) != {"ok", "value"} or result["ok"] is not True:
            raise Invalid("Native protected storage did not confirm the OneSignal action")
        return result["value"]

    def put(self, target, value):
        self.invoke("put", target, value)

    def get(self, target):
        return self.invoke("get", target)

    def delete(self, target):
        self.invoke("delete", target)


class NativeOneSignalSetup:
    def __init__(self, store, identities, vault_callback):
        self.store = store
        self.identities = identities
        self.vault_callback = vault_callback

    def call(self, session, app_id, action, payload):
        from .onesignal_setup_http import OneSignalSetupGateway

        user = self.identities.fresh(session)

        def vault():
            return OneSignalNativeVault(self.vault_callback, self.store, app_id, user["principal"])

        return OneSignalSetupGateway(self.store, self.identities, vault).call(session, app_id, action, payload)
