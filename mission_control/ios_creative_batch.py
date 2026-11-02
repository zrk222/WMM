"""Exact on-device creative packet and app-owned still source resolution."""
import hashlib
import json
import re
from pathlib import Path
from uuid import UUID

from .common import Invalid, canonical, digest, now
from .creative_rendering import current_request
from .db import connection
from .media_native import MAX_BYTES as MAX_VIDEO_BYTES

MAX_IMAGE_BYTES = 8388608  # Existing HTTP upload bound, not a new source quota.
FRAME_RATE = 24


def native_packet(db, store, app_id, variant) -> dict:
    """Project the validated brief into four exact caption-and-still intervals."""
    current_request(db, store, app_id, variant)
    screens = variant["brief"]["data"]["content"]["screens"]
    if not screens or len(variant["captions"]) != 4:
        raise Invalid("The native batch needs its four approved scenes and actual stills")
    frames = variant["duration_seconds"] * FRAME_RATE
    scenes = []
    for index, caption in enumerate(variant["captions"]):
        screen = screens[index % len(screens)]
        start = frames * index // 4
        end = frames * (index + 1) // 4
        scenes.append(dict(start_frame=start, frame_count=end-start, caption=caption,
                           source_id=screen["file_id"], source_hash=screen["sha256"]))
    packet = dict(schema="growth.ios-creative-batch-packet.v1", app_id=app_id,
                  request=variant, shape=variant["shape"], fps=FRAME_RATE,
                  title=variant["brief"]["data"]["app"]["name"],
                  frame_count=frames, scenes=scenes, audio="SILENT", publication="NOT_RUN")
    return dict(packet, packet_hash=digest(packet))


def _still_identifier(source_id):
    """Accept only a canonical UUID filename in the existing image formats."""
    try:
        stem, suffix = source_id.rsplit(".", 1)
        if str(UUID(stem)) != stem or suffix not in ("png", "jpg", "jpeg"):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise Invalid("Invalid native still identifier") from None


def _still_file(store, app_id, source_id, sha256):
    """Check the exact app-local still filename, size and bytes."""
    folder = (store.path.parent / "files" / app_id).resolve()
    path = folder / source_id
    if path.is_symlink() or not path.is_file() or path.resolve().parent != folder:
        raise Invalid("The current app still is unavailable")
    if not 0 < path.stat().st_size <= MAX_IMAGE_BYTES:
        raise Invalid("The still exceeds the existing upload bound")
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise Invalid("The app still changed before native rendering")
    return Path(path)


def native_source(db, store, app_id, packet, source_id, sha256):
    """Return only a current packet-bound, app-local UUID still with intact bytes."""
    if not isinstance(packet, dict) or packet.get("app_id") != app_id:
        raise Invalid("Native batch packet belongs to another app")
    try:
        expected = native_packet(db, store, app_id, packet["request"])
    except (KeyError, TypeError):
        raise Invalid("Invalid native packet") from None
    _still_identifier(source_id)
    if packet != expected or not any(s["source_id"] == source_id and s["source_hash"] == sha256 for s in packet["scenes"]):
        raise Invalid("Still is not bound to the current native packet")
    return _still_file(store, app_id, source_id, sha256)


def _native_owner(db, store, batch):
    """Require a fresh native session belonging to the batch's original owner."""
    from .creative_batch_authority import bound_plan
    from .ios_host import NativeIdentities
    from .operation_authority import PROTECTED, check, store_identity
    context = PROTECTED.get()
    if (not context or context.get("store") != store_identity(store)
            or not isinstance(context.get("identities"), NativeIdentities)
            or not context.get("principal") or json.loads(context["envelope"])["app_id"] != batch["app_id"]):
        raise PermissionError("A fresh native owner session is required")
    current = check(db, context)
    envelope = bound_plan(batch)
    authority = envelope["authority"]
    if authority["kind"] == "OWNER":
        owner = authority["principal"]
    else:
        grant = db.execute("SELECT owner FROM agent_grants WHERE id=?", (authority["grant_id"],)).fetchone()
        owner = grant["owner"] if grant else None
    if current != owner:
        raise PermissionError("Native batch belongs to another owner")
    return envelope


def _native_context(db, store, app_id, batch):
    """Require a freshly verified native owner as well as retained batch scope."""
    from .creative_batch_authority import guard_batch
    _native_owner(db, store, batch)
    return guard_batch(db, store, batch)


