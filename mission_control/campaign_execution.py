"""Durable owner-scoped Meta Page and finite paid campaign execution."""

import json
import sqlite3
from contextvars import ContextVar
from datetime import datetime, timezone
from .common import Invalid, canonical, digest, iso_time, now, uid
from .db import connection
from .review_access import member
from .social_connections import Connections
from .social_profiles import facebook, selected_page
from .campaign_contract import scope_data, post_data, ad_data
from .campaign_transport import MetaTransport, Unconfirmed
from .campaign_locks import paid_lock, CampaignLockBusy
from .campaign_destination import check_destination

PAID_EXECUTION_READY = (
    True  # Protected gateway, recovery tests and focused ECC review passed; live acceptance is separate.
)
SAFETY_CALL_LIMIT = 160
RECOVERING_PAID = ContextVar("wmm_campaign_paid_recovery", default=False)

SCHEMA = """
CREATE TABLE IF NOT EXISTS campaign_scopes (
 app_id TEXT NOT NULL, id TEXT NOT NULL, owner TEXT NOT NULL, owner_version INTEGER NOT NULL,
 summary TEXT NOT NULL, summary_hash TEXT NOT NULL, status TEXT NOT NULL,
 calls INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL, updated TEXT NOT NULL,
 PRIMARY KEY(app_id,id));
CREATE TABLE IF NOT EXISTS campaign_intents (
 app_id TEXT NOT NULL, id TEXT NOT NULL, scope_id TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, content_hash TEXT NOT NULL, rights_hash TEXT NOT NULL,
 page_id TEXT NOT NULL, status TEXT NOT NULL, remote_id TEXT, result TEXT,
 created TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(app_id,id),
 UNIQUE(app_id,request_id), UNIQUE(app_id,page_id,content_hash,rights_hash));
CREATE TABLE IF NOT EXISTS campaign_paid_intents (
 app_id TEXT NOT NULL, id TEXT NOT NULL, scope_id TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, account_id TEXT NOT NULL, currency TEXT NOT NULL,
 commitment INTEGER NOT NULL, data TEXT NOT NULL, ids TEXT NOT NULL, status TEXT NOT NULL,
 result TEXT, created TEXT NOT NULL, updated TEXT NOT NULL,
 PRIMARY KEY(app_id,id), UNIQUE(app_id,request_id));
CREATE TABLE IF NOT EXISTS campaign_stop_requests (app_id TEXT NOT NULL, intent_id TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,intent_id));
CREATE TABLE IF NOT EXISTS campaign_paid_leases (app_id TEXT NOT NULL, intent_id TEXT NOT NULL, step TEXT NOT NULL, owner_token TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(app_id,intent_id));
CREATE TABLE IF NOT EXISTS campaign_safety_calls (app_id TEXT NOT NULL, scope_id TEXT NOT NULL, category TEXT NOT NULL, used INTEGER NOT NULL, PRIMARY KEY(app_id,scope_id,category));
CREATE TABLE IF NOT EXISTS campaign_pause_receipts (
 app_id TEXT NOT NULL, intent_id TEXT NOT NULL, hash TEXT NOT NULL, data TEXT NOT NULL,
 observed_at TEXT NOT NULL, PRIMARY KEY(app_id,intent_id,hash));
"""

EFFECTIVE_STATUSES = frozenset(
    (
        "ACTIVE",
        "PAUSED",
        "DELETED",
        "PENDING_REVIEW",
        "DISAPPROVED",
        "PREAPPROVED",
        "PENDING_BILLING_INFO",
        "CAMPAIGN_PAUSED",
        "ARCHIVED",
        "ADSET_PAUSED",
        "IN_PROCESS",
        "WITH_ISSUES",
    )
)


def pause_receipt_data(intent, observed):
    """Keep only the exact identity and status fields from a confirmed pause read."""
    ids = json.loads(intent["ids"]) if isinstance(intent["ids"], str) else intent["ids"]
    if (
        not isinstance(observed, dict)
        or observed.get("id") != ids.get("campaign")
        or str(observed.get("account_id")) != intent["account_id"]
        or observed.get("status") != "PAUSED"
    ):
        raise Invalid("Pause observation differs from the saved campaign")
    effective = observed.get("effective_status")
    if not isinstance(effective, str) or effective not in EFFECTIVE_STATUSES:
        effective = None
    return dict(
        schema="wmm.campaign-pause-readback.v1",
        app_id=intent["app_id"],
        intent_id=intent["id"],
        scope_id=intent["scope_id"],
        request_hash=intent["request_hash"],
        campaign_id=ids["campaign"],
        account_id=intent["account_id"],
        configured_status="PAUSED",
        effective_status=effective,
        observed_at=now(),
    )


