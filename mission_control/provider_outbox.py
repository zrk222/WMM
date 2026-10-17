"""Durable exact provider changes with one dispatch and read-only uncertain recovery."""
from datetime import datetime, timedelta, timezone
import json
import time
from .common import Invalid, canonical, digest, now, uid
from .db import connection
from .store import audit
from .review_access import member
from .action_contract import sources, current, find, load, connection_row
from . import store_actions


def binding(store, app_id, row):
    """Add the trusted runtime vault namespace without persisting credentials."""
    from .credential_vault import namespace
    return {**row["data"], "_vault_namespace": namespace(store.path)}


def observe(store, app_id, packet, conn=None):
    """Read a sanitized actual baseline through the finite production adapter."""
    target = packet["before"]
    return store_actions.baseline(binding(store, app_id, conn or packet["connection"]), app_id, target["localization_id"], target["release"], target["locale"])


def event(db, row, state, detail):
    """Append a hashed immutable receipt and persist the resulting action state."""
    data = {"state": state, "detail": detail, "observed_at": now()}
    db.execute("INSERT INTO provider_action_events(action_id,data,hash,created) VALUES(?,?,?,?)", (row["id"], canonical(data), digest(data), now()))
    db.execute("UPDATE provider_actions SET status=?,updated=? WHERE id=? AND app_id=?", (state, now(), row["id"], row["app_id"]))
    audit(db, row["app_id"], "provider_action."+state.lower(), {"id": row["id"], "receipt_hash": digest(data)})


def checked_body(body, confirmation):
    """Require an exact packet hash and literal explicit-action confirmation."""
    if set(body) != {"hash", confirmation} or body[confirmation] is not True or not isinstance(body["hash"], str):
        raise Invalid("Inspect the exact hash and explicitly confirm this provider action")


def view(db, row):
    """Keep exact old receipts addressable even after they leave the latest-100 list."""
    item = dict(row); item["packet"] = json.loads(item["packet"])
    item["events"] = [{**dict(r), "data": json.loads(r["data"])} for r in db.execute("SELECT * FROM provider_action_events WHERE action_id=? ORDER BY id", (row["id"],))]
    for receipt in item["events"]:
        if digest(receipt["data"]) != receipt["hash"]: raise Invalid("Provider action receipt integrity changed")
    try: current(db, row); item["availability"] = "CURRENT"; item["unavailable_reason"] = None
    except (Invalid, PermissionError, KeyError, ValueError) as exc: item["availability"] = "UNAVAILABLE"; item["unavailable_reason"] = str(exc)
    return item


