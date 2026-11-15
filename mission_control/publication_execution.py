"""One approved organic action, durable phases and read-only reconciliation.

Each HTTP request consumes one committed allowance reservation. A pending mutation
is never automatically replayed. The OS lock serializes local executions; approval
revocation prevents subsequent admission but cannot recall an in-flight request.
"""

from dataclasses import dataclass
import json, re, time
from .common import Invalid, canonical, digest, now, safe_data, uid
from .db import connection
from .campaign_locks import paid_lock
from .publication_authority import current, _admit
from .publication_contract import channel_descriptor
from . import publication_sessions as sessions
from .publication_schedule import check_job

SCHEMA = """
CREATE TABLE IF NOT EXISTS publication_intents(
 id TEXT PRIMARY KEY,app_id TEXT NOT NULL,authority_id TEXT NOT NULL UNIQUE,
 owner TEXT NOT NULL,request_hash TEXT NOT NULL,channel_hash TEXT NOT NULL,
 state TEXT NOT NULL,state_hash TEXT NOT NULL,status TEXT NOT NULL,
 pending TEXT,pending_action TEXT,session_checkpoint TEXT,
 version INTEGER NOT NULL,attention INTEGER NOT NULL,created TEXT NOT NULL,updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS publication_events(
 intent_id TEXT NOT NULL,sequence INTEGER NOT NULL,data TEXT NOT NULL,
 hash TEXT NOT NULL,previous_hash TEXT NOT NULL,PRIMARY KEY(intent_id,sequence));
CREATE TRIGGER IF NOT EXISTS publication_intent_binding BEFORE UPDATE ON publication_intents
 WHEN NEW.id!=OLD.id OR NEW.app_id!=OLD.app_id OR NEW.authority_id!=OLD.authority_id
 OR NEW.owner!=OLD.owner OR NEW.request_hash!=OLD.request_hash OR NEW.channel_hash!=OLD.channel_hash
 OR NEW.created!=OLD.created OR NEW.version!=OLD.version+1
 BEGIN SELECT RAISE(ABORT,'Publication intent binding changed'); END;
CREATE TRIGGER IF NOT EXISTS publication_intent_no_replace BEFORE INSERT ON publication_intents
 WHEN EXISTS(SELECT 1 FROM publication_intents WHERE id=NEW.id OR authority_id=NEW.authority_id)
 BEGIN SELECT RAISE(ABORT,'Publication intent already exists'); END;
CREATE TRIGGER IF NOT EXISTS publication_intent_no_delete BEFORE DELETE ON publication_intents
 BEGIN SELECT RAISE(ABORT,'Publication intent is retained'); END;
CREATE TRIGGER IF NOT EXISTS publication_event_no_update BEFORE UPDATE ON publication_events
 BEGIN SELECT RAISE(ABORT,'Publication event is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_event_no_delete BEFORE DELETE ON publication_events
 BEGIN SELECT RAISE(ABORT,'Publication event is immutable'); END;
CREATE TRIGGER IF NOT EXISTS publication_event_no_replace BEFORE INSERT ON publication_events
 WHEN EXISTS(SELECT 1 FROM publication_events WHERE intent_id=NEW.intent_id AND sequence=NEW.sequence)
 BEGIN SELECT RAISE(ABORT,'Publication event already exists'); END;
"""


def _adapter(provider):
    # Explicit imports keep the registry closed and visible to frozen bundlers.
    from . import publication_meta, publication_linkedin, publication_youtube, publication_tiktok

    return {
        "instagram": publication_meta,
        "linkedin": publication_linkedin,
        "youtube": publication_youtube,
        "tiktok": publication_tiktok,
    }[provider]


_NEXT = {
    "NEW": {"CREATED", "READY_TO_PUBLISH"},
    "CREATED": {"UPLOAD_IN_PROGRESS", "UPLOADED", "PROCESSING"},
    "UPLOAD_IN_PROGRESS": {"UPLOAD_IN_PROGRESS", "UPLOADED", "PROCESSING"},
    "UPLOADED": {"PROCESSING", "PUBLISH_ACKNOWLEDGED"},
    "PROCESSING": {"PROCESSING", "READY_TO_PUBLISH", "PUBLISHED"},
    "READY_TO_PUBLISH": {"PUBLISH_ACKNOWLEDGED"},
    "PUBLISH_ACKNOWLEDGED": {"PROCESSING", "PUBLISHED"},
    "PUBLISHED": {"PUBLISHED"},
}


@dataclass(frozen=True)
class PreparedPublicationStep:
    result: dict
    reschedule_at: float | None


