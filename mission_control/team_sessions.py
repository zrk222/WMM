"""Durable team sessions bound to a verified GitHub identity; no passwords or raw tokens stored."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from .common import Invalid, iso_time, now, uid
from .db import connection
from .operator_identity import github_read
from .review_access import member

TOKEN = re.compile(r"wmms_[A-Za-z0-9_-]{43}")
GITHUB = re.compile(r"[A-Za-z0-9_]{20,256}")


def token_hash(token):
    """Store only a SHA-256 of the one-time session credential."""
    if not isinstance(token, str) or not TOKEN.fullmatch(token):
        raise Invalid("Use a valid team session credential")
    return hashlib.sha256(token.encode()).hexdigest()


def _public(row):
    value = dict(row)
    value.pop("token_hash", None)
    return value


def _ttl(hours):
    if type(hours) is not int or not 1 <= hours <= 720:
        raise Invalid("Session lifetime must be between 1 and 720 hours")
    return hours


def open_session(store, app_id, user, hours=8):
    """Create one app-scoped session for an already verified identity."""
    store.app(app_id)
    if (not isinstance(user, dict) or not isinstance(user.get("principal"), str)
            or not user["principal"] or not isinstance(user.get("login"), str) or not user["login"]):
        raise PermissionError("A verified teammate identity is required")
    hours = _ttl(hours)
    observed = datetime.now(timezone.utc)
    token = "wmms_" + secrets.token_urlsafe(32)
    identity = uid()
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        member(db, app_id, user["principal"])
        db.execute("INSERT INTO team_sessions VALUES(?,?,?,?,?,?,?,?,?,?)",
                   (app_id, identity, token_hash(token), user["principal"], user["login"], "GITHUB",
                    observed.isoformat(), (observed + timedelta(hours=hours)).isoformat(), 0, 1))
        row = dict(db.execute("SELECT * FROM team_sessions WHERE app_id=? AND id=?",
                              (app_id, identity)).fetchone())
    return dict(session=_public(row), token=token, token_delivery="ONCE_ONLY")


def login(store, app_id, github_token, hours=8):
    """Verify a GitHub token through the fixed identity reader, then open a session."""
    store.app(app_id)
    if not isinstance(github_token, str) or not GITHUB.fullmatch(github_token):
        raise Invalid("Enter a GitHub personal access token; no repository permissions are needed")
    return open_session(store, app_id, github_read("/user", github_token), hours)


def verify(store, token):
    """Resolve a current session; revoked or expired sessions are denied."""
    digest = token_hash(token)
    with connection(store.path) as db:
        row = db.execute("SELECT * FROM team_sessions WHERE token_hash=?", (digest,)).fetchone()
        if row is None:
            raise PermissionError("Team session is unknown")
        if row["revoked"]:
            raise PermissionError("Team session was revoked")
        if iso_time(row["expires"]) <= datetime.now(timezone.utc):
            raise PermissionError("Team session expired")
        current = member(db, row["app_id"], row["principal"])
    store.app(row["app_id"])
    return dict(app_id=row["app_id"], session_id=row["id"], principal=row["principal"],
                login=row["login"], provider=row["provider"], expires=row["expires"],
                role=current["role"], role_version=current["version"])


def revoke(store, app_id, owner, identity, version):
    """An app owner revokes one session by exact identity and version."""
    store.app(app_id)
    if type(version) is not int:
        raise Invalid("Use the current session version")
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        member(db, app_id, owner["principal"], "OWNER")
        changed = db.execute("UPDATE team_sessions SET revoked=1,version=version+1 "
                             "WHERE app_id=? AND id=? AND revoked=0 AND version=?",
                             (app_id, identity, version)).rowcount
        if changed != 1:
            raise Invalid("Session is unknown, already revoked or changed")
    return list_sessions(store, app_id, owner)


def list_sessions(store, app_id, owner):
    """Owner-only session history without credentials or token hashes."""
    store.app(app_id)
    with connection(store.path) as db:
        member(db, app_id, owner["principal"], "OWNER")
        rows = [dict(row) for row in db.execute(
            "SELECT * FROM team_sessions WHERE app_id=? ORDER BY created DESC,id LIMIT 100", (app_id,))]
    return dict(app_id=app_id, sessions=[_public(row) for row in rows],
                scope="App-scoped GitHub identity sessions; no hosted tenant or password storage.")
