"""Exact owner-reviewed publication authority; no provider or credential access."""

from datetime import datetime, timezone
import json, time
from .agent_grants import app_scope
from .authority_expiry import deadline
from .campaign_access import identity as campaign_identity, scope_owner
from .campaign_schedule import owner_context
from .common import Invalid, canonical, digest, now, uid, iso_time
from .db import connection
from .operation_authority import check
from .publication_contract import validate_draft
from .review_access import member, exact_role
from .social_contract import reference, display

SCHEMA = """
CREATE TABLE IF NOT EXISTS publication_authorities(
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL,
 owner_version INTEGER NOT NULL, app_version INTEGER NOT NULL, app_hash TEXT NOT NULL,
 draft TEXT NOT NULL, review_hash TEXT NOT NULL, binding TEXT NOT NULL, binding_hash TEXT NOT NULL,
 preflight_id TEXT, status TEXT NOT NULL, version INTEGER NOT NULL, approval TEXT,
 approval_hash TEXT, expires REAL, max_calls INTEGER, calls_used INTEGER NOT NULL DEFAULT 0,
 created TEXT NOT NULL, updated TEXT NOT NULL, UNIQUE(app_id,owner,review_hash));
CREATE TABLE IF NOT EXISTS publication_preflights(
 id TEXT PRIMARY KEY, app_id TEXT NOT NULL REFERENCES apps(id), owner TEXT NOT NULL,
 connection_id TEXT NOT NULL, connection_version INTEGER NOT NULL, destination_id TEXT NOT NULL,
 info TEXT NOT NULL, info_hash TEXT NOT NULL, created REAL NOT NULL);
CREATE TRIGGER IF NOT EXISTS publication_preflight_no_update BEFORE UPDATE ON publication_preflights
 BEGIN SELECT RAISE(ABORT,'Publication preflight is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_preflight_no_delete BEFORE DELETE ON publication_preflights
 BEGIN SELECT RAISE(ABORT,'Publication preflight is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_preflight_no_replace BEFORE INSERT ON publication_preflights
 WHEN EXISTS(SELECT 1 FROM publication_preflights WHERE id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'Publication preflight is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_authority_no_rewrite BEFORE UPDATE ON publication_authorities
 WHEN NEW.id!=OLD.id OR NEW.app_id!=OLD.app_id OR NEW.owner!=OLD.owner OR NEW.owner_version!=OLD.owner_version
 OR NEW.app_version!=OLD.app_version OR NEW.app_hash!=OLD.app_hash OR NEW.draft!=OLD.draft
 OR NEW.review_hash!=OLD.review_hash OR NEW.binding!=OLD.binding OR NEW.binding_hash!=OLD.binding_hash
 OR NEW.preflight_id IS NOT OLD.preflight_id OR NEW.created!=OLD.created
 BEGIN SELECT RAISE(ABORT,'Publication review is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_authority_no_delete BEFORE DELETE ON publication_authorities
 BEGIN SELECT RAISE(ABORT,'Publication authority is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_authority_no_replace BEFORE INSERT ON publication_authorities
 WHEN EXISTS(SELECT 1 FROM publication_authorities WHERE id=NEW.id OR (app_id=NEW.app_id AND owner=NEW.owner AND review_hash=NEW.review_hash))
 BEGIN SELECT RAISE(ABORT,'Publication review already exists'); END;
CREATE TRIGGER IF NOT EXISTS publication_approval_no_rewrite BEFORE UPDATE ON publication_authorities
 WHEN OLD.approval IS NOT NULL AND (NEW.approval IS NOT OLD.approval OR NEW.approval_hash IS NOT OLD.approval_hash
 OR NEW.expires IS NOT OLD.expires OR NEW.max_calls IS NOT OLD.max_calls)
 BEGIN SELECT RAISE(ABORT,'Publication approval is immutable'); END;
DROP TRIGGER IF EXISTS publication_authority_state_guard;
CREATE TRIGGER IF NOT EXISTS publication_authority_state_guard_v2 BEFORE UPDATE ON publication_authorities
 WHEN NOT ((NEW.status=OLD.status AND (OLD.status!='REVOKED' OR
           (NEW.calls_used=OLD.calls_used+1 AND NEW.version=OLD.version))) OR
           (OLD.status='PREPARED' AND NEW.status IN ('APPROVED','REVOKED')) OR
           (OLD.status='APPROVED' AND NEW.status='REVOKED'))
 OR NEW.calls_used<OLD.calls_used OR NEW.calls_used>OLD.calls_used+1
 OR (NEW.calls_used>OLD.calls_used AND (OLD.status NOT IN ('APPROVED','REVOKED') OR NEW.status!=OLD.status OR NEW.calls_used>OLD.max_calls))
 BEGIN SELECT RAISE(ABORT,'Invalid publication transition'); END;
"""


