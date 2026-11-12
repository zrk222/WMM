"""Owner-bound OneSignal setup with durable single-attempt provider effects.

SCHEMA is installed by the host database bootstrap, never by request handlers.
Only opaque native-vault references and safe provider metadata are stored locally.
"""

import base64
import json
import re
import time
from datetime import timedelta
from .common import Invalid, canonical, digest, identifier, iso_time, now, required, uid
from .credential_vault import Vault, namespace
from .db import connection
from .operation_authority import PROTECTED, check, store_identity
from .onesignal_transport import CHANNEL_FIELDS, key_text, payload, request, safe_app, uuid_text

PRIVATE_FIELDS = frozenset(("apns_p8", "fcm_v1_service_account_json"))
APNS_FIELDS = frozenset(("apns_p8", "apns_key_id", "apns_team_id", "apns_bundle_id"))


def encoded_update(values):
    encoded = {
        k: (base64.b64encode(v.encode("utf-8")).decode("ascii") if k in PRIVATE_FIELDS else v)
        for k, v in values.items()
    }
    checked = payload("update", encoded)
    if len(canonical(checked).encode("utf-8")) > 65536:
        raise Invalid("OneSignal setup body is too large")
    return checked


SCHEMA = """
CREATE TABLE IF NOT EXISTS onesignal_connections(app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL, version INTEGER NOT NULL, kind TEXT NOT NULL, secret_ref TEXT NOT NULL, provider_app_id TEXT, organization_id TEXT, data TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(app_id,owner));
CREATE TABLE IF NOT EXISTS onesignal_setup_effects(id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL, request_key TEXT NOT NULL, action TEXT NOT NULL, packet TEXT NOT NULL, packet_hash TEXT NOT NULL, status TEXT NOT NULL, secret_ref TEXT, provider_app_id TEXT, result TEXT, created TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(app_id,owner,request_key));
CREATE TABLE IF NOT EXISTS onesignal_retirements(app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL, reference TEXT NOT NULL, eligible REAL NOT NULL, PRIMARY KEY(app_id,owner,reference));
CREATE TABLE IF NOT EXISTS onesignal_recoveries(id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL, effect_id TEXT NOT NULL REFERENCES onesignal_setup_effects(id), packet TEXT NOT NULL, packet_hash TEXT NOT NULL, secret_ref TEXT, status TEXT NOT NULL, result TEXT, created TEXT NOT NULL, updated TEXT NOT NULL);
"""


def unresolved(db, app_id, principal, exclude=None, secret_ref=None):
    """An explicit readback recovery closes the lock without changing the old receipt."""
    sql = """SELECT 1 FROM onesignal_setup_effects e WHERE e.app_id=? AND e.owner=? AND e.status IN ('RESERVED','UNKNOWN')
        AND NOT EXISTS (SELECT 1 FROM onesignal_recoveries r WHERE r.effect_id=e.id AND r.status='RECOVERED_READBACK_ONLY')"""
    args = [app_id, principal]
    if exclude is not None:
        sql += " AND e.id!=?"
        args.append(exclude)
    if secret_ref is not None:
        sql += " AND e.secret_ref=?"
        args.append(secret_ref)
    return db.execute(sql, args).fetchone()


def owner(store, app_id):
    """Refuse caller-supplied identities and require the current protected owner scope."""
    identifier(app_id)
    context = PROTECTED.get()
    if context is None or "principal" not in context or context["store"] != store_identity(store):
        raise PermissionError("A current protected owner session is required")
    if json.loads(context["envelope"]).get("app_id") != app_id:
        raise PermissionError("Owner scope belongs to another app")
    with connection(store.path) as db:
        principal = check(db, context)
    return principal, context["role_version"]


def entry(store, app_id, action, body):
    principal, role_version = owner(store, app_id)
    envelope = json.loads(PROTECTED.get()["envelope"])
    if envelope != {"app_id": app_id, "operation": "onesignal." + action, "input": body}:
        raise PermissionError("The exact OneSignal owner operation is required")
    return principal, role_version


def target(store, app_id, principal, reference, part):
    identifier(app_id)
    uuid_text(reference)
    if not re.fullmatch(r"[a-f0-9]{16}", part) and part != "manifest":
        raise Invalid("Protected setup part is invalid")
    return "/".join(("OneSignal", namespace(store.path), app_id, digest(principal)[:24], reference, part))


