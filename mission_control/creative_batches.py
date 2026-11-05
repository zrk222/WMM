"""Finite creative plans and factual inspection of local rendered bytes.

Admission, reservations and execution are deliberately separate from this module's
read-only preparation until the caller can retain and recheck its authority.
"""
import hashlib
import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import Invalid, canonical, digest, iso_time, now, required, uid
from .creative_batch_authority import bound_plan, guard_batch
from .creative_rendering import artifact_file, current_request, render_request
from .db import connection
from .media_native import capability, invoke, validate_video

MAX_VARIANTS = 8
MAX_ACTIVE_FRAMES = 11520
FRAME_RATE = 24
MAX_BATCH_HOURS = 24


def _selection(data):
    """Validate the owner-selected finite resource and execution bounds."""
    if not isinstance(data, dict) or set(data) != {"variants", "max_total_frames", "runtime", "expires"}:
        raise Invalid("Choose exact variants, frame budget, local runtime and expiry")
    if data["runtime"] not in ("DESKTOP", "IOS"):
        raise Invalid("Choose desktop or iOS local rendering")
    observed = datetime.now(timezone.utc)
    expiry = iso_time(data["expires"])
    if not observed < expiry:
        raise Invalid("Choose a future expiry")
    variants = data["variants"]
    limit = data["max_total_frames"]
    if not isinstance(variants, list) or not 1 <= len(variants) <= MAX_VARIANTS:
        raise Invalid("Choose 1 through 8 video variants")
    if type(limit) is not int or not 1 <= limit <= MAX_ACTIVE_FRAMES:
        raise Invalid("Choose a frame budget from 1 through 11520")
    return variants, limit, expiry


def plan_data(db, store, app_id, data) -> dict:
    """Freeze exact current sources and reject duplicate or unbounded variants."""
    variants, budget, ends_at = _selection(data)
    app = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("App does not exist")
    requests = [render_request(db, store, app_id, row) for row in variants]
    hashes = [digest(row) for row in requests]
    if len(hashes) != len(set(hashes)):
        raise Invalid("Each variant must have a different brief or shape")
    frames = sum(row["duration_seconds"] * FRAME_RATE for row in requests)
    if frames > budget:
        raise Invalid("The chosen videos exceed the reviewed frame budget")
    return dict(app_id=app_id, manifest_version=app["version"], variants=requests,
                total_frames=frames, max_total_frames=budget,
                runtime=data["runtime"], expires=ends_at.isoformat(), publication="NOT_RUN")


def prepare(store, app_id, data):
    """Create a reviewable plan without queueing, reserving or publishing."""
    store.app(app_id)
    with connection(store.path) as db:
        plan = plan_data(db, store, app_id, data)
    return dict(plan=plan, plan_json=canonical(plan), plan_hash=digest(plan))


def inspect_output(store, app_id, render_id):
    """Decode four actual frames, separating technical checks from visual review."""
    path, data = artifact_file(store, app_id, render_id)
    request = data["request"]
    actual = validate_video(path, request)
    tools = capability()["tools"]
    if not tools.get("ffmpeg"):
        raise Invalid("FFmpeg is required to inspect rendered frames")
    frame_count = request["duration_seconds"] * FRAME_RATE
    selected = [int(i * frame_count / 4) for i in range(4)]
    expression = "+".join("eq(n\\,%d)" % number for number in selected)
    with tempfile.TemporaryDirectory(prefix="inspect-", dir=path.parent) as temporary:
        folder = Path(temporary)
        invoke([tools["ffmpeg"], "-v", "error", "-nostdin", "-protocol_whitelist", "file,pipe",
                "-i", str(path), "-vf", "select=" + expression, "-fps_mode", "passthrough", "-f", "framemd5", "-"],
               folder, lambda: None, time.monotonic() + 30)
        decoded = [line for line in (folder / "native.log").read_bytes().splitlines() if line and not line.startswith(b"#")]
    if len(decoded) != 4:
        raise Invalid("Output inspection could not decode all four sampled frames")
    if validate_video(path, request)["sha256"] != actual["sha256"]:
        raise Invalid("Video changed during output inspection")
    dimensions = [actual["metadata"]["width"], actual["metadata"]["height"]]
    return dict(artifact_hash=actual["sha256"], decoded_frames=len(decoded),
                dimensions=dimensions, audio="SILENT_VERIFIED",
                captions="UNKNOWN_HUMAN_REVIEW_REQUIRED",
                framing="UNKNOWN_HUMAN_REVIEW_REQUIRED", publication="NOT_RUN")


