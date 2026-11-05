"""Trusted, local authorization state for private read-only dashboard access."""

from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
import uuid


class Unauthenticated(PermissionError):
    """The opaque session is absent, expired, or revoked."""


class Unassigned(PermissionError):
    """The requested assignment is absent or no longer current."""


@dataclass(frozen=True)
class Admission:
    token_hash: bytes
    issuer: str
    subject: str
    tenant_id: str
    client_id: str
    client_epoch: int
    member_epoch: int
    role: str
    generation: str


_TOKEN = re.compile(r"wmmr_[A-Za-z0-9_-]{43}\Z")
_META = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ROLES = {"OWNER", "OPERATOR", "REVIEWER", "VIEWER"}
_STATUSES = {"ACTIVE", "REVOKED"}
_REASONS = {"UNAUTHENTICATED", "UNASSIGNED", "NOT_FOUND", "REGISTRY_UNAVAILABLE",
            "PROJECTION_INVALID", "AUTHORITY_CHANGED", "CONTROL_UNAVAILABLE", "INVALID_REQUEST"}


def _metadata(value):
    if not isinstance(value, str) or not _META.fullmatch(value) or "wmmr_" in value:
        raise ValueError("invalid metadata")
    return value


def _principal(value):
    if (not isinstance(value, str) or not 0 < len(value) <= 200
            or not value.isprintable() or "wmmr_" in value):
        raise ValueError("invalid identity")
    return value


def _token_hash(token):
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise Unauthenticated("invalid session")
    return hashlib.sha256(token.encode("ascii")).digest()


def _identity_time(bounds, now):
    """Only signature-verified temporal values may reach this trusted helper."""
    expires, issued, not_before = bounds
    values = (expires, issued) if not_before is None else bounds
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
        raise Unauthenticated('Identity assertion is invalid')
    if expires <= now or issued > now + 5 or (not_before is not None and not_before > now):
        raise Unauthenticated('Identity assertion is expired or not yet valid')