def saved_pause_receipt(db, intent):
    """Read a retained pause observation independently of later reconciliation."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='campaign_pause_receipts'").fetchone():
        return None
    row = db.execute(
        "SELECT hash,data,observed_at FROM campaign_pause_receipts "
        "WHERE app_id=? AND intent_id=? ORDER BY observed_at DESC,rowid DESC LIMIT 1",
        (intent["app_id"], intent["id"]),
    ).fetchone()
    if row is None:
        return None
    try:
        receipt = json.loads(row["data"])
        expected = pause_receipt_data(
            intent,
            dict(
                id=receipt["campaign_id"],
                account_id=receipt["account_id"],
                status=receipt["configured_status"],
                effective_status=receipt["effective_status"],
            ),
        )
        expected["observed_at"] = iso_time(receipt["observed_at"]).isoformat()
        if receipt != expected or receipt["observed_at"] != row["observed_at"] or digest(receipt) != row["hash"]:
            raise Invalid("Saved pause receipt failed integrity validation")
    except (KeyError, ValueError, TypeError, AttributeError):
        raise Invalid("Saved pause receipt failed integrity validation") from None
    return dict(receipt, sha256=row["hash"])


def row_scope(row):
    if row is None:
        raise Invalid("Campaign scope was not found")
    value = json.loads(row["summary"])
    return dict(
        value,
        scope_id=row["id"],
        approval_hash=row["summary_hash"],
        status=row["status"],
        call_allowance_units_used=row["calls"],
        allowance_note="Provider boundary checks are conservatively charged; some read requests use two units.",
    )


def scope_expiry(db, row, scope):
    from .authority_expiry import effective_expiry, initial_base

    base = initial_base(scope["expires_at"], row["created"], scope.get("extended_expiry_consent"))
    return effective_expiry(db, "CAMPAIGN", row, base)


def scope_view(db, row):
    """Expose the effective clock separately from the original reviewed scope."""
    scope = row_scope(row)
    proof = scope_expiry(db, row, scope)
    return dict(scope, permission_expires_at=proof["expires"], consent_revision=proof["revision"])


def check_campaign_saved_connection(saved, scope):
    if (
        not saved
        or saved["version"] != scope["connection_version"]
        or saved["status"] != "CONNECTED_READ_TESTED"
        or saved["provider"] != "facebook"
        or saved["lease"]
    ):
        raise PermissionError("Facebook connection changed or became unavailable")
    if saved["expires"] is not None and saved["expires"] <= datetime.now(timezone.utc).timestamp():
        raise PermissionError("Facebook connection expired")
    if json.loads(saved["data"])["destination"]["id"] != scope["page_id"]:
        raise PermissionError("Facebook Page changed")


def check_campaign_connection(db, app_id, scope):
    saved = db.execute(
        "SELECT version,status,provider,config_version,expires,lease,data FROM social_connections WHERE app_id=? AND id=?",
        (app_id, scope["connection_id"]),
    ).fetchone()
    check_campaign_saved_connection(saved, scope)
    config = db.execute(
        "SELECT version,status FROM social_configs WHERE app_id=? AND provider='facebook'", (app_id,)
    ).fetchone()
    if not config or config["version"] != saved["config_version"] or config["status"] == "DISCONNECTED":
        raise PermissionError("Facebook developer configuration changed")


def check_campaign_app(db, app_id, actor, scope, action):
    owner = member(db, app_id, scope["owner_principal"], "OWNER")
    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    protective_owner = actor == scope["owner_principal"] and action in ("PAUSE", "REVOKE", "RECONCILE")
    if app is None:
        raise PermissionError("App workspace is unavailable")
    if not protective_owner:
        if owner["version"] != scope["owner_version"]:
            raise PermissionError("Owner membership changed")
        if app["version"] != scope["app_version"] or digest(json.loads(app["data"])) != scope["app_hash"]:
            raise PermissionError("App manifest changed; prepare a new scope")


def check_ad_scope(scope, body):
    for name in ("content", "rights", "targeting"):
        if body[name + "_hash"] not in scope["approved_" + name + "_hashes"]:
            raise PermissionError("Campaign content, rights or targeting is outside scope")


def check_ad_limits(db, row, scope, body):
    if not scope["ad_account_id"]:
        raise PermissionError("Scope has no advertising account")
    check_ad_scope(scope, body)
    if iso_time(body["end_time"]) > iso_time(scope_expiry(db, row, scope)["expires"]):
        raise Invalid("Campaign must end within the approved scope")
    budget = body["lifetime_budget_minor"]
    if budget > scope["max_campaign_minor"]:
        raise PermissionError("Campaign budget exceeds the approved per-campaign amount")
    return budget


def row_intent(row):
    if row is None:
        raise Invalid("Campaign intent was not found")
    return {
        key: row[key]
        for key in (
            "id",
            "scope_id",
            "request_id",
            "request_hash",
            "content_hash",
            "rights_hash",
            "page_id",
            "status",
            "remote_id",
            "created",
            "updated",
        )
    } | {"result": json.loads(row["result"]) if row["result"] else None}


def paid_view(row):
    if row is None:
        raise Invalid("Paid campaign intent was not found")
    value = {
        key: row[key]
        for key in (
            "id",
            "scope_id",
            "request_id",
            "request_hash",
            "account_id",
            "currency",
            "commitment",
            "status",
            "created",
            "updated",
        )
    }
    value.update(
        kind="AD",
        data=json.loads(row["data"]),
        ids=json.loads(row["ids"]),
        result=json.loads(row["result"]) if row["result"] else None,
    )
    return value


class CampaignExecutionService:
    def __init__(self, store, policy_checker, transport=None):
        if not callable(policy_checker):
            raise TypeError("A trusted policy checker is required")
        self.store = store
        self.policy_checker = policy_checker
        self.transport = transport or MetaTransport()
        self.connections = Connections(store)
        with connection(store.path) as db:
            db.executescript(SCHEMA)

    def _row(self, db, app_id, scope_id):
        return db.execute("SELECT * FROM campaign_scopes WHERE app_id=? AND id=?", (app_id, scope_id)).fetchone()

    def get_scope(self, app_id, scope_id):
        with connection(self.store.path) as db:
            scope = scope_view(db, self._row(db, app_id, scope_id))
            rows = db.execute(
                "SELECT category,used FROM campaign_safety_calls WHERE app_id=? AND scope_id=?", (app_id, scope_id)
            ).fetchall()
        used = {row["category"]: row["used"] for row in rows}
        scope["safety_allowance"] = {
            category: dict(used=used.get(category, 0), limit=SAFETY_CALL_LIMIT)
            for category in ("PAUSE", "RECONCILE", "RECOVERY")
        }
        return scope

    def list_scopes(self, app_id, owner, limit=50):
        """Return owner-filtered history; the trusted dispatcher authorizes owner."""
        if type(limit) is not int or not 1 <= limit <= 50:
            raise Invalid("Use a history limit from 1 to 50")
        with connection(self.store.path) as db:
            rows = db.execute(
                "SELECT * FROM campaign_scopes WHERE app_id=? AND owner=? ORDER BY created DESC LIMIT ?",
                (app_id, owner, limit),
            ).fetchall()
            return [scope_view(db, row) for row in rows]

    def tracked_posts(self, app_id, owner, link_hash):
        """Read verified canonical Page receipts with the exact retained link binding."""
        with connection(self.store.path) as db:
            member(db, app_id, owner, "OWNER")
            rows = db.execute(
                """
                SELECT i.id,i.page_id,i.remote_id FROM campaign_intents i
                JOIN campaign_scopes s ON s.app_id=i.app_id AND s.id=i.scope_id
                WHERE i.app_id=? AND s.owner=? AND i.status='VERIFIED' AND i.remote_id IS NOT NULL
                  AND CASE WHEN json_valid(i.result)
                      THEN json_extract(i.result,'$.destination_check.approved_link_sha256')
                      END=?
                ORDER BY i.updated DESC,i.id LIMIT 101""",
                (app_id, owner, link_hash),
            ).fetchall()
        return {"records": [dict(row) for row in rows[:100]], "complete": len(rows) <= 100}

    def list_intents(self, app_id, scope_id):
        self.get_scope(app_id, scope_id)
        with connection(self.store.path) as db:
            posts = [
                row_intent(row)
                for row in db.execute(
                    "SELECT * FROM campaign_intents WHERE app_id=? AND scope_id=? ORDER BY created", (app_id, scope_id)
                )
            ]
            ads = []
            for row in db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? ORDER BY created", (app_id, scope_id)
            ):
                ads.append(dict(paid_view(row), pause_readback=saved_pause_receipt(db, row)))
        return posts + ads

    def _check(self, db, app_id, actor, scope, action, active=True):
        row = self._row(db, app_id, scope["scope_id"])
        if row is None or digest(json.loads(row["summary"])) != row["summary_hash"]:
            raise PermissionError("Campaign authority is unavailable or changed")
        expiry = scope_expiry(db, row, scope)["expires"]
        if active and (row["status"] != "ACTIVE" or iso_time(expiry) <= datetime.now(timezone.utc)):
            raise PermissionError("Campaign approval is OFF or expired")
        check_campaign_app(db, app_id, actor, scope, action)
        check_campaign_connection(db, app_id, scope)
        self.policy_checker(app_id, actor, scope, action)

    def prepare_scope(self, app_id, owner, body):
        proposal = scope_data(body)
        app = self.store.app(app_id)
        selected = self.connections.get(app_id, proposal["connection_id"])
        self.connections.alive(selected)
        if selected["provider"] != "facebook" or selected["data"]["destination"]["id"] != proposal["page_id"]:
            raise Invalid("Select the saved Facebook Page connection")
        identity = uid()
        principal = owner
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            role = member(db, app_id, principal, "OWNER")
            summary = dict(
                proposal,
                app_id=app_id,
                app_hash=digest(app["data"]),
                app_version=app["version"],
                owner_principal=principal,
                owner_version=role["version"],
                connection_version=selected["version"],
                billing_notice="Media budget excludes taxes, fees and foreign exchange; provider billing may lag.",
                rights_notice="Rights hashes are owner attestations, not proof of rights.",
            )
            temp = dict(summary, scope_id=identity)
            self.policy_checker(app_id, owner, temp, "PREPARE")
            stamp = now()
            db.execute(
                "INSERT INTO campaign_scopes VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    app_id,
                    identity,
                    principal,
                    role["version"],
                    canonical(summary),
                    digest(summary),
                    "DRAFT",
                    0,
                    stamp,
                    stamp,
                ),
            )
        return self.get_scope(app_id, identity)

    def _alive(self, app_id, actor, scope_id, action, active=True):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, app_id, scope_id)
            scope = row_scope(row)
            self._check(db, app_id, actor, scope, action, active)
            category = (
                "PAUSE"
                if action in ("PAUSE", "REVOKE")
                else (("RECOVERY" if RECOVERING_PAID.get() else "RECONCILE") if action == "RECONCILE" else None)
            )
            if category:
                self._safety_admit(db, app_id, scope_id, category)
            else:
                if row["calls"] >= scope["max_calls"]:
                    raise PermissionError("Campaign call allowance exhausted")
                db.execute(
                    "UPDATE campaign_scopes SET calls=calls+1,updated=? WHERE app_id=? AND id=?",
                    (now(), app_id, scope_id),
                )
        return scope

    def _safety_admit(self, db, app_id, scope_id, category):
        """Reserve a separate finite no-spend safety check inside the same transaction."""
        row = db.execute(
            "SELECT used FROM campaign_safety_calls WHERE app_id=? AND scope_id=? AND category=?",
            (app_id, scope_id, category),
        ).fetchone()
        if row is not None and row["used"] >= SAFETY_CALL_LIMIT:
            raise PermissionError("Campaign safety allowance exhausted; inspect provider directly")
        db.execute(
            "INSERT INTO campaign_safety_calls VALUES(?,?,?,1) ON CONFLICT(app_id,scope_id,category) DO UPDATE SET used=used+1",
            (app_id, scope_id, category),
        )

    def _credentials(self, app_id, scope):
        selected = self.connections.get(app_id, scope["connection_id"])
        self.connections.alive(selected)
        if selected["version"] != scope["connection_version"] or selected["provider"] != "facebook":
            raise PermissionError("Facebook connection changed; prepare a new scope")
        if selected["data"]["destination"]["id"] != scope["page_id"]:
            raise PermissionError("Facebook Page changed")
        cfg = self.connections.setup.get(app_id, "facebook")
        client = self.connections.secrets.load(app_id, "facebook", cfg["secret_ref"])
        grant = self.connections.secrets.load(app_id, "facebook", selected["secret_ref"])
        return cfg["data"], client["client_secret"], grant

    def _preflight(self, app_id, actor, scope_id, action, active=True):
        scope = self.get_scope(app_id, scope_id)
        cfg, secret, grant = self._credentials(app_id, scope)
        alive = lambda: self._alive(app_id, actor, scope_id, action, active)
        found = facebook(cfg, secret, grant["access_token"], alive)
        saved = self.connections.get(app_id, scope["connection_id"])
        if found.subject_id != saved["subject_id"]:
            raise PermissionError("Facebook grant belongs to another account")
        required = {"pages_manage_posts", "pages_show_list", "pages_read_engagement"}
        if scope["ad_account_id"]:
            required.update(("ads_management", "ads_read"))
        if not required.issubset(set(found.permissions or [])):
            raise PermissionError("Fresh Facebook permissions do not cover this scope; reconnect")
        pages = [page for page in found.destinations if page["id"] == scope["page_id"]]
        if len(pages) != 1 or "CREATE_CONTENT" not in pages[0]["tasks"]:
            raise PermissionError("Facebook Page does not grant CREATE_CONTENT")
        page, token = selected_page(secret, grant["access_token"], scope["page_id"], alive)
        # selected_page verifies the current token against this exact approved Page.
        # Meta may rotate token bytes while preserving the same account and authority.
        if "CREATE_CONTENT" not in page["tasks"]:
            raise PermissionError("Page creation task is absent")
        return scope, secret, token

    def _account_preflight(self, app_id, actor, scope_id, action, active=True):
        scope = self.get_scope(app_id, scope_id)
        if not scope["ad_account_id"]:
            raise PermissionError("Scope has no approved ad account")
        _, secret, grant = self._credentials(app_id, scope)
        token = grant["access_token"]
        info = self.transport.ad_account(
            scope["ad_account_id"], token, secret, lambda: self._alive(app_id, actor, scope_id, action, active)
        )
        if info["currency"] != scope["currency"]:
            raise PermissionError("Advertising account currency differs from scope")
        return scope, secret, token

    def activate_scope(self, app_id, owner, scope_id, approval_hash):
        scope = self.get_scope(app_id, scope_id)
        if scope["status"] != "DRAFT" or scope["approval_hash"] != approval_hash:
            raise Invalid("Campaign review changed; prepare the exact scope again")
        if scope["owner_principal"] != owner:
            raise PermissionError("Only the scope owner may activate")
        self._preflight(app_id, owner, scope_id, "ACTIVATE", False)
        if scope["ad_account_id"]:
            if not PAID_EXECUTION_READY:
                raise Invalid("Paid lifecycle verification is incomplete")
            self._account_preflight(app_id, owner, scope_id, "ACTIVATE", False)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            fresh = row_scope(self._row(db, app_id, scope_id))
            self._check(db, app_id, owner, fresh, "ACTIVATE", False)
            if fresh["status"] != "DRAFT" or fresh["approval_hash"] != approval_hash:
                raise Invalid("Campaign review changed during verification")
            if iso_time(fresh["expires_at"]) <= datetime.now(timezone.utc):
                raise Invalid("Campaign review expired")
            db.execute(
                "UPDATE campaign_scopes SET status='ACTIVE',updated=? WHERE app_id=? AND id=?",
                (now(), app_id, scope_id),
            )
            from .authority_expiry import initial_base, record_initial

            saved = self._row(db, app_id, scope_id)
            base = initial_base(fresh["expires_at"], saved["created"], fresh.get("extended_expiry_consent"))
            record_initial(
                db,
                "CAMPAIGN",
                saved,
                base,
                fresh["expires_at"],
                owner,
                saved["owner_version"],
                json.loads(saved["summary"]),
                datetime.now(timezone.utc),
            )
        return self.get_scope(app_id, scope_id)

    def revoke_scope(self, app_id, owner, scope_id):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            scope = row_scope(self._row(db, app_id, scope_id))
            if owner != scope["owner_principal"]:
                raise PermissionError("Only the scope owner may revoke")
            member(db, app_id, owner, "OWNER")
            self.policy_checker(app_id, owner, scope, "REVOKE")
            db.execute(
                "UPDATE campaign_scopes SET status='REVOKED',updated=? WHERE app_id=? AND id=?",
                (now(), app_id, scope_id),
            )
        scope = self.get_scope(app_id, scope_id)
        with connection(self.store.path) as db:
            rows = db.execute(
                "SELECT id,ids FROM campaign_paid_intents WHERE app_id=? AND scope_id=?", (app_id, scope_id)
            ).fetchall()
        pauses = []
        for row in rows:
            if not json.loads(row["ids"]).get("campaign"):
                continue
            try:
                result = self._pause(app_id, owner, scope_id, row["id"], "REVOKE")
                pauses.append({"intent_id": row["id"], "status": result["status"]})
            except Exception:
                pauses.append({"intent_id": row["id"], "status": "PAUSE_UNCONFIRMED"})
        return dict(scope, pause_results=pauses)

    def _reserve_post(self, app_id, actor, scope_id, post, destination_check=None):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            scope = row_scope(self._row(db, app_id, scope_id))
            self._check(db, app_id, actor, scope, "RUN_POST")
            if (
                post["content_hash"] not in scope["approved_content_hashes"]
                or post["rights_hash"] not in scope["approved_rights_hashes"]
            ):
                raise PermissionError("Post content or rights attestation is outside the approved scope")
            previous = db.execute(
                "SELECT * FROM campaign_intents WHERE app_id=? AND request_id=?", (app_id, post["request_id"])
            ).fetchone()
            if previous:
                if previous["request_hash"] != digest(post) or previous["scope_id"] != scope_id:
                    raise Invalid("Request identity was already used with different content")
                return row_intent(previous), False
            previous = db.execute(
                "SELECT * FROM campaign_intents WHERE app_id=? AND page_id=? AND content_hash=? AND rights_hash=?",
                (app_id, scope["page_id"], post["content_hash"], post["rights_hash"]),
            ).fetchone()
            if previous:
                raise Invalid("Matching post already has a saved intent; inspect it instead of creating another")
            count = db.execute(
                "SELECT count(*) FROM campaign_intents WHERE app_id=? AND scope_id=?", (app_id, scope_id)
            ).fetchone()[0]
            if count >= scope["max_posts"]:
                raise PermissionError("Approved post count is exhausted")
            identity = uid()
            stamp = now()
            db.execute(
                "INSERT INTO campaign_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    app_id,
                    identity,
                    scope_id,
                    post["request_id"],
                    digest(post),
                    post["content_hash"],
                    post["rights_hash"],
                    scope["page_id"],
                    "DISPATCHING",
                    None,
                    canonical({"destination_check": destination_check}) if destination_check else None,
                    stamp,
                    stamp,
                ),
            )
            return row_intent(
                db.execute("SELECT * FROM campaign_intents WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
            ), True

    def _save_intent(self, app_id, identity, status, remote_id=None, result=None):
        """Record an already-dispatched outcome even if authority expires in flight.

        This receipt-only connection cannot grant authority or write a business effect.
        Transition and identity are constrained to the previously admitted intent.
        """
        transitions = {
            "UNKNOWN": ("DISPATCHING",),
            "ACKNOWLEDGED": ("DISPATCHING",),
            "VERIFYING": ("ACKNOWLEDGED", "VERIFYING"),
            "VERIFIED": ("ACKNOWLEDGED", "VERIFYING", "VERIFIED"),
        }
        allowed = transitions.get(status)
        if not allowed:
            raise Invalid("Invalid campaign receipt transition")
        db = sqlite3.connect(str(self.store.path), timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM campaign_intents WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
            if row is None or row["status"] not in allowed:
                raise Invalid("Campaign receipt state changed")
            if row["remote_id"] and remote_id and row["remote_id"] != remote_id:
                raise Invalid("Campaign receipt identity changed")
            previous = json.loads(row["result"]) if row["result"] else {}
            if "destination_check" in previous:
                result = dict(result or {}, destination_check=previous["destination_check"])
            db.execute(
                "UPDATE campaign_intents SET status=?,remote_id=COALESCE(?,remote_id),result=?,updated=? WHERE app_id=? AND id=?",
                (status, remote_id, canonical(result) if result else None, now(), app_id, identity),
            )
            saved = row_intent(
                db.execute("SELECT * FROM campaign_intents WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
            )
            db.commit()
            return saved
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def run_post(self, app_id, actor, scope_id, body):
        post = post_data(body)
        scope, secret, token = self._preflight(app_id, actor, scope_id, "RUN_POST")
        if scope.get("measurement_plan"):
            from .evidence_gate import assert_ready

            assert_ready(self.store, app_id, scope, request=post)
        with connection(self.store.path) as db:
            self._check(db, app_id, actor, scope, "RUN_POST")
            if (
                post["content_hash"] not in scope["approved_content_hashes"]
                or post["rights_hash"] not in scope["approved_rights_hashes"]
            ):
                raise PermissionError("Post content or rights attestation is outside the approved scope")
            previous = db.execute(
                """SELECT 1 FROM campaign_intents WHERE app_id=? AND
                (request_id=? OR (page_id=? AND content_hash=? AND rights_hash=?))""",
                (app_id, post["request_id"], scope["page_id"], post["content_hash"], post["rights_hash"]),
            ).fetchone()
        if previous:
            # A retained or uncertain intent must never trigger a new URL check
            # or a second dispatch; reserve rechecks exact identity and authority.
            intent, _ = self._reserve_post(app_id, actor, scope_id, post)
            return intent
        destination = check_destination(post["link"])
        intent, fresh = self._reserve_post(app_id, actor, scope_id, post, destination)
        if not fresh:
            return intent
        try:
            remote = self.transport.publish(
                scope["page_id"],
                post["message"],
                post["link"],
                token,
                secret,
                lambda: self._alive(app_id, actor, scope_id, "RUN_POST"),
            )
        except Exception:
            self._save_intent(app_id, intent["id"], "UNKNOWN")
            raise Unconfirmed("Post dispatch outcome is unknown; inspect the saved intent before any retry") from None
        self._save_intent(app_id, intent["id"], "ACKNOWLEDGED", remote)
        try:
            result = self.transport.read_post(
                scope["page_id"],
                remote,
                post["content_hash"],
                token,
                secret,
                lambda: self._alive(app_id, actor, scope_id, "RUN_POST"),
            )
        except Exception:
            return self._save_intent(app_id, intent["id"], "VERIFYING", remote)
        return self._save_intent(app_id, intent["id"], "VERIFIED", remote, result)

    def reconcile(self, app_id, actor, scope_id, intent_id):
        with connection(self.store.path) as db:
            scope = row_scope(self._row(db, app_id, scope_id))
            self._check(db, app_id, actor, scope, "RECONCILE", False)
            paid = db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND id=?",
                (app_id, scope_id, intent_id),
            ).fetchone()
        if paid is not None:
            return self._reconcile_paid(app_id, actor, scope_id, paid_view(paid))
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT * FROM campaign_intents WHERE app_id=? AND scope_id=? AND id=?", (app_id, scope_id, intent_id)
            ).fetchone()
        intent = row_intent(row)
        if not intent["remote_id"]:
            return intent
        scope, secret, token = self._preflight(app_id, actor, scope_id, "RECONCILE", False)
        result = self.transport.read_post(
            scope["page_id"],
            intent["remote_id"],
            intent["content_hash"],
            token,
            secret,
            lambda: self._alive(app_id, actor, scope_id, "RECONCILE", False),
        )
        return self._save_intent(app_id, intent_id, "VERIFIED", intent["remote_id"], result)

    def _reconcile_paid(self, app_id, actor, scope_id, intent):
        """Observe saved IDs and recover only an abandoned, token-bound pending step."""
        try:
            with paid_lock(self.store, app_id, intent["id"]):
                return self._reconcile_locked(app_id, actor, scope_id, intent["id"])
        except CampaignLockBusy:
            with connection(self.store.path) as db:
                row = db.execute(
                    "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND id=?",
                    (app_id, scope_id, intent["id"]),
                ).fetchone()
            return dict(paid_view(row), recovery="IN_FLIGHT")

    def _reconcile_locked(self, app_id, actor, scope_id, intent_id):
        with connection(self.store.path) as db:
            row = db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND id=?",
                (app_id, scope_id, intent_id),
            ).fetchone()
            lease = db.execute(
                "SELECT * FROM campaign_paid_leases WHERE app_id=? AND intent_id=?", (app_id, intent_id)
            ).fetchone()
        intent = paid_view(row)
        pending = intent["status"].startswith("PENDING_")
        if pending and (lease is None or lease["step"] != intent["status"][8:]):
            return dict(intent, recovery="OWNER_UNVERIFIED")
        if not pending and lease is not None:
            return dict(intent, recovery="LEASE_STATE_CONFLICT")
        recovery_token = RECOVERING_PAID.set(pending)
        try:
            result = self._paid_observation(app_id, actor, scope_id, intent)
        finally:
            RECOVERING_PAID.reset(recovery_token)
        if pending:
            result["recovery"] = "ABANDONED_UNKNOWN"
            result["interrupted_step"] = lease["step"]
        return self._record_reconcile(app_id, intent, lease, result)

    def _paid_observation(self, app_id, actor, scope_id, intent):
        scope, secret, token = self._protective_credentials(app_id, scope_id)
        result = {
            "observed_at": now(),
            "objects": {},
            "configuration": "INCOMPLETE",
            "reported_spend": None,
            "reporting": "NOT_AVAILABLE",
            "commitment_note": "Full media commitment remains held; provider reporting may lag.",
        }
        observed = {}
        for kind, identity in intent["ids"].items():
            row = self._paid_read(app_id, actor, scope, kind, identity, token, secret, "RECONCILE", False)
            if str(row.get("account_id")) != scope["ad_account_id"]:
                raise Unconfirmed("Advertising account readback changed")
            observed[kind] = row
            result["objects"][kind] = {key: row.get(key) for key in ("id", "status", "effective_status") if key in row}
        if set(observed) == {"campaign", "adset", "creative", "ad"}:
            try:
                self._verify_paid_values(scope, intent, observed)
                result["configuration"] = "MATCHES_APPROVAL"
            except (Invalid, TypeError, KeyError):
                result["configuration"] = "CHANGED_OR_UNCONFIRMED_PAUSE_RECOMMENDED"
        if intent["ids"].get("ad"):
            result.update(
                self.transport.ad_insights(
                    intent["ids"]["ad"], token, secret, lambda: self._alive(app_id, actor, scope_id, "RECONCILE", False)
                )
            )
        return result

    def _record_reconcile(self, app_id, intent, lease, result):
        """Commit only a matching pending owner, status and ID snapshot; preserve holds."""
        db = sqlite3.connect(str(self.store.path), timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, intent["id"])
            ).fetchone()
            actual = db.execute(
                "SELECT * FROM campaign_paid_leases WHERE app_id=? AND intent_id=?", (app_id, intent["id"])
            ).fetchone()
            same = (
                current is not None
                and current["status"] == intent["status"]
                and json.loads(current["ids"]) == intent["ids"]
            )
            if same:
                fields = ("scope_id", "request_id", "request_hash", "account_id", "currency", "commitment")
                same = (
                    all(current[key] == intent[key] for key in fields) and json.loads(current["data"]) == intent["data"]
                )
            if lease is not None:
                same = bool(
                    same
                    and actual is not None
                    and actual["step"] == lease["step"]
                    and actual["owner_token"] == lease["owner_token"]
                )
            elif actual is not None:
                same = False
            if not same:
                raise Invalid("Campaign changed during reconciliation; inspect current state")
            new_status = "UNKNOWN" if lease is not None else intent["status"]
            db.execute(
                "UPDATE campaign_paid_intents SET status=?,result=?,updated=? WHERE app_id=? AND id=?",
                (new_status, canonical(result), now(), app_id, intent["id"]),
            )
            if lease is not None:
                deleted = db.execute(
                    "DELETE FROM campaign_paid_leases WHERE app_id=? AND intent_id=? AND step=? AND owner_token=?",
                    (app_id, intent["id"], lease["step"], lease["owner_token"]),
                ).rowcount
                if deleted != 1:
                    raise Invalid("Campaign recovery owner changed")
            saved = paid_view(
                db.execute(
                    "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, intent["id"])
                ).fetchone()
            )
            db.commit()
            return saved
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _reserve_ad(self, app_id, actor, scope_id, body):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._row(db, app_id, scope_id)
            scope = row_scope(row)
            self._check(db, app_id, actor, scope, "RUN_AD")
            budget = check_ad_limits(db, row, scope, body)
            post = db.execute(
                "SELECT * FROM campaign_intents WHERE app_id=? AND page_id=? AND remote_id=? AND status='VERIFIED' AND content_hash=? AND rights_hash=?",
                (app_id, scope["page_id"], body["post_id"], body["content_hash"], body["rights_hash"]),
            ).fetchone()
            if post is None:
                raise PermissionError("Promote only a verified saved Page post with approved content and rights")
            previous = db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND request_id=?", (app_id, body["request_id"])
            ).fetchone()
            if previous:
                if previous["request_hash"] != digest(body) or previous["scope_id"] != scope_id:
                    raise Invalid("Request ID belongs to a different campaign")
                return paid_view(previous), False
            count = db.execute(
                "SELECT count(*) FROM campaign_paid_intents WHERE app_id=? AND scope_id=?", (app_id, scope_id)
            ).fetchone()[0]
            held = db.execute(
                "SELECT COALESCE(sum(commitment),0) FROM campaign_paid_intents WHERE account_id=? AND currency=?",
                (scope["ad_account_id"], scope["currency"]),
            ).fetchone()[0]
            if count >= scope["max_campaigns"] or held + budget > scope["max_total_minor"]:
                raise PermissionError("Campaign count or retained account commitment exceeds scope")
            identity = uid()
            stamp = now()
            db.execute(
                "INSERT INTO campaign_paid_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    app_id,
                    identity,
                    scope_id,
                    body["request_id"],
                    digest(body),
                    scope["ad_account_id"],
                    scope["currency"],
                    budget,
                    canonical(body),
                    "{}",
                    "RESERVED",
                    None,
                    stamp,
                    stamp,
                ),
            )
            return paid_view(
                db.execute("SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
            ), True

    def _mark_paid(self, app_id, actor, scope_id, intent_id, step, owner_token, action="RUN_AD", active=True):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            scope = row_scope(self._row(db, app_id, scope_id))
            self._check(db, app_id, actor, scope, action, active)
            row = db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND id=?",
                (app_id, scope_id, intent_id),
            ).fetchone()
            if row is None or row["status"].startswith("PENDING_"):
                raise Invalid("Campaign has another unresolved provider operation")
            stopped = db.execute(
                "SELECT 1 FROM campaign_stop_requests WHERE app_id=? AND intent_id=?", (app_id, intent_id)
            ).fetchone()
            if stopped and step != "PAUSED_campaign":
                raise PermissionError("Campaign stop was requested")
            expected = {
                "CREATE_campaign": "RESERVED",
                "CREATE_adset": "CREATED_campaign",
                "CREATE_creative": "CREATED_adset",
                "CREATE_ad": "CREATED_creative",
                "ACTIVE_adset": "CREATED_ad",
                "ACTIVE_ad": "ACTIVE_adset",
                "ACTIVE_campaign": "ACTIVE_ad",
            }
            if step not in expected and step != "PAUSED_campaign":
                raise Invalid("Unsupported campaign step")
            if step in expected and row["status"] != expected[step]:
                raise PermissionError("Campaign stopped or changed before the next operation")
            if db.execute(
                "SELECT 1 FROM campaign_paid_leases WHERE app_id=? AND intent_id=?", (app_id, intent_id)
            ).fetchone():
                raise Invalid("Campaign has an unresolved operation lease")
            db.execute(
                "INSERT INTO campaign_paid_leases VALUES(?,?,?,?,?)", (app_id, intent_id, step, owner_token, now())
            )
            db.execute(
                "UPDATE campaign_paid_intents SET status=?,updated=? WHERE app_id=? AND id=?",
                ("PENDING_" + step, now(), app_id, intent_id),
            )

    def _receipt_paid(self, app_id, intent_id, step, owner_token, status, kind=None, remote_id=None, result=None):
        """Record only the result of the exact previously admitted paid boundary."""
        from .campaign_contract import numeric

        if remote_id is not None:
            numeric(remote_id)
        create_steps = {f"CREATE_{name}": name for name in ("campaign", "adset", "creative", "ad")}
        status_steps = {f"ACTIVE_{name}" for name in ("campaign", "adset", "ad")} | {"PAUSED_campaign"}
        if step in create_steps:
            expected_kind = create_steps[step]
            if status == "UNKNOWN":
                if kind is not None or remote_id is not None:
                    raise Invalid("Unknown receipt cannot invent an ID")
            elif status != "CREATED_" + expected_kind or kind != expected_kind or remote_id is None:
                raise Invalid("Invalid campaign creation receipt")
        elif step in status_steps:
            if status not in ("UNKNOWN", "ACK_" + step) or kind is not None or remote_id is not None:
                raise Invalid("Invalid advertising status receipt")
        else:
            raise Invalid("Unsupported campaign receipt")
        db = sqlite3.connect(str(self.store.path), timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, intent_id)
            ).fetchone()
            lease = db.execute(
                "SELECT * FROM campaign_paid_leases WHERE app_id=? AND intent_id=?", (app_id, intent_id)
            ).fetchone()
            if (
                row is None
                or row["status"] != "PENDING_" + step
                or lease is None
                or lease["step"] != step
                or lease["owner_token"] != owner_token
            ):
                raise Invalid("Campaign receipt ownership changed")
            ids = json.loads(row["ids"])
            if kind:
                if kind not in ("campaign", "adset", "creative", "ad") or (kind in ids and ids[kind] != remote_id):
                    raise Invalid("Campaign object identity changed")
                ids[kind] = remote_id
            db.execute(
                "UPDATE campaign_paid_intents SET ids=?,status=?,result=?,updated=? WHERE app_id=? AND id=?",
                (canonical(ids), status, canonical(result) if result is not None else None, now(), app_id, intent_id),
            )
            db.execute(
                "DELETE FROM campaign_paid_leases WHERE app_id=? AND intent_id=? AND owner_token=?",
                (app_id, intent_id, owner_token),
            )
            saved = paid_view(
                db.execute(
                    "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, intent_id)
                ).fetchone()
            )
            db.commit()
            return saved
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _confirm_paid(self, app_id, intent_id, expected, status, readback=None):
        """Record only a readback following a saved provider acknowledgment."""
        permitted = {
            ("ACK_ACTIVE_adset", "ACTIVE_adset"),
            ("ACK_ACTIVE_ad", "ACTIVE_ad"),
            ("ACK_ACTIVE_campaign", "ACTIVE_campaign"),
            ("ACK_PAUSED_campaign", "PAUSED_campaign"),
        }
        if (expected, status) not in permitted:
            raise Invalid("Invalid campaign confirmation transition")
        db = sqlite3.connect(str(self.store.path), timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            receipt = None
            if status == "PAUSED_campaign":
                intent = db.execute(
                    "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, intent_id)
                ).fetchone()
                if intent is None:
                    raise Invalid("Paid campaign intent was not found")
                receipt = pause_receipt_data(intent, readback)
            changed = db.execute(
                "UPDATE campaign_paid_intents SET status=?,updated=? WHERE app_id=? AND id=? AND status=?",
                (status, now(), app_id, intent_id, expected),
            ).rowcount
            if not changed:
                raise Invalid("Campaign verification state changed")
            if receipt is not None:
                db.execute(
                    "INSERT INTO campaign_pause_receipts VALUES(?,?,?,?,?)",
                    (app_id, intent_id, digest(receipt), canonical(receipt), receipt["observed_at"]),
                )
            result = paid_view(
                db.execute(
                    "SELECT * FROM campaign_paid_intents WHERE app_id=? AND id=?", (app_id, intent_id)
                ).fetchone()
            )
            if receipt is not None:
                result["pause_readback"] = dict(receipt, sha256=digest(receipt))
            db.commit()
            return result
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _paid_create(self, app_id, actor, scope, intent, kind, fields, token, secret):
        step = "CREATE_" + kind
        identity = intent["id"]
        owner_token = uid()
        with paid_lock(self.store, app_id, identity):
            self._mark_paid(app_id, actor, scope["scope_id"], identity, step, owner_token)
            try:
                remote = self.transport.create_paid(
                    kind,
                    scope["ad_account_id"],
                    fields,
                    token,
                    secret,
                    lambda: self._alive(app_id, actor, scope["scope_id"], "RUN_AD"),
                )
            except Exception:
                self._receipt_paid(app_id, identity, step, owner_token, "UNKNOWN")
                raise Unconfirmed("Campaign creation outcome is unknown; no automatic retry") from None
            return self._receipt_paid(app_id, identity, step, owner_token, "CREATED_" + kind, kind, remote)

    def _paid_read(self, app_id, actor, scope, kind, identity, token, secret, action="RUN_AD", active=True):
        value = self.transport.read_paid(
            kind, identity, token, secret, lambda: self._alive(app_id, actor, scope["scope_id"], action, active)
        )
        if not isinstance(value, dict) or value.get("id") != identity:
            raise Unconfirmed("Saved advertising object identity was not confirmed")
        return value

    def _verify_paid(self, app_id, actor, scope, intent, token, secret, action="RUN_AD", active=True):
        ids = intent["ids"]
        found = {}
        for kind in ("campaign", "adset", "creative", "ad"):
            found[kind] = self._paid_read(app_id, actor, scope, kind, ids[kind], token, secret, action, active)
            if str(found[kind].get("account_id")) != scope["ad_account_id"]:
                raise Unconfirmed("Advertising object account mismatch")
        self._verify_paid_values(scope, intent, found)
        return found

    def _verify_paid_values(self, scope, intent, found):
        ids = intent["ids"]
        body = intent["data"]
        campaign, adset, creative, ad = (found[x] for x in ("campaign", "adset", "creative", "ad"))
        if campaign.get("objective") != "OUTCOME_ENGAGEMENT" or adset.get("campaign_id") != ids["campaign"]:
            raise Unconfirmed("Advertising campaign ownership differs from approval")
        if campaign.get("is_adset_budget_sharing_enabled") is not False:
            raise Unconfirmed("Provider ad set budget sharing is not confirmed disabled")
        if str(adset.get("lifetime_budget")) != str(body["lifetime_budget_minor"]) or iso_time(
            adset.get("end_time")
        ) != iso_time(body["end_time"]):
            raise Unconfirmed("Provider lifetime budget or end time differs from approval")
        target = adset.get("targeting")
        if (
            not isinstance(target, dict)
            or target.get("geo_locations", {}).get("countries") != body["targeting"]["countries"]
        ):
            raise Unconfirmed("Provider targeting countries differ from approval")
        if target.get("publisher_platforms") != ["facebook"] or target.get("facebook_positions") != ["feed"]:
            raise Unconfirmed("Provider placements differ from approval")
        if adset.get("optimization_goal") != "POST_ENGAGEMENT" or adset.get("billing_event") != "IMPRESSIONS":
            raise Unconfirmed("Provider optimization differs from approval")
        if creative.get("object_story_id") != body["post_id"] or ad.get("adset_id") != ids["adset"]:
            raise Unconfirmed("Advertising post or ad set differs from approval")
        if not isinstance(ad.get("creative"), dict) or ad["creative"].get("id") != ids["creative"]:
            raise Unconfirmed("Advertising creative differs from approval")

    def _paid_status(self, app_id, actor, scope, intent, kind, status, token, secret, action="RUN_AD", active=True):
        step = status + "_" + kind
        identity = intent["id"]
        owner_token = uid()
        with paid_lock(self.store, app_id, identity):
            self._mark_paid(app_id, actor, scope["scope_id"], identity, step, owner_token, action, active)
            try:
                self.transport.set_paid_status(
                    kind,
                    intent["ids"][kind],
                    status,
                    token,
                    secret,
                    lambda: self._alive(app_id, actor, scope["scope_id"], action, active),
                )
            except Exception:
                self._receipt_paid(app_id, identity, step, owner_token, "UNKNOWN")
                raise Unconfirmed("Advertising status outcome is unknown; inspect before another action") from None
            return self._receipt_paid(app_id, identity, step, owner_token, "ACK_" + status + "_" + kind)

    def run_ad(self, app_id, actor, scope_id, body):
        if not PAID_EXECUTION_READY:
            raise Invalid("Paid lifecycle verification is incomplete")
        body = ad_data(body)
        scope, secret, page_token = self._preflight(app_id, actor, scope_id, "RUN_AD")
        scope, secret, token = self._account_preflight(app_id, actor, scope_id, "RUN_AD")
        if scope.get("measurement_plan"):
            from .evidence_gate import assert_ready

            assert_ready(self.store, app_id, scope)
        intent, fresh = self._reserve_ad(app_id, actor, scope_id, body)
        if not fresh:
            return intent
        try:
            self.transport.read_post(
                scope["page_id"],
                body["post_id"],
                body["content_hash"],
                page_token,
                secret,
                lambda: self._alive(app_id, actor, scope_id, "RUN_AD"),
            )
            name = body["name"]
            target = {
                "geo_locations": {"countries": body["targeting"]["countries"]},
                "publisher_platforms": ["facebook"],
                "facebook_positions": ["feed"],
            }
            intent = self._paid_create(
                app_id,
                actor,
                scope,
                intent,
                "campaign",
                dict(
                    name=name,
                    objective="OUTCOME_ENGAGEMENT",
                    status="PAUSED",
                    special_ad_categories=[],
                    is_adset_budget_sharing_enabled=False,
                ),
                token,
                secret,
            )
            intent = self._paid_create(
                app_id,
                actor,
                scope,
                intent,
                "adset",
                dict(
                    name=name,
                    campaign_id=intent["ids"]["campaign"],
                    lifetime_budget=body["lifetime_budget_minor"],
                    end_time=body["end_time"],
                    billing_event="IMPRESSIONS",
                    optimization_goal="POST_ENGAGEMENT",
                    targeting=target,
                    status="PAUSED",
                ),
                token,
                secret,
            )
            intent = self._paid_create(
                app_id,
                actor,
                scope,
                intent,
                "creative",
                dict(name=name, object_story_id=body["post_id"]),
                token,
                secret,
            )
            intent = self._paid_create(
                app_id,
                actor,
                scope,
                intent,
                "ad",
                dict(
                    name=name,
                    adset_id=intent["ids"]["adset"],
                    creative={"creative_id": intent["ids"]["creative"]},
                    status="PAUSED",
                ),
                token,
                secret,
            )
            values = self._verify_paid(app_id, actor, scope, intent, token, secret)
            if any(values[kind].get("status") != "PAUSED" for kind in ("campaign", "adset", "ad")):
                raise Unconfirmed("Advertising objects were not confirmed paused")
            for kind in ("adset", "ad", "campaign"):
                if kind == "campaign":
                    self._account_preflight(app_id, actor, scope_id, "RUN_AD")
                    current_objects = self._verify_paid(app_id, actor, scope, intent, token, secret)
                    if current_objects["campaign"].get("status") != "PAUSED" or any(
                        current_objects[k].get("status") != "ACTIVE" for k in ("adset", "ad")
                    ):
                        raise Unconfirmed("Advertising objects changed before final activation")
                intent = self._paid_status(app_id, actor, scope, intent, kind, "ACTIVE", token, secret)
                current = self._paid_read(app_id, actor, scope, kind, intent["ids"][kind], token, secret)
                if current.get("status") != "ACTIVE":
                    raise Unconfirmed("Advertising activation readback is not confirmed")
                intent = self._confirm_paid(app_id, intent["id"], "ACK_ACTIVE_" + kind, "ACTIVE_" + kind)
            return intent
        except Exception:
            raise

    def run_pause(self, app_id, actor, scope_id, intent_id):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            scope = row_scope(self._row(db, app_id, scope_id))
            self._check(db, app_id, actor, scope, "PAUSE", False)
            row = db.execute(
                "SELECT id FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND id=?",
                (app_id, scope_id, intent_id),
            ).fetchone()
            if row is None:
                raise Invalid("Paid campaign intent was not found")
            db.execute("INSERT OR IGNORE INTO campaign_stop_requests VALUES(?,?,?)", (app_id, intent_id, now()))
        return self._pause(app_id, actor, scope_id, intent_id, "PAUSE")

    def _protective_credentials(self, app_id, scope_id):
        """Use only the unchanged saved grant and approved account for no-spend control."""
        scope = self.get_scope(app_id, scope_id)
        if not scope["ad_account_id"]:
            raise PermissionError("Scope has no approved ad account")
        _, secret, grant = self._credentials(app_id, scope)
        return scope, secret, grant["access_token"]

    def _pause(self, app_id, actor, scope_id, intent_id, action):
        scope, secret, token = self._protective_credentials(app_id, scope_id)
        with connection(self.store.path) as db:
            intent = paid_view(
                db.execute(
                    "SELECT * FROM campaign_paid_intents WHERE app_id=? AND scope_id=? AND id=?",
                    (app_id, scope_id, intent_id),
                ).fetchone()
            )
        if not intent["ids"].get("campaign"):
            raise Invalid("No saved campaign ID is available to pause")
        current = self._paid_read(
            app_id, actor, scope, "campaign", intent["ids"]["campaign"], token, secret, action, False
        )
        if str(current.get("account_id")) != scope["ad_account_id"]:
            raise Unconfirmed("Saved campaign account readback differs from approved account")
        intent = self._paid_status(app_id, actor, scope, intent, "campaign", "PAUSED", token, secret, action, False)
        current = self._paid_read(
            app_id, actor, scope, "campaign", intent["ids"]["campaign"], token, secret, action, False
        )
        if str(current.get("account_id")) != scope["ad_account_id"] or current.get("status") != "PAUSED":
            raise Unconfirmed("Pause account or status readback was not confirmed")
        return self._confirm_paid(app_id, intent["id"], "ACK_PAUSED_campaign", "PAUSED_campaign", current)