def initialize(store):
    with connection(store.path) as db:
        db.executescript(SCHEMA)


def _state(status="NEW"):
    return dict(status=status, remote_id=None, asset_id=None, session=None, observation={})


def _public(state):
    if not isinstance(state, dict) or set(state) != {"status", "remote_id", "asset_id", "session", "observation"}:
        raise Invalid("Publication adapter state is incomplete")
    if state["status"] not in {*_NEXT, "FAILED", "UNKNOWN"}:
        raise Invalid("Unknown publication phase")
    for key in ("remote_id", "asset_id"):
        value = state[key]
        if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.~:-]{1,200}", value)):
            raise Invalid("Invalid provider publication identifier")
    value = {key: state[key] for key in ("status", "remote_id", "asset_id", "observation")}
    safe_data(value)
    if len(canonical(value).encode()) > 16384:
        raise Invalid("Publication observation exceeds limit")
    # Provider adapters return interpreted fields only, never upload capabilities.
    if re.search(
        r'"[^"\\]*(?:token|secret|session|upload_url|uploadUrl|authorization)[^"\\]*"\s*:', canonical(value), re.I
    ):
        raise Invalid("Private provider state cannot be included in a receipt")
    return value


def _row(db, app_id, identity):
    row = db.execute("SELECT * FROM publication_intents WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
    if not row:
        raise Invalid("Publication intent unavailable")
    state = json.loads(row["state"])
    if canonical(state) != row["state"] or digest(state) != row["state_hash"]:
        raise Invalid("Publication state integrity changed")
    return row, state


def _view(db, row):
    state = json.loads(row["state"])
    event = db.execute(
        "SELECT * FROM publication_events WHERE intent_id=? ORDER BY sequence DESC LIMIT 1", (row["id"],)
    ).fetchone()
    if not event:
        raise Invalid("Publication receipt unavailable")
    data = json.loads(event["data"])
    if (
        digest(data) != event["hash"]
        or data.get("state_hash") != row["state_hash"]
        or data.get("version") != row["version"]
    ):
        raise Invalid("Publication receipt integrity changed")
    result = dict(
        id=row["id"],
        authority_id=row["authority_id"],
        app_id=row["app_id"],
        status=row["status"],
        phase=state["status"],
        remote_id=state["remote_id"],
        asset_id=state["asset_id"],
        observation=state["observation"],
        channel_hash=row["channel_hash"],
        version=row["version"],
        receipt_hash=event["hash"],
        requires_attention=bool(row["attention"]),
        monitoring=False,
        updated=row["updated"],
    )
    result["next_action"] = (
        "Check the saved provider state, then use Reconcile. Do not submit the same post again."
        if row["attention"]
        else "The worker will continue within your approved allowance."
    )
    return result


def _event(db, row, action, attempt):
    previous = db.execute(
        "SELECT sequence,hash FROM publication_events WHERE intent_id=? ORDER BY sequence DESC LIMIT 1", (row["id"],)
    ).fetchone()
    prev = previous["hash"] if previous else ""
    seq = previous["sequence"] + 1 if previous else 1
    value = dict(
        intent_id=row["id"],
        app_id=row["app_id"],
        authority_id=row["authority_id"],
        request_hash=row["request_hash"],
        channel_hash=row["channel_hash"],
        version=row["version"],
        status=row["status"],
        state_hash=row["state_hash"],
        action=action,
        attempt=attempt,
        previous_hash=prev,
        observed_at=now(),
    )
    # Preserve historical public observations after the current intent advances
    # and superseded protected upload-session checkpoints are retired.
    value["state"] = json.loads(row["state"]) if action in ("create", "upload", "publish", "read") else None
    db.execute(
        "INSERT INTO publication_events VALUES(?,?,?,?,?)", (row["id"], seq, canonical(value), digest(value), prev)
    )


def _ensure(db, app_id, approved):
    authority = approved["authority"]
    draft = approved["draft"]
    identity = authority["id"]
    binding = digest({"approval": authority["approval_hash"], "draft": draft})
    channel = digest(channel_descriptor(draft))
    old = db.execute("SELECT * FROM publication_intents WHERE id=?", (identity,)).fetchone()
    if old:
        row, state = _row(db, app_id, identity)
        if row["request_hash"] != binding or row["owner"] != authority["owner"] or row["channel_hash"] != channel:
            raise PermissionError("Publication intent no longer matches approval")
        return row, state
    state = _public(_state())
    stamp = now()
    db.execute(
        "INSERT INTO publication_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            identity,
            app_id,
            identity,
            authority["owner"],
            binding,
            channel,
            canonical(state),
            digest(state),
            "NEW",
            None,
            None,
            None,
            1,
            0,
            stamp,
            stamp,
        ),
    )
    row, state = _row(db, app_id, identity)
    _event(db, row, "PREPARED", 0)
    return row, state