def _variant(db, store, app_id, batch_id, ordinal):
    if type(ordinal) is not int or ordinal < 0:
        raise Invalid("Choose an exact batch variant")
    batch = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (app_id, batch_id)).fetchone()
    row = db.execute("SELECT * FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND ordinal=?",
                     (app_id, batch_id, ordinal)).fetchone()
    if not batch or not row or batch["state"] != "ACTIVE":
        raise Invalid("Native batch is unavailable or cancelled")
    envelope = _native_context(db, store, app_id, batch)
    if envelope["plan"]["runtime"] != "IOS":
        raise Invalid("This batch uses a different renderer")
    request = json.loads(row["request"])
    if digest(request) != row["request_hash"] or request != envelope["plan"]["variants"][ordinal]:
        raise Invalid("The saved native variant changed")
    packet = native_packet(db, store, app_id, request)
    return batch, row, packet


def native_start(store, app_id, batch_id, ordinal):
    """Claim a native variant once; interrupted claims need reconciliation."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        _, row, packet = _variant(db, store, app_id, batch_id, ordinal)
        if row["native_state"] == "SUCCEEDED":
            return dict(job_id=row["job_id"], status="SUCCEEDED", packet=packet)
        if row["native_state"] != "PREPARED":
            return dict(job_id=row["job_id"], status="RECONCILE_REQUIRED", packet=packet)
        db.execute("UPDATE creative_batch_variants SET native_state='RUNNING',native_packet_hash=? "
            "WHERE app_id=? AND batch_id=? AND ordinal=?", (packet["packet_hash"], app_id, batch_id, ordinal))
        return dict(job_id=row["job_id"], status="RUNNING", packet=packet)


def native_validate(store, app_id, batch_id, ordinal, packet_hash):
    with connection(store.path) as db:
        _, row, packet = _variant(db, store, app_id, batch_id, ordinal)
        if row["native_state"] != "RUNNING" or row["native_packet_hash"] != packet_hash or packet["packet_hash"] != packet_hash:
            raise Invalid("Native render was cancelled or its packet changed")
        return dict(job_id=row["job_id"], status="RUNNING")


def native_source_for_job(store, app_id, batch_id, ordinal, packet_hash, source_id, sha256):
    """Resolve a still only for the still-running exact native packet."""
    with connection(store.path) as db:
        _, row, packet = _variant(db, store, app_id, batch_id, ordinal)
        if row["native_state"] != "RUNNING" or row["native_packet_hash"] != packet_hash or packet["packet_hash"] != packet_hash:
            raise Invalid("Native render was cancelled or its packet changed")
        return native_source(db, store, app_id, packet, source_id, sha256)


def _inspection_shape(row, packet, inspection):
    """Validate typed decoder facts against the exact requested native packet."""
    fields = {"artifact_id", "sha256", "bytes", "frames", "width", "height", "audio"}
    if not isinstance(inspection, dict) or set(inspection) != fields:
        raise Invalid("Native decoded output inspection is required")
    size = (720, 1280) if packet["shape"] == "PORTRAIT" else (1280, 720)
    if inspection["artifact_id"] != row["job_id"] or type(inspection["bytes"]) is not int:
        raise Invalid("Native output identity or size is invalid")
    if not 0 < inspection["bytes"] <= MAX_VIDEO_BYTES or inspection["frames"] != packet["frame_count"]:
        raise Invalid("Native output size or frame count does not match")
    if (inspection["width"], inspection["height"]) != size or inspection["audio"] is not False:
        raise Invalid("Native output dimensions or audio do not match")
    if not isinstance(inspection["sha256"], str) or not re.fullmatch("[a-f0-9]{64}", inspection["sha256"]):
        raise Invalid("Native output hash is invalid")
    return size


def _output_file(store, job_id, expected_hash, expected_bytes=None):
    """Read only the expected regular app-container artifact with current bytes."""
    folder = (store.path.parent / "native-batch-exports").resolve()
    path = folder / (job_id + ".mp4")
    if path.is_symlink() or not path.is_file() or path.resolve().parent != folder:
        raise Invalid("Native output bytes are missing or changed")
    size = path.stat().st_size
    if not 0 < size <= MAX_VIDEO_BYTES or (expected_bytes is not None and size != expected_bytes):
        raise Invalid("Native output size is missing or changed")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise Invalid("Native output bytes are missing or changed")
    return path


def native_finish(store, app_id, batch_id, ordinal, packet_hash, inspection):
    """Commit only trusted host inspection matching the saved app-local bytes."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        _, row, packet = _variant(db, store, app_id, batch_id, ordinal)
        if row["native_state"] != "RUNNING" or row["native_packet_hash"] != packet_hash or packet["packet_hash"] != packet_hash:
            raise Invalid("Native render was cancelled or its packet changed")
        size = _inspection_shape(row, packet, inspection)
        _output_file(store, row["job_id"], inspection["sha256"], inspection["bytes"])
        result = dict(status="INSPECTED", artifact_hash=inspection["sha256"], decoded_frames=inspection["frames"],
                      dimensions=list(size), audio="SILENT_VERIFIED", captions="UNKNOWN_HUMAN_REVIEW_REQUIRED",
                      framing="UNKNOWN_HUMAN_REVIEW_REQUIRED", publication="NOT_RUN")
        db.execute("UPDATE creative_batch_variants SET native_state='SUCCEEDED',inspection=?,inspection_hash=? "
                   "WHERE app_id=? AND batch_id=? AND ordinal=?", (canonical(result), digest(result), app_id, batch_id, ordinal))
        remaining = db.execute("SELECT count(*) FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND native_state!='SUCCEEDED'",
                               (app_id, batch_id)).fetchone()[0]
        if not remaining:
            db.execute("UPDATE creative_batches SET state='COMPLETED',updated=? WHERE app_id=? AND id=?", (now(), app_id, batch_id))
        return dict(job_id=row["job_id"], status="SUCCEEDED", inspection=result)


