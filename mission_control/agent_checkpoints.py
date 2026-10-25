"""Durable admission primitives for trusted adapters; no authentication or dispatch.

Principals passed here MUST come from a separately authenticated adapter. This
internal interface cannot establish a human identity from a caller-supplied name.
Approval records are intentionally absent from portable snapshot exports.
"""
from datetime import datetime, timedelta, timezone
import json
from .common import Invalid, canonical, digest, identifier, iso_time
from .db import connection
from .pmf_contract import exact
from .review_access import member, exact_role
from .operation_catalog import OPERATIONS as LOCAL_OPERATIONS


OPERATIONS = ("READ_WORKSPACE", "RECOMPUTE_REPORT", "PREPARE_DRAFT", *LOCAL_OPERATIONS)
_READ = object()


def packet_data(db, app_id, principal, body, observed):
    """Freeze narrow operation metadata, not credentials or executable commands."""
    exact(body, {"id", "agent_id", "operation", "input_hash", "manifest_version", "expires"})
    identifier(body["id"])
    identifier(body["agent_id"])
    if body["operation"] not in OPERATIONS:
        raise Invalid("This checkpoint supports only bounded local operations")
    hashed(body["input_hash"])
    expiry = iso_time(body["expires"])
    if not observed < expiry <= observed + timedelta(hours=24):
        raise Invalid("Checkpoint expiry must be in the next 24 hours")
    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if not app or type(body["manifest_version"]) is not int or body["manifest_version"] != app["version"]:
        raise Invalid("Checkpoint manifest changed")
    role = member(db, app_id, principal, "MAKER")
    return dict(body, app_id=app_id, app_hash=digest(json.loads(app["data"])),
                maker=principal, maker_role_version=role["version"])


def hashed(value):
    """Accept exact lowercase SHA256 references, without arbitrary payload text."""
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise Invalid("Use a lowercase SHA256 content hash")
    return value


def current(db, row, observed):
    """Recheck every admission dependency before approving or claiming work."""
    packet = row["packet"]
    if digest(packet) != row["hash"] or iso_time(packet["expires"]) <= observed:
        raise Invalid("Checkpoint changed or expired; prepare a fresh request")
    app = db.execute("SELECT * FROM apps WHERE id=?", (packet["app_id"],)).fetchone()
    if not app or app["version"] != packet["manifest_version"] or digest(json.loads(app["data"])) != packet["app_hash"]:
        raise Invalid("Checkpoint app scope changed")
    exact_role(db, packet["app_id"], packet["maker"], packet["maker_role_version"], "MAKER")
    if row["checker"]:
        exact_role(db, packet["app_id"], row["checker"], row["checker_role_version"], "CHECKER")