def _full(store, row, state):
    if row["session_checkpoint"]:
        full = sessions.load(store, row["app_id"], row["id"], row["request_hash"], row["session_checkpoint"])
        if _public(full) != state:
            raise Invalid("Protected checkpoint differs from retained receipt")
        return full
    return {**state, "session": None}


def _guard(store, job, identity, pending=None, charge=False):
    # Commit before returning to transport. A network exception cannot refund it.
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        owner = check_job(db, store, job)
        approved = current(db, store, job["app_id"], identity, owner=owner, charge=charge)
        row, _ = _row(db, job["app_id"], identity)
        if row["pending"] != pending:
            raise PermissionError("Publication checkpoint changed")
        db.execute(
            "UPDATE jobs SET lease=?,updated=? WHERE id=? AND status='RUNNING' AND attempts=?",
            (time.time() + 360, now(), job["id"], job["attempts"]),
        )
    return approved


def _advance_allowed(before, after, action):
    if after in _NEXT.get(before, set()) | {"FAILED", "UNKNOWN"}:
        return True
    # A verified status read can observe provider progress after a lost response.
    # This grants no create/upload/publish action and never permits regression.
    if action != "read" or before not in ("CREATED", "UPLOAD_IN_PROGRESS", "UPLOADED"):
        return False
    return after in ("PROCESSING", "READY_TO_PUBLISH", "PUBLISHED")


def _save(db, row, state, checkpoint, action, attempt, attention=False):
    public = _public(state)
    before = json.loads(row["state"])["status"]
    after = state["status"]
    if not _advance_allowed(before, after, action):
        raise Invalid("Publication phase regressed or was not allowed")
    if after == "PUBLISHED" and (action != "read" or not (public["remote_id"] or public["asset_id"])):
        raise Invalid("Published status needs a provider read and retained identifier")
    db.execute(
        "UPDATE publication_intents SET state=?,state_hash=?,status=?,session_checkpoint=?,pending=NULL,pending_action=NULL,version=version+1,attention=?,updated=? WHERE id=? AND version=?",
        (canonical(public), digest(public), after, checkpoint, int(attention), now(), row["id"], row["version"]),
    )
    saved, _ = _row(db, row["app_id"], row["id"])
    _event(db, saved, action, attempt)
    return saved


def _attention(state):
    return state["status"] in ("FAILED", "UNKNOWN") or state["observation"].get("requires_attention") is True


def _hold(db, row, action, attempt):
    # Keep the last known state and pending response checkpoint for reconciliation.
    db.execute(
        "UPDATE publication_intents SET status='UNKNOWN',attention=1,version=version+1,updated=? WHERE id=? AND version=?",
        (now(), row["id"], row["version"]),
    )
    saved, _ = _row(db, row["app_id"], row["id"])
    _event(db, saved, action, attempt)
    return saved


def verified_result(db, app_id, identity, result):
    """Scheduler accepts only the current hash-bound executor receipt."""
    row, _ = _row(db, app_id, identity)
    view = _view(db, row)
    for key, value in view.items():
        if key != "monitoring" and result.get(key) != value:
            raise Invalid("Publication result differs from retained receipt")
    if type(result.get("monitoring")) is not bool:
        raise Invalid("Invalid publication monitoring state")
    return view


