"""One-time app invitations for the existing OWNER/MAKER/CHECKER roles."""

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from .common import Invalid, iso_time, now, uid
from .db import connection
from .review_access import Access, member

TOKEN = re.compile(r"wmmi_[A-Za-z0-9_-]{43}")
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?")
ROLES = ("MAKER", "CHECKER")


def _exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid("Use the exact team invitation fields")


def token_hash(token):
    """Never store the one-time invitation credential in plaintext."""
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise Invalid("Use a valid invitation credential")
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row):
    value = dict(row)
    value.pop("token_hash", None)
    return value


def _effective(row, observed):
    if row["status"] == "PENDING" and iso_time(row["expires"]) <= observed:
        return "EXPIRED"
    return row["status"]


def issue(store, app_id, owner, body):
    """Owner issues one bounded invitation and receives the credential once."""
    store.app(app_id)
    _exact(body, ("login", "role", "expires"))
    login = body["login"]
    if not isinstance(login, str) or not LOGIN.fullmatch(login):
        raise Invalid("Use a GitHub account login")
    if body["role"] not in ROLES:
        raise Invalid("Invitations may assign MAKER or CHECKER only")
    observed = datetime.now(timezone.utc)
    try:
        expires = iso_time(body["expires"])
    except Exception as exc:
        raise Invalid("Invitation expiry must be an ISO timestamp") from exc
    if not observed + timedelta(hours=1) <= expires <= observed + timedelta(days=7):
        raise Invalid("Invitation expiry must be within one hour and seven days")
    token = "wmmi_" + secrets.token_urlsafe(32)
    identity = uid()
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        member(db, app_id, owner["principal"], "OWNER")
        existing = db.execute(
            "SELECT * FROM operator_roles WHERE app_id=? AND login=? COLLATE NOCASE", (app_id, login)
        ).fetchone()
        if existing and existing["role"] == "OWNER":
            raise Invalid("The established owner cannot be invited as a teammate")
        db.execute(
            "INSERT INTO team_invitations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                app_id,
                identity,
                token_hash(token),
                login,
                body["role"],
                "PENDING",
                expires.isoformat(),
                now(),
                owner["principal"],
                owner["login"],
                None,
                None,
                1,
            ),
        )
        row = dict(db.execute("SELECT * FROM team_invitations WHERE app_id=? AND id=?", (app_id, identity)).fetchone())
    return dict(invitation=_public(row), token=token, token_delivery="ONCE_ONLY")


def accept(store, token, user):
    """Consume one invitation for the matching verified login; never grants OWNER."""
    if (
        not isinstance(user, dict)
        or not isinstance(user.get("principal"), str)
        or not isinstance(user.get("login"), str)
    ):
        raise PermissionError("A verified teammate identity is required")
    digest = token_hash(token)
    observed = datetime.now(timezone.utc)
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM team_invitations WHERE token_hash=?", (digest,)).fetchone()
        if row is None:
            raise Invalid("Invitation is unknown or already used")
        if _effective(row, observed) != "PENDING":
            raise Invalid("Invitation is expired, revoked or already accepted")
        if row["login"].lower() != user["login"].lower():
            raise PermissionError("This invitation belongs to another GitHub account")
        app_id = row["app_id"]
        existing = db.execute(
            "SELECT * FROM operator_roles WHERE app_id=? AND principal=?", (app_id, user["principal"])
        ).fetchone()
        if existing and existing["role"] == "OWNER":
            raise Invalid("The established owner cannot accept a teammate invitation")
        version = (existing["version"] + 1) if existing else 1
        Access(store).write(db, app_id, user, row["role"], "ACTIVE", version, user["principal"])
        changed = db.execute(
            "UPDATE team_invitations SET status='ACCEPTED',accepted_by=?,accepted_at=?,"
            "version=version+1 WHERE app_id=? AND id=? AND status='PENDING' AND version=?",
            (user["principal"], now(), app_id, row["id"], row["version"]),
        ).rowcount
        if changed != 1:
            raise Invalid("Invitation changed before acceptance; reload")
    return dict(status="ACTIVE", app_id=app_id, role=row["role"], invitation_id=row["id"])


def revoke(store, app_id, owner, body):
    """Owner revokes a pending invitation by exact identity and version."""
    store.app(app_id)
    _exact(body, ("id", "version"))
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        member(db, app_id, owner["principal"], "OWNER")
        if type(body["version"]) is not int:
            raise Invalid("Use the current invitation version")
        changed = db.execute(
            "UPDATE team_invitations SET status='REVOKED',version=version+1 "
            "WHERE app_id=? AND id=? AND status='PENDING' AND version=?",
            (app_id, body["id"], body["version"]),
        ).rowcount
        if changed != 1:
            raise Invalid("Invitation is unknown, already handled or changed")
    return list_invitations(store, app_id, owner)


def list_invitations(store, app_id, owner):
    """Owner-only invitation history without credentials or token hashes."""
    store.app(app_id)
    observed = datetime.now(timezone.utc)
    with connection(store.path) as db:
        member(db, app_id, owner["principal"], "OWNER")
        rows = [
            dict(row)
            for row in db.execute(
                "SELECT * FROM team_invitations WHERE app_id=? ORDER BY created DESC,id LIMIT 100", (app_id,)
            )
        ]
    return dict(
        app_id=app_id,
        invitations=[dict(_public(row), status=_effective(row, observed)) for row in rows],
        scope="Single-use app invitations for MAKER or CHECKER only; no hosted tenancy or public signup.",
    )