def native_ack_stopped(store, app_id, batch_id, ordinal, packet_hash):
    """Host-only acknowledgement after the native writer is confirmed stopped."""
    with connection(store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        batch = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (app_id, batch_id)).fetchone()
        row = db.execute("SELECT * FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND ordinal=?",
                         (app_id, batch_id, ordinal)).fetchone()
        if not batch or not row or batch["state"] != "CANCEL_PENDING_HOLD":
            raise Invalid("No cancelled native attempt awaits a stop acknowledgement")
        _native_owner(db, store, batch)
        if row["native_state"] != "STOP_PENDING" or row["native_packet_hash"] != packet_hash:
            raise Invalid("The stopped native attempt no longer matches")
        db.execute("UPDATE creative_batch_variants SET native_state='STOPPED' WHERE app_id=? AND batch_id=? AND ordinal=?",
                   (app_id, batch_id, ordinal))
        pending = db.execute("SELECT count(*) FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND native_state='STOP_PENDING'",
                             (app_id, batch_id)).fetchone()[0]
        if not pending:
            db.execute("UPDATE creative_batches SET state='CANCELLED',updated=? WHERE app_id=? AND id=? AND state='CANCEL_PENDING_HOLD'",
                       (now(), app_id, batch_id))
        return dict(job_id=row["job_id"], status="STOPPED")


def _artifact_binding(db, store, app_id, batch, row, ordinal):
    """Validate saved review evidence and its still-current source packet."""
    envelope = _native_owner(db, store, batch)
    request = json.loads(row["request"]); inspection = json.loads(row["inspection"])
    if envelope["plan"]["runtime"] != "IOS" or type(ordinal) is not int or ordinal < 0:
        raise Invalid("Invalid native video scope")
    if ordinal >= len(envelope["plan"]["variants"]) or request != envelope["plan"]["variants"][ordinal]:
        raise Invalid("The native video source binding changed")
    if digest(request) != row["request_hash"] or digest(inspection) != row["inspection_hash"]:
        raise Invalid("The native video or its review evidence changed")
    packet = native_packet(db, store, app_id, request)
    if packet["packet_hash"] != row["native_packet_hash"] or inspection.get("decoded_frames") != packet["frame_count"]:
        raise Invalid("The native video no longer matches its packet")
    return packet, inspection


def native_artifact(store, app_id, batch_id, ordinal):
    """Reopen only current, hash-bound output for a fresh native owner review."""
    with connection(store.path) as db:
        batch = db.execute("SELECT * FROM creative_batches WHERE app_id=? AND id=?", (app_id, batch_id)).fetchone()
        row = db.execute("SELECT * FROM creative_batch_variants WHERE app_id=? AND batch_id=? AND ordinal=?",
                         (app_id, batch_id, ordinal)).fetchone()
        if not batch or not row or row["native_state"] != "SUCCEEDED" or not row["inspection"]:
            raise Invalid("No completed native video is available for review")
        packet, inspection = _artifact_binding(db, store, app_id, batch, row, ordinal)
        path = _output_file(store, row["job_id"], inspection.get("artifact_hash"))
        return dict(path=str(path), sha256=inspection["artifact_hash"], frames=packet["frame_count"])