class _Execution:
    """Private worker orchestration; no caller-provided owner or provider session."""

    def __init__(self, store, job, adapters):
        self.store = store
        self.job = job
        self.app_id = job["app_id"]
        self.identity = job["data"]["publication_id"]
        self.adapters = adapters or {}
        self.pending = None

    def before_call(self):
        _guard(self.store, self.job, self.identity, self.pending, True)

    def heartbeat(self):
        _guard(self.store, self.job, self.identity, self.pending)

    def start(self):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            owner = check_job(db, self.store, self.job)
            self.approved = current(db, self.store, self.app_id, self.identity, owner=owner)
            self.row, self.state = _ensure(db, self.app_id, self.approved)
            if self.row["pending"] or self.row["status"] in ("UNKNOWN", "FAILED"):
                return PreparedPublicationStep(_view(db, self.row), None)
        self.draft = self.approved["draft"]
        self.full = _full(self.store, self.row, self.state)
        self.action = _action(self.state["status"])
        self.adapter = self.adapters.get(self.draft["provider"]) or _adapter(self.draft["provider"])
        return None

    def prepare(self):
        from .publication_credentials import context
        from .publication_artifacts import load

        self.ctx = context(self.store, self.app_id, self.draft, self.before_call, self.heartbeat)
        self.artifact = load(self.store, self.app_id, self.draft) if self.draft["artifact"] else {}
        if self.action == "create" and self.draft["provider"] == "tiktok":
            self.artifact = {**self.artifact, "approved_creator_info": self.approved["preflight"]}

    def checkpoint(self):
        self.pending = uid()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check_job(db, self.store, self.job)
            row, _ = _row(db, self.app_id, self.identity)
            if row["pending"]:
                raise PermissionError("Publication phase is already in progress")
            db.execute(
                "UPDATE publication_intents SET pending=?,pending_action=?,version=version+1,updated=? WHERE id=? AND version=?",
                (self.pending, self.action, now(), self.identity, row["version"]),
            )
            self.row, _ = _row(db, self.app_id, self.identity)
            _event(db, self.row, "PENDING_" + self.action, self.job["attempts"])

    def invoke(self):
        if self.action == "create":
            return self.adapter.create(self.draft, self.artifact, self.ctx)
        if self.action == "upload":
            return self.adapter.upload(self.draft, self.artifact, self.full, self.ctx)
        if self.action == "publish":
            return self.adapter.publish(self.draft, self.full, self.ctx)
        return self.adapter.read(self.draft, self.full, self.ctx)

    def commit_response(self, result):
        _public(result)
        sessions.retain(self.store, self.app_id, self.identity, self.row["request_hash"], self.pending, result)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row, _ = _row(db, self.app_id, self.identity)
            if row["pending"] != self.pending:
                raise PermissionError("Publication checkpoint changed")
            # Save facts after an admitted request even when OFF occurred in flight.
            saved = _save(db, row, result, self.pending, self.action, self.job["attempts"], _attention(result))
            view = _view(db, saved)
        self.retire_previous(row["session_checkpoint"])
        return view

    def retire_previous(self, previous):
        if previous and previous != self.pending:
            try:
                sessions.retire(self.store, self.app_id, self.identity, previous)
            except (Invalid, OSError):
                pass

    def hold(self):
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row, _ = _row(db, self.app_id, self.identity)
            if self.pending and row["pending"] == self.pending:
                row = _hold(db, row, "UNRESOLVED_" + self.action, self.job["attempts"])
            elif not self.pending:
                row = _hold(db, row, "SETUP_OR_READ_FAILED", self.job["attempts"])
            return PreparedPublicationStep(_view(db, row), None)

    def execute(self):
        held = self.start()
        if held is not None:
            return held
        try:
            self.prepare()
            self.checkpoint()
            view = self.commit_response(self.invoke())
        except Exception:
            return self.hold()
        return _continuation(self.store, self.identity, self.action, view)


def _action(status):
    if status == "NEW":
        return "create"
    if status in ("CREATED", "UPLOAD_IN_PROGRESS"):
        return "upload"
    if status in ("UPLOADED", "READY_TO_PUBLISH"):
        return "publish"
    return "read"


def _continuation(store, identity, action, view):
    published = view["status"] == "PUBLISHED"
    interval = 3600 if published else 15 if action == "read" else 0.05
    due = time.time() + interval
    with connection(store.path) as db:
        a = db.execute(
            "SELECT calls_used,max_calls,expires,status FROM publication_authorities WHERE id=?", (identity,)
        ).fetchone()
    can_continue = (
        not view["requires_attention"]
        and a["status"] == "APPROVED"
        and a["calls_used"] < a["max_calls"]
        and due < a["expires"]
    )
    view["monitoring"] = published and can_continue
    return PreparedPublicationStep(view, due if can_continue else None)


def process_job(store, job, adapters=None):
    """Advance exactly one guarded step of the retained worker job."""
    initialize(store)
    identity = job["data"]["publication_id"]
    with paid_lock(store, job["app_id"], identity):
        return _Execution(store, job, adapters).execute()


def list_intents(store, app_id):
    initialize(store)
    # Read permission is checked by the protected owner/agent list service.
    with connection(store.path) as db:
        return [
            _view(db, row)
            for row in db.execute(
                "SELECT * FROM publication_intents WHERE app_id=? ORDER BY updated DESC LIMIT 100", (app_id,)
            )
        ]


def _recovery_load(store, app_id, identity, owner):
    with connection(store.path) as db:
        approved = current(db, store, app_id, identity, recovery=True)
        row, state = _row(db, app_id, identity)
        if row["owner"] != owner:
            raise PermissionError("Publication belongs to another owner")
        running = db.execute(
            "SELECT 1 FROM jobs WHERE app_id=? AND action='social_publication' AND request_key=? AND status='RUNNING' AND lease>?",
            (app_id, "social-publication-" + identity, time.time()),
        ).fetchone()
        if running:
            raise Invalid("The worker still owns this publication; wait for its receipt")
    return approved, row, state