def public_batch(db, row):
    """Return lineage and local status without disclosing authority references."""
    envelope = bound_plan(row)
    variants = []
    for item in db.execute("SELECT v.*,j.status AS job_status,j.result AS job_result "
        "FROM creative_batch_variants v LEFT JOIN jobs j ON j.id=v.job_id "
        "WHERE v.app_id=? AND v.batch_id=? ORDER BY v.ordinal", (row["app_id"], row["id"])):
        inspection = json.loads(item["inspection"]) if item["inspection"] else None
        if inspection is not None and digest(inspection) != item["inspection_hash"]:
            inspection = dict(status="UNKNOWN", error="Saved inspection changed; review this artifact again")
        state = item["native_state"] if envelope["plan"]["runtime"] == "IOS" else item["job_status"]
        variants.append(dict(ordinal=item["ordinal"], job_id=item["job_id"],
            status=state or "PREPARED", request=json.loads(item["request"]),
            inspection=inspection))
    return dict(id=row["id"], state=row["state"], plan=envelope["plan"],
                plan_hash=row["plan_hash"], reserved_frames=row["reserved_frames"],
                variants=variants, publication="NOT_RUN")


def _reviewed_plan(app_id, body):
    """Parse exact canonical bytes and verify their app-scoped review hash."""
    if not isinstance(body, dict) or set(body) != {"plan", "plan_hash", "request_key"}:
        raise Invalid("Review the exact plan and provide a request key")
    key = required(body["request_key"], "Request key", 120)
    from .operator_client import strict_json
    try:
        plan = strict_json(body["plan"].encode("utf-8"))
    except (AttributeError, UnicodeError, Invalid):
        raise Invalid("The reviewed batch plan is not valid JSON") from None
    if not isinstance(plan, dict) or canonical(plan) != body["plan"]:
        raise Invalid("The reviewed batch plan changed")
    if digest(plan) != body["plan_hash"] or plan.get("app_id") != app_id:
        raise Invalid("The reviewed batch plan changed")
    if plan.get("runtime") == "DESKTOP" and capability()["status"] != "READY":
        raise Invalid(capability()["repair"])
    return key, plan


def _check_plan(db, store, app_id, plan):
    """Reconstruct and revalidate all exact reviewed selections before admission."""
    try:
        selections = [{k: r[k] for k in ("brief_id", "brief_hash", "shape")} for r in plan["variants"]]
        current = plan_data(db, store, app_id, dict(variants=selections,
            max_total_frames=plan["max_total_frames"], runtime=plan["runtime"], expires=plan["expires"]))
    except (KeyError, TypeError):
        raise Invalid("The reviewed batch plan is incomplete") from None
    if current != plan:
        raise Invalid("Batch inputs changed; review a new plan")


def _same_authority(prior, current):
    """Permit a replay only from the original owner or exact originating grant."""
    keys = ("kind", "principal", "role_version") if current["kind"] == "OWNER" else ("kind", "grant_id", "grant_version", "agent_id")
    return all(prior.get(key) == current.get(key) for key in keys)


def _queue_variants(db, store, app_id, identity, plan):
    """Queue all desktop children in this same parent reservation transaction."""
    from .worker import enqueue_db
    for ordinal, request in enumerate(plan["variants"]):
        child_key = "creative-batch-" + identity + "-" + str(ordinal)
        child = enqueue_db(db, store, app_id, "render", request, child_key) if plan["runtime"] == "DESKTOP" else None
        db.execute("INSERT INTO creative_batch_variants(app_id,batch_id,ordinal,request_key,request,request_hash,job_id,inspection,inspection_hash) VALUES(?,?,?,?,?,?,?,?,?)", (app_id, identity,
            ordinal, child_key, canonical(request), digest(request), child["id"] if child else uid(), None, None))


def _same_inspection_candidate(batch, item, original):
    """Reject changed batch state, child job or source between decode and commit."""
    if not batch or batch["state"] != "ACTIVE" or not item:
        return False
    if item["job_id"] != original["job_id"] or item["job_status"] != "SUCCEEDED":
        return False
    if item["job_result"] != original["result"] or item["request_hash"] != original["request_hash"]:
        return False
    return digest(json.loads(item["request"])) == original["request_hash"]