def initialize(store):
    with connection(store.path) as db:
        db.executescript("BEGIN IMMEDIATE;\n" + SCHEMA + "\nCOMMIT;")


def _admit(store, app_id, operation, body, owner_only=False):
    context, actor = campaign_identity(store, app_id)
    if json.loads(context["envelope"]) != {"app_id": app_id, "operation": operation, "input": body}:
        raise PermissionError("Publication operation differs from protected admission")
    if owner_only and "principal" not in context:
        raise PermissionError("Fresh owner authority is required")
    return context, actor, scope_owner(store, context, actor)


def _connection(db, app_id, draft):
    row = db.execute(
        "SELECT * FROM social_connections WHERE app_id=? AND id=?", (app_id, draft["connection_id"])
    ).fetchone()
    if (
        not row
        or row["version"] != draft["connection_version"]
        or row["status"] != "CONNECTED_READ_TESTED"
        or row["lease"]
        or (row["expires"] is not None and row["expires"] <= time.time())
    ):
        raise PermissionError("Publication connection changed or expired")
    cfg = db.execute(
        "SELECT version,status,data FROM social_configs WHERE app_id=? AND provider=?", (app_id, row["provider"])
    ).fetchone()
    if not cfg or cfg["version"] != row["config_version"] or cfg["status"] == "DISCONNECTED":
        raise PermissionError("Publication provider configuration changed")
    data = json.loads(row["data"])
    provider = draft["provider"]
    if provider == "instagram" and row["provider"] == "facebook":
        from .publication_instagram_connection import assert_saved_connection

        assert_saved_connection(row, draft)
    else:
        required = {
            "instagram": "instagram_business_content_publish",
            "tiktok": "video.publish",
            "youtube": "https://www.googleapis.com/auth/youtube.upload",
            "linkedin": "w_member_social",
        }[provider]
        scopes = data.get("facts", {}).get("reported_scopes")
        if (
            row["provider"] != provider
            or data.get("destination", {}).get("id") != draft["destination_id"]
            or not isinstance(scopes, list)
            or required not in scopes
        ):
            raise PermissionError("Publication destination or observed publish permission is unavailable")
    return dict(
        connection_version=row["version"],
        config_version=row["config_version"],
        provider=row["provider"],
        data_hash=digest(data),
        config_hash=digest(json.loads(cfg["data"])),
    )


def _proof(store, db, app_id, draft, verify_bytes=True):
    from .publication_artifacts import verify

    return verify(store, db, app_id, draft, verify_bytes=verify_bytes)


def _duration(db, preflight, proof):
    if preflight is None:
        return
    row = db.execute("SELECT info FROM publication_preflights WHERE id=?", (preflight["id"],)).fetchone()
    info = json.loads(row["info"])
    duration = proof.get("duration_seconds")
    if type(duration) not in (int, float) or not 0 < duration <= info["max_video_post_duration_sec"]:
        raise Invalid("Video exceeds the approved TikTok creator duration")


def _preflight(db, app_id, owner, identity, draft, *, fresh=False):
    if draft["provider"] != "tiktok":
        if identity is not None:
            raise Invalid("Preflight is only supported for TikTok")
        return None
    reference(identity)
    row = db.execute("SELECT * FROM publication_preflights WHERE id=? AND app_id=?", (identity, app_id)).fetchone()
    if (
        not row
        or row["owner"] != owner
        or row["connection_id"] != draft["connection_id"]
        or row["connection_version"] != draft["connection_version"]
        or row["destination_id"] != draft["destination_id"]
        or (fresh and not 0 <= time.time() - row["created"] <= 300)
    ):
        raise Invalid("A current owner-reviewed TikTok creator preflight is required")
    info = json.loads(row["info"])
    if (
        canonical(info) != row["info"]
        or digest(info) != row["info_hash"]
        or draft["settings"]["privacy_level"] not in info["privacy_level_options"]
    ):
        raise Invalid("TikTok preflight changed or does not allow selected privacy")
    for field in ("comment", "duet", "stitch"):
        if info[field + "_disabled"] and not draft["settings"]["disable_" + field]:
            raise Invalid("TikTok interaction settings are unavailable")
    return dict(id=identity, hash=row["info_hash"])