class Outbox:
    def __init__(self, store): self.store = store

    def list(self, app_id):
        """Expose bounded durable states and current availability without fabricating effects."""
        self.store.app(app_id); result = []
        with connection(self.store.path) as db:
            for row in db.execute("SELECT * FROM provider_actions WHERE app_id=? ORDER BY created DESC LIMIT 100", (app_id,)):
                result.append(view(db, row))
        return result

    def get(self, app_id, identity):
        """Resolve one app-owned action including its durable receipt history."""
        self.store.app(app_id)
        with connection(self.store.path) as db: return view(db, find(db, app_id, identity))

    def destination(self, app_id, user, body):
        """Guide destination discovery without granting any mutation authority."""
        if set(body) != {"record_id", "connection_id"}: raise Invalid("Choose store evidence and its App Store connection")
        self.store.app(app_id)
        with connection(self.store.path) as db:
            member(db, app_id, user["principal"], "MAKER")
            _, manifest, _, conn = sources(db, app_id, body["record_id"], body["connection_id"])
        return store_actions.discover(binding(self.store, app_id, conn), app_id, manifest["release"], manifest["locale"])

    def prepare(self, app_id, user, body):
        """Freeze exact actual remote state and current approved source under maker identity."""
        if set(body) != {"record_id", "connection_id", "localization_id"}:
            raise Invalid("Choose store evidence, a connection and the localization resource ID")
        self.store.app(app_id)
        with connection(self.store.path) as db:
            role = member(db, app_id, user["principal"], "MAKER")
            version, manifest, record, conn = sources(db, app_id, body["record_id"], body["connection_id"])
        text = store_actions.copy_text(record["data"].get("promotional_text"))
        before = store_actions.baseline(binding(self.store, app_id, conn), app_id, body["localization_id"], manifest["release"], manifest["locale"])
        packet = {"operation": "APP_STORE_PROMOTIONAL_TEXT", "app_id": app_id, "manifest_version": version, "record": record, "connection": conn,
                  "maker_role_version": role["version"], "preparer": user["principal"], "before": before, "after": {**before, "promotional_text": text}, "authorized_spend_minor": 0}
        identity = uid(); expiry = (datetime.now(timezone.utc)+timedelta(hours=24)).isoformat()
        packet["expires"] = expiry
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            target_key = before["store_app_id"]+":"+before["localization_id"]
            db.execute("INSERT INTO provider_actions(id,app_id,target_key,packet,hash,preparer,status,expires,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?)", (identity, app_id, target_key, canonical(packet), digest(packet), user["principal"], "WAITING_APPROVAL", expiry, now(), now()))
            row = find(db, app_id, identity); current(db, row)
            event(db, row, "WAITING_APPROVAL", {"principal": user["principal"], "provider_write": "NOT_RUN"})
        return self.get(app_id, identity)

    def approve(self, app_id, identity, user, body):
        """Authorize only exact independently inspected changes and explicit provider effect."""
        checked_body(body, "confirm_provider_change")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE"); row = find(db, app_id, identity)
            role = member(db, app_id, user["principal"], "CHECKER"); current(db, row)
            if row["status"] != "WAITING_APPROVAL" or row["hash"] != body["hash"] or row["preparer"] == user["principal"]:
                raise Invalid("This exact action requires a different checker and cannot be replayed")
            db.execute("UPDATE provider_actions SET checker=?,checker_role_version=? WHERE id=?", (user["principal"], role["version"], identity))
            event(db, row, "APPROVED", {"principal": user["principal"], "authorized_spend_minor": 0, "provider_write": "NOT_RUN"})
        return self.get(app_id, identity)

    def claim(self, app_id, identity, user, body, remote):
        """Commit ownership before the only write; compare preflight inside final authorization."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE"); row = find(db, app_id, identity); packet = current(db, row)
            member(db, app_id, user["principal"], "MAKER")
            if row["status"] != "APPROVED" or not row["checker"] or row["dispatches"] or row["preparer"] != user["principal"] or row["hash"] != body["hash"]:
                raise Invalid("Only the original maker may send this approved action once")
            if remote == packet["after"]:
                event(db, row, "ALREADY_DESIRED", {"provider_write": "NOT_RUN", "attribution": "UNPROVEN"}); return False
            if remote != packet["before"]:
                event(db, row, "BASELINE_CHANGED", {"provider_write": "NOT_RUN", "observation": remote}); return False
            if db.execute("SELECT 1 FROM provider_actions WHERE target_key=? AND status='DISPATCHING'", (row["target_key"],)).fetchone():
                raise Invalid("Another action owns this destination; inspect its outcome before sending")
            owner = uid()
            db.execute("UPDATE provider_actions SET dispatches=1,lease=?,owner=? WHERE id=?", (time.time()+90, owner, identity))
            event(db, row, "DISPATCHING", {"principal": user["principal"], "dispatch_number": 1})
        return owner

    def execute(self, app_id, identity, user, body):
        """Preflight, atomically claim, write once and verify actual provider readback."""
        checked_body(body, "confirm_send"); row, packet = load(self.store, app_id, identity)
        if row["status"] != "APPROVED" or row["preparer"] != user["principal"] or row["hash"] != body["hash"]:
            raise Invalid("Only the original authenticated maker may explicitly send an approved action")
        remote = observe(self.store, app_id, packet)
        owner = self.claim(app_id, identity, user, body, remote)
        if not owner: return self.get(app_id, identity)
        acknowledged = False
        try:
            load(self.store, app_id, identity)
            store_actions.apply(binding(self.store, app_id, packet["connection"]), app_id, packet["before"], packet["after"]["promotional_text"])
            acknowledged = True
        except Exception:
            pass  # Any post-claim failure is uncertain; never resend or persist raw secrets.
        return self.readback(app_id, identity, packet, packet["connection"], owner, acknowledged)

    def readback(self, app_id, identity, packet, conn, owner, acknowledged=False):
        """Persist sanitized observed state; equality is not attribution or public availability."""
        try:
            remote = observe(self.store, app_id, packet, conn)
            outcome = "OBSERVED_DESIRED" if remote == packet["after"] else "OBSERVED_BASELINE" if remote == packet["before"] else "OBSERVED_DIFFERENT"
            detail = {"outcome": outcome, "observation": remote, "attribution": "ACKNOWLEDGED_WRITE" if acknowledged else "UNPROVEN", "public_availability": "NOT_VERIFIED"}
            state = "VERIFIED_APPLIED" if outcome == "OBSERVED_DESIRED" else "NEEDS_RECONCILIATION"
        except Exception:
            state = "NEEDS_RECONCILIATION"; detail = {"outcome": "READ_UNAVAILABLE", "attribution": "UNPROVEN", "next_action": "Read provider state again; do not resend this action"}
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE"); row = find(db, app_id, identity)
            if row["owner"] != owner or row["status"] != "DISPATCHING":
                raise Invalid("A newer reconciliation owns this outcome; reload its receipt")
            event(db, row, state, detail); db.execute("UPDATE provider_actions SET lease=0 WHERE id=?", (identity,))
        return self.get(app_id, identity)

    def reconcile(self, app_id, identity, user, body):
        """Recover ambiguous dispatch using only reads under current app membership."""
        if body: raise Invalid("Readback takes no new mutation instructions")
        row, packet = load(self.store, app_id, identity, False)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE"); row = find(db, app_id, identity)
            member(db, app_id, user["principal"])
            if row["status"] not in ("DISPATCHING", "NEEDS_RECONCILIATION") or row["lease"] > time.time():
                raise Invalid("Wait for the active dispatch lease before read-only reconciliation")
            conn = connection_row(db, app_id, packet["connection"]["id"])
            if conn["data"].get("store_app_id") != packet["before"]["store_app_id"]:
                raise Invalid("Current connection no longer identifies the approved app")
            other = db.execute("SELECT id FROM provider_actions WHERE target_key=? AND status='DISPATCHING' AND id<>?", (row["target_key"], identity)).fetchone()
            if other: raise Invalid("Another action owns this destination; wait for its outcome")
            owner = uid()
            db.execute("UPDATE provider_actions SET lease=?,owner=? WHERE id=?", (time.time()+90, owner, identity))
            event(db, row, "DISPATCHING", {"operation": "READ_ONLY_RECONCILIATION", "principal": user["principal"]})
        return self.readback(app_id, identity, packet, conn, owner)

    def cancel(self, app_id, identity, user, body):
        """Cancel only unsent work under the original active maker; never undo a remote effect."""
        if body: raise Invalid("Cancellation takes no mutation instructions")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE"); row = find(db, app_id, identity)
            member(db, app_id, user["principal"], "MAKER")
            if row["preparer"] != user["principal"] or row["status"] not in ("WAITING_APPROVAL", "APPROVED") or row["dispatches"]:
                raise Invalid("Only an unsent action can be cancelled by its original maker")
            event(db, row, "CANCELLED", {"principal": user["principal"], "provider_write": "NOT_RUN"})
        return self.get(app_id, identity)