class Batch:
    """Persist a reviewed finite plan and reserve all desktop jobs atomically."""
    def __init__(self, store):
        self.store = store

    def plan(self, app_id, body):
        return prepare(self.store, app_id, body)

    def create(self, app_id, body):
        """Admit one exact plan and atomically reserve all child jobs."""
        from .agent_grants import capture_batch_authority
        self.store.app(app_id)
        key, plan = _reviewed_plan(app_id, body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            _check_plan(db, self.store, app_id, plan)
            authority = capture_batch_authority(db, self.store, app_id, "creative.batch.create",
                                                body["plan_hash"], plan["expires"])
            old = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND request_key=?", (app_id, key)).fetchone()
            if old:
                prior = bound_plan(old)["authority"]
                if old["request_hash"] != digest(body) or not _same_authority(prior, authority):
                    raise Invalid("Request key belongs to another batch")
                guard_batch(db, self.store, old)
                return public_batch(db, old)
            reserved = db.execute("SELECT COALESCE(sum(reserved_frames),0) FROM creative_batches "
                "WHERE app_id=? AND state IN ('ACTIVE','CANCEL_PENDING_HOLD','BLOCKED_HOLD')", (app_id,)).fetchone()[0]
            if reserved + plan["total_frames"] > MAX_ACTIVE_FRAMES:
                raise Invalid("Active or uncertain batches exceed the app frame reservation")
            identity = uid(); stamp = now()
            envelope = dict(plan=plan, authority=authority, binding_hash=digest([body["plan_hash"], authority]))
            db.execute("INSERT INTO creative_batches VALUES(?,?,?,?,?,?,?,?,?,?)", (app_id, identity, key,
                digest(body), canonical(envelope), body["plan_hash"], "ACTIVE", plan["total_frames"], stamp, stamp))
            _queue_variants(db, self.store, app_id, identity, plan)
            return public_batch(db, db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (app_id, identity)).fetchone())

    def list(self, app_id):
        self.store.app(app_id)
        with connection(self.store.path) as db:
            rows = db.execute("SELECT * FROM creative_batches WHERE app_id=? ORDER BY created DESC,id", (app_id,)).fetchall()
            return dict(items=[public_batch(db, row) for row in rows])

    def tick(self):
        """Inspect one completed desktop output per tick; retain uncertain holds."""
        with connection(self.store.path) as db:
            row = db.execute("SELECT b.app_id,b.id,v.ordinal,v.request_hash,j.id AS job_id,j.result FROM creative_batches b "
                "JOIN creative_batch_variants v ON v.app_id=b.app_id AND v.batch_id=b.id "
                "JOIN jobs j ON j.id=v.job_id WHERE b.state='ACTIVE' AND j.status='SUCCEEDED' "
                "AND v.inspection IS NULL ORDER BY b.created,v.ordinal LIMIT 1").fetchone()
        if not row:
            return False
        try:
            render_id = json.loads(row["result"])["render_id"]
            inspection = dict(status="INSPECTED", **inspect_output(self.store, row["app_id"], render_id))
        except (Invalid, OSError, KeyError, TypeError, ValueError):
            inspection = dict(status="UNKNOWN", error="Could not inspect saved video; human review is required", publication="NOT_RUN")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            batch = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (row["app_id"], row["id"])).fetchone()
            item = db.execute("SELECT v.*,j.status AS job_status,j.result AS job_result FROM creative_batch_variants v "
                "JOIN jobs j ON j.id=v.job_id WHERE v.app_id=? AND v.batch_id=? AND v.ordinal=?",
                (row["app_id"], row["id"], row["ordinal"])).fetchone()
            if not _same_inspection_candidate(batch, item, row):
                return False
            guard_batch(db, self.store, batch)
            current_request(db, self.store, row["app_id"], json.loads(item["request"]))
            if inspection["status"] == "INSPECTED":
                path, _ = artifact_file(self.store, row["app_id"], render_id)
                if hashlib.sha256(path.read_bytes()).hexdigest() != inspection["artifact_hash"]:
                    raise Invalid("Video changed before output inspection was saved")
            changed = db.execute("UPDATE creative_batch_variants SET inspection=?,inspection_hash=? "
                "WHERE app_id=? AND batch_id=? AND ordinal=? AND inspection IS NULL AND EXISTS "
                "(SELECT 1 FROM creative_batches WHERE app_id=? AND id=? AND state='ACTIVE')",
                (canonical(inspection), digest(inspection), row["app_id"], row["id"], row["ordinal"], row["app_id"], row["id"])).rowcount
            if changed:
                remaining = db.execute("SELECT count(*) FROM creative_batch_variants v LEFT JOIN jobs j ON j.id=v.job_id "
                    "WHERE v.app_id=? AND v.batch_id=? AND (j.status!='SUCCEEDED' OR v.inspection IS NULL)",
                    (row["app_id"], row["id"])).fetchone()[0]
                if not remaining:
                    db.execute("UPDATE creative_batches SET state='COMPLETED',updated=? WHERE app_id=? AND id=? AND state='ACTIVE'",
                        (now(), row["app_id"], row["id"]))
        return bool(changed)

    def cancel(self, app_id, batch_id):
        from .operation_authority import PROTECTED, check, store_identity
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            context = PROTECTED.get()
            if (not context or context.get("store") != store_identity(self.store)
                    or json.loads(context["envelope"]) != dict(app_id=app_id, operation="creative.batch.cancel", input={"batch_id": batch_id})):
                raise PermissionError("Exact protected batch cancellation is required")
            check(db, context)
            row = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (app_id, batch_id)).fetchone()
            if not row or row["state"] not in ("ACTIVE", "BLOCKED_HOLD"):
                raise Invalid("This batch cannot be cancelled")
            running = db.execute("SELECT count(*) FROM jobs j JOIN creative_batch_variants v ON v.job_id=j.id "
                "WHERE v.app_id=? AND v.batch_id=? AND j.status='RUNNING'", (app_id, batch_id)).fetchone()[0]
            runtime = bound_plan(row)["plan"]["runtime"]
            if runtime == "IOS":
                running = db.execute("SELECT count(*) FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND native_state='RUNNING'", (app_id, batch_id)).fetchone()[0]
                db.execute("UPDATE creative_batch_variants SET native_state='CANCELLED' WHERE app_id=? AND batch_id=? AND native_state='PREPARED'", (app_id, batch_id))
                db.execute("UPDATE creative_batch_variants SET native_state='STOP_PENDING' WHERE app_id=? AND batch_id=? AND native_state='RUNNING'", (app_id, batch_id))
            else:
                db.execute("UPDATE creative_batch_variants SET native_state='STOP_PENDING' WHERE app_id=? AND batch_id=? AND job_id IN (SELECT id FROM jobs WHERE status='RUNNING')", (app_id, batch_id))
                db.execute("UPDATE creative_batch_variants SET native_state='CANCELLED' WHERE app_id=? AND batch_id=? AND job_id IN (SELECT id FROM jobs WHERE status='QUEUED')", (app_id, batch_id))
                running = db.execute("SELECT count(*) FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND native_state='STOP_PENDING'", (app_id, batch_id)).fetchone()[0]
            db.execute("UPDATE jobs SET status='CANCELLED',updated=? WHERE app_id=? AND status IN ('QUEUED','RUNNING') "
                "AND id IN (SELECT job_id FROM creative_batch_variants WHERE app_id=? AND batch_id=?)",
                (now(), app_id, app_id, batch_id))
            state = "CANCEL_PENDING_HOLD" if running else "CANCELLED"
            db.execute("UPDATE creative_batches SET state=?,updated=? WHERE app_id=? AND id=?", (state, now(), app_id, batch_id))
            return public_batch(db, db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (app_id, batch_id)).fetchone())


def ack_desktop_stop(store, job):
    """Release a cancelled attempt's hold only after its worker has stopped."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT v.* FROM creative_batch_variants v JOIN jobs j ON j.id=v.job_id "
            "WHERE v.app_id=? AND v.job_id=? AND v.native_state='STOP_PENDING' "
            "AND j.status IN ('CANCELLED','BLOCKED') AND j.attempts=?", (job["app_id"], job["id"], job["attempts"])).fetchone()
        if not row:
            return False
        db.execute("UPDATE creative_batch_variants SET native_state='STOPPED' WHERE app_id=? AND batch_id=? AND ordinal=?",
                   (row["app_id"], row["batch_id"], row["ordinal"]))
        pending = db.execute("SELECT count(*) FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND native_state='STOP_PENDING'",
                             (row["app_id"], row["batch_id"])).fetchone()[0]
        if not pending:
            db.execute("UPDATE creative_batches SET state='CANCELLED',updated=? WHERE app_id=? AND id=? AND state='CANCEL_PENDING_HOLD'",
                       (now(), row["app_id"], row["batch_id"]))
        return True