class Secrets:
    def __init__(self, store, vault_factory=None):
        self.store = store
        self.vault_factory = vault_factory or Vault

    def stage(self, app_id, principal, values):
        """Durably register cleanup before writing bounded chunks to native storage."""
        if not isinstance(values, dict) or not values or set(values) - ({"app_key", "org_key"} | CHANNEL_FIELDS):
            raise Invalid("Unsupported protected OneSignal fields")
        encoded = {}
        for field, value in values.items():
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 16384:
                raise Invalid("Protected OneSignal field is invalid or too large")
            encoded[field] = base64.b64encode(value.encode("utf-8")).decode("ascii")
        ref = uid()
        manifest = {
            field: [digest(field + ":" + str(offset))[:16] for offset in range(0, len(value), 1200)]
            for field, value in encoded.items()
        }
        vault = self.vault_factory()
        with connection(self.store.path) as db:
            db.execute(
                "INSERT INTO onesignal_retirements VALUES(?,?,?,?)", (app_id, principal, ref, time.time() + 1800)
            )
        try:
            vault.put(target(self.store, app_id, principal, ref, "manifest"), {"fields": manifest})
            for field, value in encoded.items():
                for offset in range(0, len(value), 1200):
                    name = digest(field + ":" + str(offset))[:16]
                    vault.put(
                        target(self.store, app_id, principal, ref, name), {"value": value[offset : offset + 1200]}
                    )
        except Exception:
            # Keep the durable stage for recovery; no plaintext fallback.
            raise Invalid("Protected OneSignal staging failed; prior connection is unchanged") from None
        return ref

    def load(self, app_id, principal, ref):
        uuid_text(ref)
        vault = self.vault_factory()
        meta = vault.get(target(self.store, app_id, principal, ref, "manifest"))
        if not isinstance(meta, dict) or set(meta) != {"fields"} or not isinstance(meta["fields"], dict):
            raise Invalid("Protected OneSignal credentials are unavailable")
        if not meta["fields"] or set(meta["fields"]) - ({"app_key", "org_key"} | CHANNEL_FIELDS):
            raise Invalid("Protected OneSignal manifest is invalid")
        output = {}
        for field, parts in meta["fields"].items():
            if not isinstance(parts, list) or not 1 <= len(parts) <= 19:
                raise Invalid("Protected OneSignal manifest is invalid")
            fragments = []
            for name in parts:
                item = vault.get(target(self.store, app_id, principal, ref, name))
                if not isinstance(item, dict) or set(item) != {"value"} or not isinstance(item["value"], str):
                    raise Invalid("Protected OneSignal credentials are unavailable")
                fragments.append(item["value"])
            try:
                output[field] = base64.b64decode("".join(fragments), validate=True).decode("utf-8")
            except (ValueError, UnicodeError):
                raise Invalid("Protected OneSignal credentials are invalid") from None
        return output

    def activate(self, db, app_id, principal, ref):
        row = db.execute(
            "SELECT eligible FROM onesignal_retirements WHERE app_id=? AND owner=? AND reference=?",
            (app_id, principal, ref),
        ).fetchone()
        if not row or row["eligible"] <= time.time():
            raise Invalid("Protected OneSignal stage expired")
        self.load(app_id, principal, ref)
        db.execute(
            "DELETE FROM onesignal_retirements WHERE app_id=? AND owner=? AND reference=?", (app_id, principal, ref)
        )

    def cleanup(self, app_id, principal):
        """Delete only eligible inactive chunks; unresolved effects preserve their stage."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT reference FROM onesignal_retirements WHERE app_id=? AND owner=? AND eligible<=? LIMIT 20",
                (app_id, principal, time.time()),
            ).fetchall()
            vault = self.vault_factory()
            for row in rows:
                ref = row["reference"]
                active = db.execute(
                    "SELECT 1 FROM onesignal_connections WHERE app_id=? AND owner=? AND secret_ref=?",
                    (app_id, principal, ref),
                ).fetchone()
                pending = unresolved(db, app_id, principal, secret_ref=ref)
                if active or pending:
                    continue
                meta = vault.get(target(self.store, app_id, principal, ref, "manifest"))
                if meta is not None:
                    if not isinstance(meta, dict) or set(meta) != {"fields"} or not isinstance(meta["fields"], dict):
                        raise Invalid("Protected cleanup manifest is invalid")
                    for names in meta["fields"].values():
                        if not isinstance(names, list) or len(names) > 19:
                            raise Invalid("Protected cleanup manifest is invalid")
                        for name in names:
                            vault.delete(target(self.store, app_id, principal, ref, name))
                    vault.delete(target(self.store, app_id, principal, ref, "manifest"))
                db.execute(
                    "DELETE FROM onesignal_retirements WHERE app_id=? AND owner=? AND reference=?",
                    (app_id, principal, ref),
                )


def connection_row(db, app_id, principal):
    row = db.execute("SELECT * FROM onesignal_connections WHERE app_id=? AND owner=?", (app_id, principal)).fetchone()
    if not row:
        raise Invalid("Save a protected OneSignal key first")
    return dict(row)


def safe_status(row):
    data = json.loads(row["data"])
    return dict(
        version=row["version"],
        key_kind=row["kind"],
        provider_app_id=row["provider_app_id"],
        organization_id=row["organization_id"],
        **data,
        protected_key=True,
        sdk="SDK_BUILD_NOT_VERIFIED",
        device="DEVICE_SUBSCRIPTION_NOT_VERIFIED",
        next_action="Review provider setup, then verify the app SDK build and a real device subscription",
    )


class OneSignalSetup:
    def __init__(self, store, vault_factory=None, transport=request):
        self.store = store
        self.secrets = Secrets(store, vault_factory)
        self.transport = transport

    def status(self, app_id):
        principal, _ = entry(self.store, app_id, "status", {})
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT * FROM onesignal_connections WHERE app_id=? AND owner=?", (app_id, principal)
            ).fetchone()
        if not row:
            return {
                "state": "KEY_NOT_CONFIGURED",
                "protected_key": False,
                "sdk": "SDK_BUILD_NOT_VERIFIED",
                "device": "DEVICE_SUBSCRIPTION_NOT_VERIFIED",
                "next_action": "Save an app key to connect an existing app, or an organization key for provisioning",
            }
        return self._status(app_id, principal)

    def history(self, app_id):
        principal, _ = entry(self.store, app_id, "history", {})
        with connection(self.store.path) as db:
            rows = db.execute(
                "SELECT e.id,e.action,e.status,e.provider_app_id,e.result,e.created,e.updated,EXISTS(SELECT 1 FROM onesignal_recoveries r WHERE r.effect_id=e.id AND r.status='RECOVERED_READBACK_ONLY') AS recovered FROM onesignal_setup_effects e WHERE e.app_id=? AND e.owner=? ORDER BY e.created DESC LIMIT 100",
                (app_id, principal),
            ).fetchall()
        return {
            "effects": [
                dict(
                    id=r["id"],
                    action=r["action"],
                    status=r["status"],
                    provider_app_id=r["provider_app_id"],
                    result=json.loads(r["result"]) if r["result"] else None,
                    recovery="RECOVERED_READBACK_ONLY" if r["recovered"] else None,
                    created=r["created"],
                    updated=r["updated"],
                )
                for r in rows
            ]
        }

    def _status(self, app_id, principal):
        with connection(self.store.path) as db:
            return safe_status(connection_row(db, app_id, principal))

    def save_key(self, app_id, kind, key, version):
        principal, _ = entry(self.store, app_id, "save-key", {"kind": kind, "key": key, "version": version})
        if kind not in ("app", "org"):
            raise Invalid("Choose an app key or organization key")
        if type(version) is not int or version < 0:
            raise Invalid("Use the current OneSignal connection version")
        key_text(key)
        ref = self.secrets.stage(app_id, principal, {kind + "_key": key})
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT * FROM onesignal_connections WHERE app_id=? AND owner=?", (app_id, principal)
            ).fetchone()
            if version != (old["version"] if old else 0):
                raise Invalid("OneSignal connection changed; refresh before saving")
            if unresolved(db, app_id, principal):
                raise Invalid("Reconcile the pending OneSignal effect before rotating this key")
            self.secrets.activate(db, app_id, principal, ref)
            stamp = now()
            if old:
                db.execute(
                    "INSERT OR REPLACE INTO onesignal_retirements VALUES(?,?,?,?)",
                    (app_id, principal, old["secret_ref"], time.time()),
                )
            db.execute(
                "INSERT OR REPLACE INTO onesignal_connections VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    app_id,
                    principal,
                    version + 1,
                    kind,
                    ref,
                    None,
                    None,
                    canonical({"state": "KEY_SAVED_UNBOUND"}),
                    old["created"] if old else stamp,
                    stamp,
                ),
            )
        return self._status(app_id, principal)

    def read(self, app_id, selected_id=None):
        principal, _ = entry(self.store, app_id, "read", {"selected_id": selected_id})
        return self._read(app_id, principal, selected_id)

    def _read(self, app_id, principal, selected_id=None, sensitive=()):
        with connection(self.store.path) as db:
            row = connection_row(db, app_id, principal)
        values = self.secrets.load(app_id, principal, row["secret_ref"])
        if row["kind"] == "app":
            if selected_id is None:
                raise Invalid("Choose the exact OneSignal app ID for this app key")
            value = self.transport(
                "view", values["app_key"], uuid_text(selected_id), alive=lambda: owner(self.store, app_id)
            )
            if value["id"] != selected_id:
                raise Invalid("OneSignal returned a different app identity")
            projected = [safe_app(value)]
            return self._reject_sensitive_metadata(projected, sensitive)
        values = self.transport("list", values["org_key"], alive=lambda: owner(self.store, app_id))
        return self._reject_sensitive_metadata([safe_app(item) for item in values], sensitive)

    def _reject_sensitive_metadata(self, rows, sensitive):
        if any(
            secret in value
            for row in rows
            for value in row.values()
            if isinstance(value, str)
            for secret in sensitive
            if secret
        ):
            raise Invalid("OneSignal returned protected data in metadata; response rejected")
        return rows

    def bind(self, app_id, provider_app_id, expected_name, expected_org, version):
        principal, _ = entry(
            self.store,
            app_id,
            "bind",
            {
                "provider_app_id": provider_app_id,
                "expected_name": expected_name,
                "expected_org": expected_org,
                "version": version,
            },
        )
        uuid_text(provider_app_id)
        if type(version) is not int or version < 1:
            raise Invalid("Use the current OneSignal connection version")
        selected = [item for item in self._read(app_id, principal, provider_app_id) if item["id"] == provider_app_id]
        if (
            len(selected) != 1
            or selected[0]["name"] != expected_name
            or selected[0].get("organization_id") != expected_org
        ):
            raise Invalid("OneSignal app identity changed; inspect and select it again")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = connection_row(db, app_id, principal)
            if row["version"] != version:
                raise Invalid("OneSignal connection changed; select again")
            if unresolved(db, app_id, principal):
                raise Invalid("Reconcile the pending OneSignal effect before changing the binding")
            db.execute(
                "UPDATE onesignal_connections SET version=version+1,provider_app_id=?,organization_id=?,data=?,updated=? WHERE app_id=? AND owner=?",
                (
                    provider_app_id,
                    expected_org,
                    canonical({"state": "APP_BOUND", "name": expected_name}),
                    now(),
                    app_id,
                    principal,
                ),
            )
        return self._status(app_id, principal)

    def cleanup(self, app_id):
        principal, _ = entry(self.store, app_id, "cleanup", {})
        self.secrets.cleanup(app_id, principal)
        return {"cleanup": "CHECKED", "provider_revocation": "NOT_PERFORMED"}

    def prepare(self, app_id, action, details, request_key):
        principal, role_version = entry(
            self.store, app_id, "prepare", {"action": action, "details": details, "request_key": request_key}
        )
        uuid_text(request_key)
        if action not in ("create", "update") or not isinstance(details, dict):
            raise Invalid("Choose create or selected channel setup")
        app = self.store.app(app_id)
        with connection(self.store.path) as db:
            row = connection_row(db, app_id, principal)
            existing = db.execute(
                "SELECT * FROM onesignal_setup_effects WHERE app_id=? AND owner=? AND request_key=?",
                (app_id, principal, request_key),
            ).fetchone()
        if existing:
            raise Invalid("This request identity already exists; inspect its saved result")
        if row["kind"] != "org":
            raise Invalid("Create and configuration require an explicit organization key")
        secret_ref = None
        if action == "create":
            if set(details) != {"name", "organization_id"}:
                raise Invalid("Create requires the exact name and organization")
            public = {
                "name": required(details["name"], "OneSignal app name", 128),
                "organization_id": uuid_text(details["organization_id"]),
            }
            if any(
                item["name"].casefold() == public["name"].casefold()
                and item.get("organization_id") == public["organization_id"]
                for item in self._read(app_id, principal)
            ):
                raise Invalid("An app with this name exists in the organization; select an exact app ID instead")
        else:
            if not row["provider_app_id"] or not row["organization_id"]:
                raise Invalid("Bind the exact app and organization before configuring channels")
            if (
                not details
                or set(details) - CHANNEL_FIELDS
                or (set(details) & APNS_FIELDS and not APNS_FIELDS <= set(details))
            ):
                raise Invalid("Choose FCM or the complete APNs P8 configuration")
            for field, value in details.items():
                if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 16384:
                    raise Invalid("Channel field is invalid or too large")
            if "apns_env" in details and details["apns_env"] not in ("production", "development"):
                raise Invalid("Choose the APNs environment")
            if "fcm_v1_service_account_json" in details:
                try:
                    from .payment_signature import unique_pairs

                    service = json.loads(details["fcm_v1_service_account_json"], object_pairs_hook=unique_pairs)
                    if (
                        not isinstance(service, dict)
                        or service.get("type") != "service_account"
                        or not service.get("private_key")
                        or not service.get("client_email")
                    ):
                        raise ValueError()
                except (ValueError, TypeError):
                    raise Invalid("Enter the Firebase service account JSON") from None
            if "apns_p8" in details and "PRIVATE KEY" not in details["apns_p8"]:
                raise Invalid("Enter an APNs P8 private key")
            encoded_update(details)
            secret_ref = self.secrets.stage(app_id, principal, details)
            public = {
                key: ("PROTECTED_VALUE_SELECTED" if key in PRIVATE_FIELDS else value) for key, value in details.items()
            }
        packet = dict(
            schema="wmm.onesignal-setup.v1",
            action=action,
            app_id=app_id,
            owner=principal,
            role_version=role_version,
            app_version=app["version"],
            app_hash=digest(app["data"]),
            connection_version=row["version"],
            provider_app_id=row["provider_app_id"],
            organization_id=row["organization_id"],
            details=public,
            protected_stage=secret_ref,
            expires_at=(iso_time(now()) + timedelta(minutes=15)).isoformat(),
        )
        hashed = digest(packet)
        stamp = now()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current = connection_row(db, app_id, principal)
            if current["version"] != row["version"]:
                raise Invalid("Connection changed while preparing setup")
            if unresolved(db, app_id, principal):
                raise Invalid("Reconcile the pending OneSignal effect before preparing another")
            db.execute(
                "INSERT INTO onesignal_setup_effects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid(),
                    app_id,
                    principal,
                    request_key,
                    action,
                    canonical(packet),
                    hashed,
                    "PROPOSED",
                    secret_ref,
                    None,
                    None,
                    stamp,
                    stamp,
                ),
            )
            effect = db.execute(
                "SELECT id FROM onesignal_setup_effects WHERE app_id=? AND owner=? AND request_key=?",
                (app_id, principal, request_key),
            ).fetchone()
        return {"id": effect["id"], "proposal": packet, "source_hash": hashed, "status": "PROPOSED"}

    def _effect(self, db, app_id, principal, effect_id):
        uuid_text(effect_id)
        row = db.execute(
            "SELECT * FROM onesignal_setup_effects WHERE id=? AND app_id=? AND owner=?", (effect_id, app_id, principal)
        ).fetchone()
        if not row:
            raise Invalid("OneSignal setup effect is unavailable")
        result = dict(row)
        result["packet"] = json.loads(result["packet"])
        if digest(result["packet"]) != result["packet_hash"]:
            raise Invalid("OneSignal setup proposal integrity changed")
        if (
            result["packet"].get("action") != result["action"]
            or result["packet"].get("app_id") != app_id
            or result["packet"].get("owner") != principal
            or result["packet"].get("protected_stage") != result["secret_ref"]
        ):
            raise Invalid("OneSignal setup proposal binding changed")
        return result

    def _guard(self, app_id, principal, role_version, effect):
        packet = effect["packet"]
        app = self.store.app(app_id)
        if (
            packet["owner"] != principal
            or packet["role_version"] != role_version
            or packet["app_version"] != app["version"]
            or packet["app_hash"] != digest(app["data"])
        ):
            raise Invalid("OneSignal owner or app changed; prepare again")
        if iso_time(now()) > iso_time(packet["expires_at"]):
            raise Invalid("OneSignal setup approval expired")
        with connection(self.store.path) as db:
            row = connection_row(db, app_id, principal)
        if row["version"] != packet["connection_version"] or row["kind"] != "org":
            raise Invalid("OneSignal key or connection changed; prepare again")
        return row

    def execute(self, app_id, effect_id, source_hash, confirmed):
        principal, role_version = entry(
            self.store, app_id, "execute", {"effect_id": effect_id, "source_hash": source_hash, "confirmed": confirmed}
        )
        if confirmed is not True:
            raise Invalid("Approve the exact OneSignal setup proposal")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            effect = self._effect(db, app_id, principal, effect_id)
            if effect["packet_hash"] != source_hash:
                raise Invalid("OneSignal approval does not match the proposal")
            if effect["status"] != "PROPOSED":
                return {
                    "id": effect_id,
                    "status": effect["status"],
                    "next_action": "Inspect the saved effect; no automatic retry",
                }
            guarded = self._guard(app_id, principal, role_version, effect)
            if unresolved(db, app_id, principal, exclude=effect_id):
                raise Invalid("Reconcile the prior OneSignal effect first")
            key_text(self.secrets.load(app_id, principal, guarded["secret_ref"])["org_key"])
            if effect["secret_ref"]:
                staged = self.secrets.load(app_id, principal, effect["secret_ref"])
                masked = {
                    key: ("PROTECTED_VALUE_SELECTED" if key in PRIVATE_FIELDS else value)
                    for key, value in staged.items()
                }
                if masked != effect["packet"]["details"]:
                    raise Invalid("Protected channel setup differs from the reviewed proposal")
                encoded_update(staged)
            db.execute("UPDATE onesignal_setup_effects SET status='RESERVED',updated=? WHERE id=?", (now(), effect_id))
        dispatch_started = False
        try:
            row = self._guard(app_id, principal, role_version, effect)
            api_key = self.secrets.load(app_id, principal, row["secret_ref"])["org_key"]
            packet = effect["packet"]
            details = packet["details"]

            def alive():
                current, current_version = owner(self.store, app_id)
                if current != principal or current_version != role_version:
                    raise PermissionError("OneSignal owner changed")
                self._guard(app_id, principal, role_version, effect)

            sensitive = ()
            if effect["action"] == "create":
                found = self._read(app_id, principal)
                if any(
                    item["name"].casefold() == details["name"].casefold()
                    and item.get("organization_id") == details["organization_id"]
                    for item in found
                ):
                    raise Invalid("An app with this name now exists; inspect its exact identity")
                alive()
                dispatch_started = True
                response = self.transport("create", api_key, fields=details, alive=alive)
                response = safe_app(response)
                expected_org = details["organization_id"]
                expected_name = details["name"]
                identity = response["id"]
            else:
                identity = packet["provider_app_id"]
                expected_org = packet["organization_id"]
                expected_name = json.loads(row["data"])["name"]
                raw = self.secrets.load(app_id, principal, effect["secret_ref"])
                update = encoded_update(raw)
                sensitive = tuple(raw[k] for k in PRIVATE_FIELDS if k in raw) + tuple(
                    update[k] for k in PRIVATE_FIELDS if k in update
                )
                alive()
                dispatch_started = True
                response = safe_app(self.transport("update", api_key, identity, update, alive=alive))
            if (
                response["id"] != identity
                or response.get("organization_id") != expected_org
                or response["name"] != expected_name
            ):
                raise Invalid("OneSignal effect response identity does not match the reviewed app")
            with connection(self.store.path) as db:
                db.execute(
                    "UPDATE onesignal_setup_effects SET provider_app_id=?,updated=? WHERE id=? AND status='RESERVED'",
                    (identity, now(), effect_id),
                )
            found = [item for item in self._read(app_id, principal, sensitive=sensitive) if item["id"] == identity]
            if len(found) != 1 or found[0]["name"] != expected_name or found[0].get("organization_id") != expected_org:
                raise Invalid("OneSignal app readback does not match the reviewed identity")
            states = ["APP_BOUND"]
            if effect["action"] == "update":
                prior = json.loads(row["data"]).get("channel_states", [])
                if not isinstance(prior, list) or any(
                    state not in ("APNS_CONFIGURED_UNVERIFIED", "FCM_CONFIGURED_UNVERIFIED") for state in prior
                ):
                    raise Invalid("Saved OneSignal channel state is invalid")
                states.extend(prior)
                for key in (APNS_FIELDS - PRIVATE_FIELDS) | {"apns_env"}:
                    if key in details and found[0].get(key) != details[key]:
                        raise Invalid("OneSignal channel readback does not match the reviewed metadata")
                if "apns_p8" in details and "APNS_CONFIGURED_UNVERIFIED" not in states:
                    states.append("APNS_CONFIGURED_UNVERIFIED")
                if "fcm_v1_service_account_json" in details and "FCM_CONFIGURED_UNVERIFIED" not in states:
                    states.append("FCM_CONFIGURED_UNVERIFIED")
            result = {
                "states": states,
                "sdk": "SDK_BUILD_NOT_VERIFIED",
                "device": "DEVICE_SUBSCRIPTION_NOT_VERIFIED",
                "next_action": "Verify provider credentials, SDK build and a real device subscription",
            }
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                self._guard(app_id, principal, role_version, effect)
                db.execute(
                    "UPDATE onesignal_connections SET version=version+1,provider_app_id=?,organization_id=?,data=?,updated=? WHERE app_id=? AND owner=?",
                    (
                        identity,
                        expected_org,
                        canonical({"state": "APP_BOUND", "name": expected_name, "channel_states": states[1:]}),
                        now(),
                        app_id,
                        principal,
                    ),
                )
                db.execute(
                    "UPDATE onesignal_setup_effects SET status='SUCCEEDED',result=?,updated=? WHERE id=? AND status='RESERVED'",
                    (canonical(result), now(), effect_id),
                )
            return {"id": effect_id, "status": "SUCCEEDED", **result}
        except Exception:
            state = "UNKNOWN" if dispatch_started else "BLOCKED_NOT_SENT"
            try:
                with connection(self.store.path) as db:
                    db.execute(
                        "UPDATE onesignal_setup_effects SET status=?,updated=? WHERE id=? AND status='RESERVED'",
                        (state, now(), effect_id),
                    )
            except Exception:
                state = "RESERVED"
            return {
                "id": effect_id,
                "status": state,
                "next_action": (
                    "No provider mutation was sent; review a new proposal"
                    if state == "BLOCKED_NOT_SENT"
                    else "Inspect the provider and reconcile; no automatic retry"
                ),
            }

    def reconcile(self, app_id, effect_id, provider_app_id, expected_name, expected_org, confirmed):
        principal, role_version = entry(
            self.store,
            app_id,
            "reconcile",
            {
                "effect_id": effect_id,
                "provider_app_id": provider_app_id,
                "expected_name": expected_name,
                "expected_org": expected_org,
                "confirmed": confirmed,
            },
        )
        if confirmed is not True:
            raise Invalid("Confirm the exact app selection for reconciliation")
        uuid_text(provider_app_id)
        with connection(self.store.path) as db:
            effect = self._effect(db, app_id, principal, effect_id)
        if effect["status"] not in ("RESERVED", "UNKNOWN"):
            raise Invalid("Only unresolved setup can be reconciled")
        with connection(self.store.path) as db:
            if db.execute(
                "SELECT 1 FROM onesignal_recoveries WHERE effect_id=? AND status='RECOVERED_READBACK_ONLY'",
                (effect_id,),
            ).fetchone():
                raise Invalid("This OneSignal effect was already recovered")
        if effect["status"] == "RESERVED" and (iso_time(now()) - iso_time(effect["updated"])).total_seconds() < 120:
            raise Invalid("OneSignal effect may still be running; wait before reconciliation")
        self._reconcile_guard(app_id, principal, role_version, effect)
        if effect["provider_app_id"] and effect["provider_app_id"] != provider_app_id:
            raise Invalid("Choose the recorded OneSignal app ID")
        packet = effect["packet"]
        expected_packet_org = (
            packet["details"]["organization_id"] if effect["action"] == "create" else packet["organization_id"]
        )
        expected_packet_name = (
            packet["details"]["name"]
            if effect["action"] == "create"
            else json.loads(self._connection_for_reconcile(app_id, principal)["data"])["name"]
        )
        if expected_org != expected_packet_org or expected_name != expected_packet_name:
            raise Invalid("Select the exact reviewed organization and app identity")
        found = [
            item
            for item in self._read(
                app_id, principal, provider_app_id, sensitive=self._effect_private(app_id, principal, effect)
            )
            if item["id"] == provider_app_id
        ]
        if len(found) != 1 or found[0].get("organization_id") != expected_org or found[0]["name"] != expected_name:
            raise Invalid("OneSignal readback does not match this app")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            effect = self._effect(db, app_id, principal, effect_id)
            if effect["status"] not in ("RESERVED", "UNKNOWN"):
                raise Invalid("OneSignal effect changed during reconciliation")
            if db.execute(
                "SELECT 1 FROM onesignal_recoveries WHERE effect_id=? AND status='RECOVERED_READBACK_ONLY'",
                (effect_id,),
            ).fetchone():
                raise Invalid("This OneSignal effect was already recovered")
            if effect["status"] == "RESERVED" and (iso_time(now()) - iso_time(effect["updated"])).total_seconds() < 120:
                raise Invalid("OneSignal effect may still be running; wait before reconciliation")
            self._reconcile_guard(app_id, principal, role_version, effect)
            db.execute(
                "UPDATE onesignal_connections SET version=version+1,provider_app_id=?,organization_id=?,data=?,updated=? WHERE app_id=? AND owner=?",
                (
                    provider_app_id,
                    expected_org,
                    canonical({"state": "APP_BOUND", "name": expected_name}),
                    now(),
                    app_id,
                    principal,
                ),
            )
            receipt = dict(
                schema="wmm.onesignal-recovery-legacy.v1",
                effect_id=effect_id,
                effect_hash=effect["packet_hash"],
                provider_app_id=provider_app_id,
                provider_name=expected_name,
                organization_id=expected_org,
            )
            stamp = now()
            db.execute(
                "INSERT INTO onesignal_recoveries VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid(),
                    app_id,
                    principal,
                    effect_id,
                    canonical(receipt),
                    digest(receipt),
                    None,
                    "RECOVERED_READBACK_ONLY",
                    canonical({"provider_app_id": provider_app_id}),
                    stamp,
                    stamp,
                ),
            )
        return {
            "id": effect_id,
            "status": "RECONCILED_APP_SELECTED",
            "next_action": "Verify whether provider configuration succeeded; no creation or delivery is inferred",
        }

    def _connection_for_reconcile(self, app_id, principal):
        with connection(self.store.path) as db:
            return connection_row(db, app_id, principal)

    def _reconcile_guard(self, app_id, principal, role_version, effect):
        packet = effect["packet"]
        app = self.store.app(app_id)
        row = self._connection_for_reconcile(app_id, principal)
        if (
            packet["owner"] != principal
            or packet["role_version"] != role_version
            or packet["app_version"] != app["version"]
            or packet["app_hash"] != digest(app["data"])
            or packet["connection_version"] != row["version"]
        ):
            raise Invalid("OneSignal owner, app or connection changed; use a separately reviewed recovery")

    def _effect_private(self, app_id, principal, effect):
        if not effect["secret_ref"]:
            return ()
        values = self.secrets.load(app_id, principal, effect["secret_ref"])
        encoded = encoded_update(values)
        return tuple(values[k] for k in PRIVATE_FIELDS if k in values) + tuple(
            encoded[k] for k in PRIVATE_FIELDS if k in encoded
        )

    def _recovery_read(self, app_id, principal, kind, key, provider_app_id, sensitive=()):
        alive = lambda: owner(self.store, app_id)
        if kind == "app":
            rows = [self.transport("view", key, provider_app_id, alive=alive)]
        else:
            rows = self.transport("list", key, alive=alive)
        rows = [safe_app(row) for row in rows]
        self._reject_sensitive_metadata(rows, (key,) + tuple(sensitive))
        selected = [row for row in rows if row["id"] == provider_app_id]
        if len(selected) != 1:
            raise Invalid("Select an exact OneSignal app ID available to this key")
        return selected[0]

    def recovery_prepare(self, app_id, effect_id, provider_app_id, key_kind, key):
        body = {"effect_id": effect_id, "provider_app_id": provider_app_id, "key_kind": key_kind, "key": key}
        principal, role_version = entry(self.store, app_id, "recovery-prepare", body)
        uuid_text(provider_app_id)
        key_text(key)
        if key_kind not in ("app", "org"):
            raise Invalid("Choose an app or organization key for readback")
        with connection(self.store.path) as db:
            effect = self._effect(db, app_id, principal, effect_id)
            row = connection_row(db, app_id, principal)
            if db.execute(
                "SELECT 1 FROM onesignal_recoveries WHERE effect_id=? AND status='RECOVERED_READBACK_ONLY'",
                (effect_id,),
            ).fetchone():
                raise Invalid("This OneSignal effect was already recovered")
        if effect["status"] not in ("RESERVED", "UNKNOWN"):
            raise Invalid("Choose an unresolved OneSignal effect")
        if effect["status"] == "RESERVED" and (iso_time(now()) - iso_time(effect["updated"])).total_seconds() < 120:
            raise Invalid("OneSignal effect may still be running; wait before recovery")
        if effect["provider_app_id"] and effect["provider_app_id"] != provider_app_id:
            raise Invalid("Choose the recorded provider app ID")
        if effect["action"] == "update" and effect["packet"]["provider_app_id"] != provider_app_id:
            raise Invalid("Choose the reviewed provider app ID")
        readback = self._recovery_read(
            app_id, principal, key_kind, key, provider_app_id, self._effect_private(app_id, principal, effect)
        )
        expected_org = (
            effect["packet"]["details"]["organization_id"]
            if effect["action"] == "create"
            else effect["packet"]["organization_id"]
        )
        if readback.get("organization_id") != expected_org:
            raise Invalid("OneSignal organization differs from the original review")
        if effect["action"] == "create" and readback["name"] != effect["packet"]["details"]["name"]:
            raise Invalid("OneSignal app name differs from the original review")
        app = self.store.app(app_id)
        ref = self.secrets.stage(app_id, principal, {key_kind + "_key": key})
        stamp = now()
        packet = dict(
            schema="wmm.onesignal-recovery.v1",
            effect_id=effect_id,
            effect_hash=effect["packet_hash"],
            effect_status=effect["status"],
            effect_updated=effect["updated"],
            effect_action=effect["action"],
            original=dict(
                app_version=effect["packet"]["app_version"],
                app_hash=effect["packet"]["app_hash"],
                role_version=effect["packet"]["role_version"],
                connection_version=effect["packet"]["connection_version"],
            ),
            current=dict(
                app_version=app["version"],
                app_hash=digest(app["data"]),
                role_version=role_version,
                connection_version=row["version"],
                connection_hash=digest(row),
            ),
            provider_identity={k: readback.get(k) for k in ("id", "name", "organization_id")},
            key_kind=key_kind,
            protected_stage=ref,
            expires_at=(iso_time(stamp) + timedelta(minutes=15)).isoformat(),
        )
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            self._recovery_guard(db, app_id, principal, role_version, packet)
            db.execute(
                "INSERT INTO onesignal_recoveries VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid(),
                    app_id,
                    principal,
                    effect_id,
                    canonical(packet),
                    digest(packet),
                    ref,
                    "PROPOSED",
                    None,
                    stamp,
                    stamp,
                ),
            )
            recovery = db.execute(
                "SELECT id FROM onesignal_recoveries WHERE app_id=? AND owner=? AND secret_ref=?",
                (app_id, principal, ref),
            ).fetchone()
        return {"id": recovery["id"], "proposal": packet, "source_hash": digest(packet), "status": "PROPOSED"}

    def _recovery_guard(self, db, app_id, principal, role_version, packet):
        if packet.get("schema") != "wmm.onesignal-recovery.v1" or iso_time(now()) > iso_time(packet["expires_at"]):
            raise Invalid("OneSignal recovery review expired or changed")
        effect = self._effect(db, app_id, principal, packet["effect_id"])
        row = connection_row(db, app_id, principal)
        app = self.store.app(app_id)
        current = dict(
            app_version=app["version"],
            app_hash=digest(app["data"]),
            role_version=role_version,
            connection_version=row["version"],
            connection_hash=digest(row),
        )
        if (
            packet["current"] != current
            or packet["effect_hash"] != effect["packet_hash"]
            or packet["effect_status"] != effect["status"]
            or packet["effect_updated"] != effect["updated"]
            or effect["status"] not in ("RESERVED", "UNKNOWN")
        ):
            raise Invalid("OneSignal source or pending effect changed; review a new recovery")
        if effect["status"] == "RESERVED" and (iso_time(now()) - iso_time(effect["updated"])).total_seconds() < 120:
            raise Invalid("OneSignal effect may still be running")
        if db.execute(
            "SELECT 1 FROM onesignal_recoveries WHERE effect_id=? AND status='RECOVERED_READBACK_ONLY'", (effect["id"],)
        ).fetchone():
            raise Invalid("This OneSignal effect was already recovered")

    def recovery_confirm(self, app_id, recovery_id, source_hash, confirmed):
        principal, role_version = entry(
            self.store,
            app_id,
            "recovery-confirm",
            {"recovery_id": recovery_id, "source_hash": source_hash, "confirmed": confirmed},
        )
        if confirmed is not True:
            raise Invalid("Approve the exact recovery readback")
        uuid_text(recovery_id)
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT * FROM onesignal_recoveries WHERE id=? AND app_id=? AND owner=?",
                (recovery_id, app_id, principal),
            ).fetchone()
            if not row:
                raise Invalid("OneSignal recovery is unavailable")
            if row["packet_hash"] != source_hash:
                raise Invalid("OneSignal recovery approval changed")
            if row["status"] == "RECOVERED_READBACK_ONLY":
                return {
                    "id": recovery_id,
                    "status": row["status"],
                    "next_action": "Inspect the original uncertain effect; no mutation was retried",
                }
            packet = json.loads(row["packet"])
            if row["status"] != "PROPOSED" or row["packet_hash"] != source_hash or digest(packet) != source_hash:
                raise Invalid("OneSignal recovery approval changed")
            if packet.get("protected_stage") != row["secret_ref"] or packet.get("effect_id") != row["effect_id"]:
                raise Invalid("OneSignal recovery credential binding changed")
            self._recovery_guard(db, app_id, principal, role_version, packet)
            effect = self._effect(db, app_id, principal, packet["effect_id"])
        key = self.secrets.load(app_id, principal, row["secret_ref"])[packet["key_kind"] + "_key"]
        readback = self._recovery_read(
            app_id,
            principal,
            packet["key_kind"],
            key,
            packet["provider_identity"]["id"],
            self._effect_private(app_id, principal, effect),
        )
        if {k: readback.get(k) for k in ("id", "name", "organization_id")} != packet["provider_identity"]:
            raise Invalid("OneSignal app changed since the reviewed recovery")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            self._recovery_guard(db, app_id, principal, role_version, packet)
            changed = db.execute(
                "UPDATE onesignal_recoveries SET status='RECOVERED_READBACK_ONLY',result=?,updated=? WHERE id=? AND status='PROPOSED' AND packet_hash=?",
                (canonical({"provider_identity": packet["provider_identity"]}), now(), recovery_id, source_hash),
            ).rowcount
            if changed != 1:
                raise Invalid("OneSignal recovery changed; refresh")
        return {
            "id": recovery_id,
            "status": "RECOVERED_READBACK_ONLY",
            "next_action": "Inspect the original uncertain effect; no mutation was retried or inferred successful",
        }