def read_row(db, app_id, identity, revision=_READ):
    """Use app-owned identity and an exact optimistic revision for mutation."""
    stored = db.execute("SELECT * FROM agent_checkpoints WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
    if not stored:
        raise Invalid("Checkpoint was not found in this app")
    row = json.loads(stored["data"])
    if revision is not _READ and (type(revision) is not int or revision != stored["revision"]):
        raise Invalid("Checkpoint revision changed; reload")
    return row


def persist(db, row, state, actor, observed, evidence=None):
    """Append immutable transition evidence in the same transaction as state."""
    event = dict(state=state, actor=actor, observed_at=observed.isoformat(), evidence_hash=evidence,
                 previous_hash=row["history"][-1]["hash"] if row["history"] else None)
    row["history"].append(dict(event, hash=digest(event)))
    row.update(state=state, revision=row["revision"] + 1)
    packet = row["packet"]
    db.execute("INSERT INTO agent_checkpoints VALUES(?,?,?,?) ON CONFLICT(app_id,id) DO UPDATE SET data=excluded.data,revision=excluded.revision",
               (packet["app_id"], packet["id"], canonical(row), row["revision"]))
    return row


def prepare_in_db(db,app_id,principal,body,observed):
    """Share immutable preparation with adapters that already hold a writer transaction."""
    packet=packet_data(db,app_id,principal,body,observed)
    old=db.execute('SELECT data FROM agent_checkpoints WHERE app_id=? AND id=?',(app_id,body['id'])).fetchone()
    if old:
        row=json.loads(old['data'])
        if row['hash']!=digest(packet):raise Invalid('Checkpoint identity is immutable')
        return row
    row=dict(packet=packet,hash=digest(packet),state='WAITING_REVIEW',revision=0,checker=None,checker_role_version=None,history=[])
    return persist(db,row,'WAITING_REVIEW',principal,observed)


def claim_in_db(db,app_id,identity,agent_id,revision,packet_hash,observed):
    """Share exclusive current admission with a grant-bound effect dispatcher."""
    row=read_row(db,app_id,identity,revision)
    if row['state']!='APPROVED' or row['packet']['agent_id']!=agent_id or row['hash']!=packet_hash:
        raise Invalid('Claim requires the approved agent, exact hash and current state')
    current(db,row,observed)
    return persist(db,row,'RUNNING',agent_id,observed)


class Checkpoints:
    """Serialize trusted-service calls. Authentication and effect adapters are separate."""

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def prepare(self, app_id, principal, body):
        """Create immutable intent; identical replay cannot resurrect authority."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            return prepare_in_db(db,app_id,principal,body,self.clock())

    def inspect(self, app_id, identity):
        """Return durable state and derived availability without granting permission."""
        with connection(self.store.path) as db:
            row = read_row(db, app_id, identity)
            try:
                current(db, row, self.clock())
                available = row["state"] == "APPROVED"
            except (Invalid, PermissionError):
                available = False
        return dict(row, claim_available=available, reconciliation_required=row["state"] in ("RUNNING", "UNKNOWN", "CANCEL_REQUESTED"))

    def approve(self, app_id, identity, principal, revision, packet_hash):
        """Require an authenticated adapter's distinct current checker identity."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = read_row(db, app_id, identity, revision)
            role = member(db, app_id, principal, "CHECKER")
            if row["state"] != "WAITING_REVIEW" or row["hash"] != packet_hash or row["packet"]["maker"] == principal:
                raise Invalid("Review requires waiting intent, exact hash and a distinct checker")
            current(db, row, self.clock())
            row.update(checker=principal, checker_role_version=role["version"])
            return persist(db, row, "APPROVED", principal, self.clock())

    def claim(self, app_id, identity, agent_id, revision, packet_hash):
        """Admit once; an effect adapter must separately validate input and grants."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            return claim_in_db(db,app_id,identity,agent_id,revision,packet_hash,self.clock())

    def finish(self, app_id, identity, agent_id, revision, outcome, evidence_hash):
        """Record a receipt even after expiry; never authorize an automatic retry."""
        hashed(evidence_hash)
        if outcome not in ("SUCCEEDED", "FAILED", "UNKNOWN"):
            raise Invalid("Record succeeded, failed or unknown outcome")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = read_row(db, app_id, identity, revision)
            if row["state"] != "RUNNING" or row["packet"]["agent_id"] != agent_id:
                raise Invalid("Only the current claimed agent may record its outcome")
            return persist(db, row, outcome, agent_id, self.clock(), evidence_hash)

    def cancel(self, app_id, identity, principal, revision):
        """Revoke admission; a running action cannot be assumed to have stopped."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = read_row(db, app_id, identity, revision)
            role = member(db, app_id, principal)
            if principal not in (row["packet"]["maker"], row["checker"]) and role["role"] != "OWNER":
                raise PermissionError("Only the maker, checker or owner may cancel")
            if row["state"] not in ("WAITING_REVIEW", "APPROVED", "RUNNING"):
                raise Invalid("Checkpoint is terminal or already awaiting reconciliation")
            state = "CANCEL_REQUESTED" if row["state"] == "RUNNING" else "CANCELLED"
            return persist(db, row, state, principal, self.clock())

    def reconcile(self, app_id, identity, principal, revision, outcome, evidence_hash):
        """A current distinct checker records evidence, without rearming admission."""
        hashed(evidence_hash)
        if outcome not in ("SUCCEEDED", "FAILED"):
            raise Invalid("Reconciliation requires a known outcome")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = read_row(db, app_id, identity, revision)
            member(db, app_id, principal, "CHECKER")
            if row["state"] not in ("UNKNOWN", "CANCEL_REQUESTED") or principal == row["packet"]["maker"]:
                raise Invalid("Only distinct checkers may reconcile uncertain work")
            return persist(db, row, outcome, principal, self.clock(), evidence_hash)