def _recovery_save(store, row, result, checkpoint, action, expected_pending=None):
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        current(db, store, row["app_id"], row["id"], recovery=True)
        saved, _ = _row(db, row["app_id"], row["id"])
        if saved["pending"] != expected_pending:
            raise Invalid("Publication checkpoint changed")
        saved = _save(db, saved, result, checkpoint, action, 0, _attention(result))
        _resume_known(db, store, saved)
        view = _view(db, saved)
    previous = row["session_checkpoint"]
    if previous and previous != checkpoint:
        try:
            sessions.retire(store, row["app_id"], row["id"], previous)
        except (Invalid, OSError):
            pass
    return view


def _adopt_pending(store, row):
    pending = row["pending"]
    if not pending:
        return None
    try:
        full = sessions.load(store, row["app_id"], row["id"], row["request_hash"], pending)
    except Invalid:
        return None
    return _recovery_save(store, row, full, pending, row["pending_action"], pending)


def _recovery_transport(store, app_id, identity, admission, draft):
    calls = 0

    def heartbeat():
        from .operation_authority import check

        with connection(store.path) as db:
            check(db, admission)
            current(db, store, app_id, identity, recovery=True)

    def before_call():
        nonlocal calls
        heartbeat()
        if calls >= 8:
            raise Invalid("Recovery read allowance exhausted")
        from .operation_authority import check

        with connection(store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            check(db, admission)
            current(db, store, app_id, identity, recovery=True, charge=True)
        calls += 1

    from .publication_credentials import context as credentials

    return credentials(store, app_id, draft, before_call, heartbeat)


def _recover_read(store, row, state, approved, admission):
    full = _full(store, row, state)
    if not (full["remote_id"] or full["asset_id"] or full["session"]):
        raise Invalid("No provider identity was retained. Inspect the provider before preparing a new action")
    ctx = _recovery_transport(store, row["app_id"], row["id"], admission, approved["draft"])
    adapter = _adapter(approved["draft"]["provider"])
    result = adapter.read(approved["draft"], full, ctx)
    checkpoint = uid()
    _public(result)
    sessions.retain(store, row["app_id"], row["id"], row["request_hash"], checkpoint, result)
    return _recovery_save(store, row, result, checkpoint, "read", row["pending"])


def reconcile(store, app_id, identity):
    """Fresh owner only: adopt a sealed response or read the retained identity.

    This admits at most eight reads, never create, upload or publish. Confirmed
    phases can resume under still-current approval; uncertain effects cannot.
    """
    admission, actor, owner = _admit(store, app_id, "publication.reconcile", {"id": identity}, True)
    initialize(store)
    with paid_lock(store, app_id, identity):
        approved, row, state = _recovery_load(store, app_id, identity, owner)
        adopted = _adopt_pending(store, row)
        if adopted is not None:
            return adopted
        return _recover_read(store, row, state, approved, admission)


def _resume_known(db, store, row):
    """Owner recovery can continue a confirmed phase, never an uncertain effect."""
    if row["attention"] or row["pending"] or row["status"] in ("UNKNOWN", "FAILED", "NEW"):
        return
    authority = db.execute(
        "SELECT status,expires,calls_used,max_calls FROM publication_authorities WHERE id=?", (row["authority_id"],)
    ).fetchone()
    schedule = db.execute(
        "SELECT * FROM publication_schedules WHERE app_id=? AND authority_id=?", (row["app_id"], row["authority_id"])
    ).fetchone()
    if not _can_resume(authority):
        return
    if not schedule or schedule["status"] != "BLOCKED":
        return
    saved = db.execute("SELECT * FROM jobs WHERE id=?", (schedule["job_id"],)).fetchone()
    if saved and saved["status"] == "BLOCKED":
        db.execute(
            "UPDATE jobs SET status='QUEUED',lease=0,updated=? WHERE id=? AND status='BLOCKED'", (now(), saved["id"])
        )
        db.execute(
            "UPDATE publication_schedules SET status='QUEUED',next_due=?,updated=? WHERE id=? AND status='BLOCKED'",
            (time.time(), now(), schedule["id"]),
        )


def _can_resume(authority):
    return (
        authority is not None
        and authority["status"] == "APPROVED"
        and authority["expires"] > time.time()
        and authority["calls_used"] < authority["max_calls"]
    )
