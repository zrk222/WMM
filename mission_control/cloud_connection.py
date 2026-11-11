"""Optional personal-cloud connection; local mode is the default and never requires it."""
from __future__ import annotations

from .cloud_ingest import CloudIngest, IngestError, validate_endpoint
from .common import Invalid, now, uid
from .credential_vault import Vault, namespace, target
from .db import connection

PROVIDER = "personal_cloud"
STATUSES = ("CONFIGURED_UNTESTED", "TESTED", "FAILED")


def _name(store, app_id, reference):
    return target(namespace(store.path), app_id, PROVIDER, reference)


def _public(row):
    if row is None:
        return {"mode": "LOCAL", "status": "LOCAL", "endpoint": None, "last_test": None,
                "last_error": None, "version": None}
    return {"mode": "PERSONAL_CLOUD", "status": row["status"], "endpoint": row["endpoint"],
            "last_test": row["last_test"], "last_error": row["last_error"], "version": row["version"]}


class CloudConnections:
    def __init__(self, store, vault=None):
        self.store = store
        self._vault = vault

    @property
    def vault(self):
        if self._vault is None:
            self._vault = Vault()
        return self._vault

    def current(self, app_id):
        self.store.app(app_id)
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM cloud_connections WHERE app_id=?", (app_id,)).fetchone()
        return _public(row)

    def save(self, app_id, owner, body):
        """Store an optional endpoint and write-only token; local behavior is unchanged."""
        self.store.app(app_id)
        if not isinstance(owner, dict) or not isinstance(owner.get("principal"), str) or not owner["principal"]:
            raise PermissionError("A verified owner is required")
        if not isinstance(body, dict) or set(body) - {"endpoint", "token"} or "endpoint" not in body:
            raise Invalid("Use the exact cloud connection fields")
        endpoint = validate_endpoint(body["endpoint"])
        token = body.get("token", "")
        if token != "" and (not isinstance(token, str) or not 8 <= len(token) <= 4096
                            or "\n" in token or "\r" in token):
            raise Invalid("Enter a valid cloud token")
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM cloud_connections WHERE app_id=?", (app_id,)).fetchone()
        reference = uid()
        previous = row["credential_ref"] if row else None
        if token or previous is None:
            if not token:
                raise Invalid("Enter the cloud token to connect")
            self.vault.put(_name(self.store, app_id, reference), {"token": token})
        else:
            reference = previous
        try:
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE")
                version = (row["version"] + 1) if row else 1
                db.execute("INSERT INTO cloud_connections VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(app_id) DO UPDATE SET "
                           "endpoint=excluded.endpoint,credential_ref=excluded.credential_ref,status=excluded.status,"
                           "last_test=excluded.last_test,last_error=excluded.last_error,version=excluded.version,updated=excluded.updated",
                           (app_id, endpoint, reference, "CONFIGURED_UNTESTED", None, None, version, now(), now()))
        except Exception:
            if token:
                try:
                    self.vault.delete(_name(self.store, app_id, reference))
                except Invalid:
                    pass
            raise
        if token and previous and previous != reference:
            try:
                self.vault.delete(_name(self.store, app_id, previous))
            except Invalid:
                pass
        return self.current(app_id)

    def test(self, app_id):
        """Test token/contract only; no evidence is sent and failures stay explicit."""
        current = self.current(app_id)
        if current["mode"] == "LOCAL":
            raise Invalid("No personal cloud connection is configured; WMM is running locally.")
        with connection(self.store.path) as db:
            row = db.execute("SELECT * FROM cloud_connections WHERE app_id=?", (app_id,)).fetchone()
        secret = self.vault.get(_name(self.store, app_id, row["credential_ref"]))
        if not secret or not isinstance(secret.get("token"), str):
            self._set_status(app_id, "FAILED", "Protected token is unavailable; reconnect")
            raise Invalid("Protected cloud token is unavailable; reconnect.")
        try:
            value = CloudIngest(row["endpoint"], secret["token"]).health()
        except (IngestError, ValueError) as exc:
            self._set_status(app_id, "FAILED", type(exc).__name__)
            raise Invalid("Cloud connection test failed: " + type(exc).__name__) from None
        self._set_status(app_id, "TESTED", None)
        return {"status": "TESTED", "tenant": value.get("tenant"), "version": value.get("version")}

    def _set_status(self, app_id, status, error):
        with connection(self.store.path) as db:
            db.execute("UPDATE cloud_connections SET status=?,last_test=?,last_error=?,updated=? WHERE app_id=?",
                       (status, now() if status == "TESTED" else None, error, now(), app_id))

    def remove(self, app_id):
        """Return to local mode and delete the protected token; no provider revocation."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            row = db.execute("SELECT credential_ref FROM cloud_connections WHERE app_id=?", (app_id,)).fetchone()
            db.execute("DELETE FROM cloud_connections WHERE app_id=?", (app_id,))
        if row:
            try:
                self.vault.delete(_name(self.store, app_id, row["credential_ref"]))
            except Invalid:
                return {"mode": "LOCAL", "status": "LOCAL", "cleanup": "TOKEN_CLEANUP_REQUIRED"}
        return {"mode": "LOCAL", "status": "LOCAL", "cleanup": "REMOVED"}