def _record_preflight(store, app_id, connection_id, connection_version, destination_id, info):
    body = dict(connection_id=connection_id, connection_version=connection_version, destination_id=destination_id)
    context, actor, owner = _admit(store, app_id, "publication.preflight", body, True)
    fields = {
        "creator_username",
        "creator_nickname",
        "privacy_level_options",
        "max_video_post_duration_sec",
        "comment_disabled",
        "duet_disabled",
        "stitch_disabled",
    }
    allowed = {"PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"}
    if (
        not isinstance(info, dict)
        or set(info) != fields
        or not isinstance(info["privacy_level_options"], list)
        or not info["privacy_level_options"]
        or any(x not in allowed for x in info["privacy_level_options"])
        or type(info["max_video_post_duration_sec"]) is not int
        or info["max_video_post_duration_sec"] <= 0
        or any(type(info[x]) is not bool for x in ("comment_disabled", "duet_disabled", "stitch_disabled"))
    ):
        raise Invalid("Invalid TikTok creator preflight")
    for field in ("creator_username", "creator_nickname"):
        display(info[field], "creator name")
    fake = {
        "provider": "tiktok",
        "connection_id": connection_id,
        "connection_version": connection_version,
        "destination_id": destination_id,
    }
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        check(db, context)
        member(db, app_id, owner, "OWNER")
        _connection(db, app_id, fake)
        ident = uid()
        stamp = time.time()
        info = json.loads(canonical(info))
        ih = digest(info)
        db.execute(
            "INSERT INTO publication_preflights VALUES(?,?,?,?,?,?,?,?,?)",
            (ident, app_id, owner, connection_id, connection_version, destination_id, canonical(info), ih, stamp),
        )
    return dict(id=ident, info=info, info_hash=ih, created=stamp)


def record_preflight(store, app_id, connection_id, connection_version, destination_id):
    """Fetch creator settings under the exact owner admission; caller cannot supply them."""
    from .publication_credentials import context as credential_context
    from .publication_tiktok import creator_info

    body = dict(connection_id=connection_id, connection_version=connection_version, destination_id=destination_id)
    admitted, _, owner = _admit(store, app_id, "publication.preflight", body, True)
    count = 0
    fake = {"provider": "tiktok", **body}

    def heartbeat():
        with connection(store.path) as db:
            check(db, admitted)
            member(db, app_id, owner, "OWNER")
            _connection(db, app_id, fake)

    def before_call():
        nonlocal count
        heartbeat()
        if count >= 4:
            raise PermissionError("TikTok preflight read limit reached")
        count += 1

    draft = {"app_id": app_id, "provider": "tiktok", **body}
    ctx = credential_context(store, app_id, draft, before_call, heartbeat)
    info = creator_info(ctx)
    heartbeat()
    return _record_preflight(store, app_id, connection_id, connection_version, destination_id, info)