class Control:
    """Separate control database. Provisioning methods are trusted Python only."""

    def __init__(self, path, clock=time.time):
        self.path = str(Path(path))
        self.clock = clock
        if os.name != "nt":
            fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(fd)
            os.chmod(self.path, 0o600)
        # Bootstrap is the only create-capable connection; subsequent accesses
        # must not recreate a missing control database.
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS clients (
                    tenant_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    status TEXT NOT NULL, epoch INTEGER NOT NULL,
                    PRIMARY KEY (tenant_id, client_id));
                CREATE TABLE IF NOT EXISTS members (
                    issuer TEXT NOT NULL, subject TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    role TEXT NOT NULL, status TEXT NOT NULL, epoch INTEGER NOT NULL,
                    PRIMARY KEY (issuer, subject, tenant_id, client_id),
                    FOREIGN KEY (tenant_id, client_id) REFERENCES clients);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash BLOB PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL,
                    generation TEXT NOT NULL, idle_expiry REAL NOT NULL,
                    absolute_expiry REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS session_assignments (
                    token_hash BLOB NOT NULL, tenant_id TEXT NOT NULL, client_id TEXT NOT NULL,
                    client_epoch INTEGER NOT NULL, member_epoch INTEGER NOT NULL, role TEXT NOT NULL,
                    PRIMARY KEY (token_hash, tenant_id, client_id),
                    FOREIGN KEY (token_hash) REFERENCES sessions);
                CREATE TABLE IF NOT EXISTS receipts (
                    id TEXT PRIMARY KEY, outcome TEXT NOT NULL, reason TEXT NOT NULL,
                    tenant_id TEXT NOT NULL, client_id TEXT NOT NULL, app_id TEXT NOT NULL,
                    projection_hash TEXT NOT NULL, correlation TEXT NOT NULL,
                    issuer TEXT NOT NULL, subject TEXT NOT NULL, role TEXT NOT NULL,
                    created_at REAL NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            try:
                columns = {row[1] for row in db.execute("PRAGMA table_info(receipts)")}
                for name, column_type in (("session_generation", "TEXT"),
                                          ("client_epoch", "INTEGER"),
                                          ("member_epoch", "INTEGER")):
                    if name not in columns:
                        db.execute(f"ALTER TABLE receipts ADD COLUMN {name} {column_type}")
                db.commit()
            except BaseException:
                db.rollback()
                raise
        info = os.stat(self.path)
        self._identity = (info.st_dev, info.st_ino)

    def _check_file(self):
        try:
            info = os.stat(self.path)
        except OSError as exc:
            raise sqlite3.OperationalError("control database unavailable") from exc
        if (info.st_dev, info.st_ino) != self._identity:
            raise sqlite3.OperationalError("control database replaced")

    @contextmanager
    def _connection(self):
        self._check_file()
        uri = Path(self.path).absolute().as_uri() + "?mode=rw"
        db = sqlite3.connect(uri, timeout=5, isolation_level=None, uri=True)
        try:
            self._check_file()
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=5000")
            yield db
        finally:
            db.close()

    @contextmanager
    def _write(self):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            try:
                yield db
                self._check_file()
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _now(self):
        now = float(self.clock())
        if not math.isfinite(now):
            raise ValueError("clock must be finite")
        return now

    def register_client(self, tenant_id, client_id):
        tenant_id, client_id = _metadata(tenant_id), _metadata(client_id)
        with self._write() as db:
            db.execute("INSERT INTO clients VALUES (?, ?, 'ACTIVE', 1)", (tenant_id, client_id))

    def set_client(self, tenant_id, client_id, status):
        tenant_id, client_id = _metadata(tenant_id), _metadata(client_id)
        if status not in _STATUSES:
            raise ValueError("invalid client status")
        with self._write() as db:
            result = db.execute("UPDATE clients SET status=?, epoch=epoch+1 WHERE tenant_id=? AND client_id=?",
                                (status, tenant_id, client_id))
            if result.rowcount != 1:
                raise Unassigned("unknown client")

    def set_member(self, issuer, subject, tenant_id, client_id, role, status="ACTIVE"):
        # Issuer and subject are trusted administrator inputs, never browser claims.
        issuer, subject = _principal(issuer), _principal(subject)
        tenant_id, client_id = _metadata(tenant_id), _metadata(client_id)
        if role not in _ROLES or status not in _STATUSES:
            raise ValueError("invalid membership")
        with self._write() as db:
            db.execute("""INSERT INTO members VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT (issuer, subject, tenant_id, client_id)
                DO UPDATE SET role=excluded.role, status=excluded.status, epoch=members.epoch+1""",
                (issuer, subject, tenant_id, client_id, role, status))

    def issue_session(self, issuer, subject, max_age=28800, *, verified_times=None):
        if isinstance(max_age, bool) or not isinstance(max_age, (int, float)) or not math.isfinite(max_age) or not 0 < max_age <= 28800:
            raise ValueError("invalid session duration")
        token = "wmmr_" + secrets.token_urlsafe(32)
        token_hash = _token_hash(token)
        with self._write() as db:
            now = self._now()
            if verified_times is not None:
                _identity_time(verified_times, now)
            assignments = db.execute("""SELECT m.tenant_id, m.client_id, c.epoch AS client_epoch,
                    m.epoch AS member_epoch, m.role FROM members m JOIN clients c
                    ON c.tenant_id=m.tenant_id AND c.client_id=m.client_id
                    WHERE m.issuer=? AND m.subject=? AND m.status='ACTIVE' AND c.status='ACTIVE'""",
                    (issuer, subject)).fetchall()
            if not assignments:
                raise Unassigned("no active assignment")
            absolute = now + max_age
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, 0)",
                       (token_hash, issuer, subject, secrets.token_hex(16), min(now + 900, absolute), absolute))
            db.executemany("INSERT INTO session_assignments VALUES (?, ?, ?, ?, ?, ?)",
                           [(token_hash, a['tenant_id'], a['client_id'], a['client_epoch'],
                             a['member_epoch'], a['role']) for a in assignments])
        return token

    def issue_verified_session(self, identity):
        """Recheck verified assertion time after acquiring the issuance lock."""
        return self.issue_session(_principal(identity.issuer), _principal(identity.subject),
                                  verified_times=(identity.expires, identity.issued_at, identity.not_before))

    def _choices(self, db, token_hash, now):
        rows = db.execute("""SELECT tenant_id,client_id FROM session_assignments
                             WHERE token_hash=? ORDER BY tenant_id,client_id LIMIT 21""",
                          (token_hash,)).fetchall()
        if not rows:
            raise Unauthenticated('Sign in to an assigned workspace')
        choices = [self._admission(db, token_hash, row['tenant_id'], row['client_id'], now)
                   for row in rows]
        return choices[:20], len(choices) > 20

    def choices(self, token):
        """List only current session snapshots, with an explicit finite cap."""
        token_hash = _token_hash(token)
        with self._connection() as db:
            db.execute('BEGIN')
            return self._choices(db, token_hash, self._now())

    def finish_choices(self, token, admissions, more_available):
        """Revalidate the entire list after app-name collection, atomically."""
        token_hash = _token_hash(token)
        with self._write() as db:
            now = self._now()
            if self._choices(db, token_hash, now) != (admissions, more_available):
                raise Unassigned('Workspace assignments changed')
            db.execute('UPDATE sessions SET idle_expiry=MIN(absolute_expiry, ?) WHERE token_hash=?',
                       (now + 900, token_hash))

    def revoke_session(self, token):
        token_hash = _token_hash(token)
        with self._write() as db:
            db.execute("UPDATE sessions SET revoked=1 WHERE token_hash=?", (token_hash,))

    def _admission(self, db, token_hash, tenant_id, client_id, now):
        session = db.execute("SELECT * FROM sessions WHERE token_hash=?", (token_hash,)).fetchone()
        if session is None or session['revoked'] or session['idle_expiry'] <= now or session['absolute_expiry'] <= now:
            raise Unauthenticated("invalid session")
        row = db.execute("""SELECT a.client_epoch, a.member_epoch, a.role FROM session_assignments a
            JOIN clients c ON c.tenant_id=a.tenant_id AND c.client_id=a.client_id
            JOIN members m ON m.tenant_id=a.tenant_id AND m.client_id=a.client_id
                AND m.issuer=? AND m.subject=?
            WHERE a.token_hash=? AND a.tenant_id=? AND a.client_id=?
                AND c.status='ACTIVE' AND c.epoch=a.client_epoch
                AND m.status='ACTIVE' AND m.epoch=a.member_epoch AND m.role=a.role""",
            (session['issuer'], session['subject'], token_hash, tenant_id, client_id)).fetchone()
        if row is None:
            raise Unassigned("assignment unavailable")
        return Admission(token_hash, session['issuer'], session['subject'], tenant_id, client_id,
                         row['client_epoch'], row['member_epoch'], row['role'], session['generation'])

    def admit(self, token, tenant_id, client_id):
        token_hash = _token_hash(token)
        tenant_id, client_id = _metadata(tenant_id), _metadata(client_id)
        with self._connection() as db:
            # One snapshot prevents mixed authority if an update races the read.
            db.execute("BEGIN")
            return self._admission(db, token_hash, tenant_id, client_id, self._now())

    def finish(self, admission, app_id, projection_hash, correlation):
        app_id, correlation = _metadata(app_id), _metadata(correlation)
        if not isinstance(projection_hash, str) or not _HASH.fullmatch(projection_hash):
            raise ValueError("invalid projection hash")
        with self._write() as db:
            now = self._now()
            current = self._admission(db, admission.token_hash, admission.tenant_id, admission.client_id, now)
            if current != admission:
                raise Unassigned("assignment changed")
            db.execute("UPDATE sessions SET idle_expiry=MIN(absolute_expiry, ?) WHERE token_hash=?",
                       (now + 900, admission.token_hash))
            receipt_id = uuid.uuid4().hex
            db.execute("""INSERT INTO receipts
                       (id, outcome, reason, tenant_id, client_id, app_id, projection_hash,
                        correlation, issuer, subject, role, created_at, session_generation,
                        client_epoch, member_epoch)
                       VALUES (?, 'ALLOWED', '', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (receipt_id, admission.tenant_id, admission.client_id, app_id, projection_hash,
                        correlation, admission.issuer, admission.subject, admission.role, now,
                        admission.generation, admission.client_epoch, admission.member_epoch))
        return receipt_id

    def denied(self, token, tenant_id, client_id, app_id, reason, correlation):
        tenant_id, client_id, app_id, correlation = map(_metadata, (tenant_id, client_id, app_id, correlation))
        reason = reason if reason in _REASONS else "INVALID_REQUEST"
        receipt_id = uuid.uuid4().hex
        with self._write() as db:
            db.execute("""INSERT INTO receipts
                       (id, outcome, reason, tenant_id, client_id, app_id, projection_hash,
                        correlation, issuer, subject, role, created_at)
                       VALUES (?, 'DENIED', ?, ?, ?, ?, '', ?, '', '', '', ?)""",
                       (receipt_id, reason, tenant_id, client_id, app_id, correlation, self._now()))
        return receipt_id

    def receipts(self):
        with self._connection() as db:
            return [dict(row) for row in db.execute("SELECT * FROM receipts ORDER BY rowid")]