def _row(db, app_id, identity):
    reference(identity)
    row = db.execute("SELECT * FROM publication_authorities WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
    if not row:
        raise Invalid("Publication approval unavailable")
    draft = json.loads(row["draft"])
    binding = json.loads(row["binding"])
    review = {"draft": draft, "preflight_id": row["preflight_id"]}
    if (
        canonical(draft) != row["draft"]
        or digest(review) != row["review_hash"]
        or canonical(binding) != row["binding"]
        or digest(binding) != row["binding_hash"]
    ):
        raise Invalid("Publication review integrity changed")
    if row["status"] == "APPROVED" and row["approval"] is None:
        raise Invalid("Publication approval is missing")
    if row["approval"] is not None:
        approval = json.loads(row["approval"])
        if (
            canonical(approval) != row["approval"]
            or digest(approval) != row["approval_hash"]
            or approval.get("review_hash") != row["review_hash"]
            or approval.get("binding_hash") != row["binding_hash"]
            or approval.get("owner") != row["owner"]
            or approval.get("owner_version") != row["owner_version"]
            or approval.get("max_calls") != row["max_calls"]
            or iso_time(approval.get("expires_at")).timestamp() != row["expires"]
            or approval.get("confirm_publish") is not True
            or approval.get("confirm_rights") is not True
        ):
            raise Invalid("Publication approval integrity changed")
        due = approval.get("due_at")
        if due is not None and iso_time(due).timestamp() >= row["expires"]:
            raise Invalid("Publication due time exceeds the approved expiry")
    return row, draft, binding


def _view(row):
    result = {
        key: row[key]
        for key in (
            "id",
            "app_id",
            "owner",
            "owner_version",
            "app_version",
            "app_hash",
            "review_hash",
            "status",
            "version",
            "approval_hash",
            "expires",
            "max_calls",
            "calls_used",
            "created",
            "updated",
        )
    }
    result["due_at"] = json.loads(row["approval"]).get("due_at") if row["approval"] else None
    return result


def _validate(db, store, app_id, row, draft, binding, *, fresh_preflight=False, verify_bytes=True):
    exact_role(db, app_id, row["owner"], row["owner_version"], "OWNER")
    if app_scope(db, app_id) != (row["app_version"], row["app_hash"]):
        raise PermissionError("Publication app changed")
    if _connection(db, app_id, draft) != binding["connection"]:
        raise PermissionError("Publication connection changed")
    if _preflight(db, app_id, row["owner"], row["preflight_id"], draft, fresh=fresh_preflight) != binding["preflight"]:
        raise PermissionError("Publication preflight changed")
    proof = _proof(store, db, app_id, draft, verify_bytes)
    if proof != binding["proof"]:
        raise Invalid("Publication artifact or rights changed")
    _duration(db, binding["preflight"], proof)


def _current_owner(db, store, app_id, owner, recovery, charge):
    """Resolve the currently admitted owner without weakening recovery rules."""
    if recovery:
        actor = owner_context(store, app_id)
        if owner is not None and owner != actor:
            raise PermissionError("Recovery owner changed")
        return actor
    if owner is None:
        context, actor = campaign_identity(store, app_id)
        owner = scope_owner(store, context, actor)
        check(db, context)
    return owner


def _authorize_current(row, owner, recovery):
    """Require the matching owner and an active approval outside recovery."""
    if owner is not None and row["owner"] != owner:
        raise PermissionError("Publication belongs to another owner")
    if not recovery and (row["status"] != "APPROVED" or row["expires"] is None or row["expires"] <= time.time()):
        raise PermissionError("Publication approval is not active")


def _charge_current(db, identity, recovery=False):
    """Charge one HTTP request, including owner-only recovery reads, before send."""
    if not db.in_transaction:
        raise Invalid("Publication calls require an owned transaction")
    allowed = ("APPROVED", "REVOKED") if recovery else ("APPROVED", "APPROVED")
    changed = db.execute(
        "UPDATE publication_authorities SET calls_used=calls_used+1,updated=? WHERE id=? AND status IN (?,?) AND approval IS NOT NULL AND calls_used<max_calls",
        (now(), identity, *allowed),
    ).rowcount
    if not changed:
        raise PermissionError("Publication call budget exhausted")
    return db.execute("SELECT * FROM publication_authorities WHERE id=?", (identity,)).fetchone()


def _current_preflight(db, app_id, row):
    """Return the owner-reviewed TikTok facts, requiring the retained row."""
    if not row["preflight_id"]:
        return None
    saved = db.execute(
        "SELECT info FROM publication_preflights WHERE id=? AND app_id=?", (row["preflight_id"], app_id)
    ).fetchone()
    if saved is None:
        raise Invalid("Publication preflight is unavailable")
    return json.loads(saved["info"])


def current(db, store, app_id, identity, *, charge=False, owner=None, recovery=False):
    """Return the current exact approval and optionally charge one effect call."""
    owner = _current_owner(db, store, app_id, owner, recovery, charge)
    row, draft, binding = _row(db, app_id, identity)
    _authorize_current(row, owner, recovery)
    _validate(db, store, app_id, row, draft, binding, verify_bytes=False)
    if charge:
        row = _charge_current(db, identity, recovery)
    preflight = _current_preflight(db, app_id, row)
    return {"authority": _view(row), "draft": draft, "preflight": preflight}


class Publications:
    def __init__(self, store):
        self.store = store
        initialize(store)

    def prepare(self, app_id, draft, preflight_id=None):
        """Bind one validated draft to the current owner, app and connection."""
        body = {"draft": draft, "preflight_id": preflight_id}
        context, actor, owner = _admit(self.store, app_id, "publication.prepare", body)
        draft = validate_draft(draft)
        if draft["app_id"] != app_id:
            raise Invalid("Publication belongs to another app")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check(db, context)
            role = member(db, app_id, owner, "OWNER")
            version, ah = app_scope(db, app_id)
            if draft["manifest_version"] != version:
                raise Invalid("Publication app changed")
            binding = {
                "connection": _connection(db, app_id, draft),
                "preflight": _preflight(db, app_id, owner, preflight_id, draft, fresh=True),
                "proof": _proof(self.store, db, app_id, draft),
            }
            _duration(db, binding["preflight"], binding["proof"])
            review_hash = digest({"draft": draft, "preflight_id": preflight_id})
            ident = uid()
            stamp = now()
            db.execute(
                "INSERT INTO publication_authorities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    app_id,
                    owner,
                    role["version"],
                    version,
                    ah,
                    canonical(draft),
                    review_hash,
                    canonical(binding),
                    digest(binding),
                    preflight_id,
                    "PREPARED",
                    1,
                    None,
                    None,
                    None,
                    None,
                    0,
                    stamp,
                    stamp,
                ),
            )
            row = db.execute("SELECT * FROM publication_authorities WHERE id=?", (ident,)).fetchone()
        return {**_view(row), "draft": draft}

    def activate(self, app_id, identity, body):
        """Activate only the exact prepared review under fresh owner authority."""
        context, actor, owner = _admit(self.store, app_id, "publication.activate", {"id": identity, "body": body}, True)
        _validate_activation_body(body)
        observed = datetime.now(timezone.utc)
        expiry = deadline(body["expires_at"], observed, body["extended_expiry_consent"])
        due = _activation_due(body, observed, expiry)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check(db, context)
            row, draft, binding = _row(db, app_id, identity)
            if row["owner"] != owner or row["status"] != "PREPARED" or body["review_hash"] != row["review_hash"]:
                raise PermissionError("Publication review is unavailable or changed")
            _validate(db, self.store, app_id, row, draft, binding, fresh_preflight=True)
            approval = {
                "review_hash": row["review_hash"],
                "binding_hash": row["binding_hash"],
                "owner": owner,
                "owner_version": row["owner_version"],
                "expires_at": expiry.isoformat(),
                "max_calls": body["max_calls"],
                "extended_expiry_consent": body["extended_expiry_consent"],
                "confirm_publish": True,
                "confirm_rights": True,
                "due_at": due,
            }
            db.execute(
                "UPDATE publication_authorities SET status='APPROVED',version=version+1,approval=?,approval_hash=?,expires=?,max_calls=?,updated=? WHERE id=?",
                (canonical(approval), digest(approval), expiry.timestamp(), body["max_calls"], now(), identity),
            )
            row = db.execute("SELECT * FROM publication_authorities WHERE id=?", (identity,)).fetchone()
        return _view(row)

    def revoke(self, app_id, identity, version):
        """Revoke the exact approved revision and disable its queued continuation."""
        context, actor, owner = _admit(
            self.store, app_id, "publication.revoke", {"id": identity, "version": version}, True
        )
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check(db, context)
            row, draft, binding = _row(db, app_id, identity)
            if (
                row["owner"] != owner
                or type(version) is not int
                or row["version"] != version
                or row["status"] == "REVOKED"
            ):
                raise PermissionError("Publication approval changed")
            exact_role(db, app_id, owner, row["owner_version"], "OWNER")
            db.execute(
                "UPDATE publication_authorities SET status='REVOKED',version=version+1,updated=? WHERE id=?",
                (now(), identity),
            )
            # The same owner transaction disables queued continuation as well.
            # Authority can also be revoked before a schedule has been created.
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='publication_schedules'"
            ).fetchone()
            if exists:
                from .publication_schedule import disable_db

                disable_db(db, app_id, identity)
            row = db.execute("SELECT * FROM publication_authorities WHERE id=?", (identity,)).fetchone()
        return _view(row)

    def get(self, app_id, identity):
        """Read an immutable approval owned by the currently admitted principal."""
        context, actor, owner = _admit(self.store, app_id, "publication.get", {"id": identity})
        with connection(self.store.path) as db:
            row, draft, binding = _row(db, app_id, identity)
            if row["owner"] != owner:
                raise PermissionError("Publication belongs to another owner")
            return {**_view(row), "draft": draft}


def _validate_activation_body(body):
    """Validate explicit owner confirmations and the bounded call ceiling."""
    fields = {"review_hash", "expires_at", "max_calls", "extended_expiry_consent", "confirm_publish", "confirm_rights"}
    if (
        not isinstance(body, dict)
        or set(body) not in (fields, fields | {"due_at"})
        or type(body["max_calls"]) is not int
        or not 1 <= body["max_calls"] <= 500
        or type(body["extended_expiry_consent"]) is not bool
        or body["confirm_publish"] is not True
        or body["confirm_rights"] is not True
    ):
        raise Invalid("Confirm the exact publication review, rights and bounded call allowance")


def _activation_due(body, observed, expiry):
    """Normalize an optional timezone-bearing due time within approval bounds."""
    due = body.get("due_at")
    if due is not None:
        try:
            parsed = iso_time(due).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            raise Invalid("Use a timezone-bearing due time") from None
        if not observed < parsed < expiry:
            raise Invalid("Due time must be future and before approval expiry")
    return due
