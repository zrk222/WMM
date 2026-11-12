"""Bind reviewed organic publication drafts to current app-owned source proof."""

import hashlib
import math
import re

from .common import Invalid, digest
from .db import connection
from .publication_contract import validate_draft


def _hashes(db, store, app_id, data):
    """Return the deterministic source and rights fingerprints for saved render inputs."""
    request = data["inputs"]["request"]
    sources = {request["brief_hash"]}
    rights = set()
    bindings = data["inputs"].get("media_bindings", [])
    if bindings:
        from .managed_media_store import derivative_snapshot

        for item in bindings:
            source, _ = derivative_snapshot(db, store, app_id, item["id"], item["sha256"])
            latest = source.get("latest_review")
            if (
                not source.get("reuse_available")
                or not latest
                or latest.get("status") != "ALLOWED"
                or latest.get("version") != item.get("review_version")
                or latest.get("manifest_version") != item.get("manifest_version")
            ):
                raise Invalid("Managed source rights or review changed")
            rights.add(digest(latest))
            sources.add(item["sha256"])
    else:
        rights.add(digest({"kind": "OWNER_ORIGINAL_RENDER", "artifact_sha256": data["artifact"]["sha256"]}))
    return sorted(rights), sorted(sources)


def _app_version(db, app_id):
    row = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
    if row is None:
        raise Invalid("Publication workspace is unavailable")
    return row["version"]


def _text_binding(draft):
    rights = [
        digest(
            {"kind": "OWNER_ORIGINAL_COPY", "title": draft["title"], "caption": draft["caption"], "link": draft["link"]}
        )
    ]
    if draft["source_hashes"]:
        raise Invalid("Original LinkedIn text cannot claim unverified source records")
    if draft["rights_hashes"] != rights:
        raise Invalid("LinkedIn copy rights fingerprint changed")
    return dict(
        artifact_id=None,
        artifact_sha256=None,
        bytes=0,
        content_type="text/plain",
        duration_seconds=None,
        width=None,
        height=None,
        fps=None,
        rights_hashes=rights,
        source_hashes=[],
        rights_basis="OWNER_ORIGINAL_COPY_CONFIRMATION_REQUIRED",
    )


def _resolve(store, app_id, draft, *, verify_bytes):
    from .hypit_jobs import current_inputs, private_path, saved
    from .hypit_media import MAX_BYTES

    artifact = draft["artifact"]
    if not isinstance(artifact, dict) or not re.fullmatch(r"[0-9a-f-]{36}", artifact["id"]):
        raise Invalid("Publication requires an exact retained Hypit artifact")
    store.app(app_id)
    with connection(store.path) as db:
        row = db.execute("SELECT * FROM hypit_renders WHERE app_id=? AND id=?", (app_id, artifact["id"])).fetchone()
        if row is None:
            raise Invalid("Hypit artifact does not belong to this app")
        render = saved(row)
        data = render["data"]
        current_inputs(db, store, app_id, data["inputs"])
        if _app_version(db, app_id) != draft["manifest_version"]:
            raise Invalid("Publication workspace revision changed")
        rights, sources = _hashes(db, store, app_id, data)
    if data.get("renderer") != "HYPIT_LOCAL" or data.get("publication") != "NOT_RUN":
        raise Invalid("Saved video is not an eligible unpublished Hypit render")
    saved_artifact = data.get("artifact")
    metadata = saved_artifact.get("metadata") if isinstance(saved_artifact, dict) else None
    if (
        not isinstance(saved_artifact, dict)
        or saved_artifact.get("sha256") != artifact["sha256"]
        or type(saved_artifact.get("bytes")) is not int
        or not isinstance(metadata, dict)
    ):
        raise Invalid("Saved Hypit artifact metadata is incomplete or changed")
    path = private_path(store, app_id, "artifacts", artifact["id"] + ".mp4")
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise Invalid("Hypit artifact is missing or exceeds its size bound")
    if path.stat().st_size != saved_artifact["bytes"]:
        raise Invalid("Hypit artifact size changed")
    if verify_bytes:
        from .hypit_jobs import artifact_file

        path, checked = artifact_file(store, app_id, artifact["id"])
        if checked != data:
            raise Invalid("Hypit artifact changed during verification")
    if draft["rights_hashes"] != rights or draft["source_hashes"] != sources:
        raise Invalid("Publication source or rights fingerprints changed")
    if draft["provider"] not in ("instagram", "tiktok", "youtube", "linkedin"):
        raise Invalid("Unsupported publication channel")
    if draft["kind"] == "linkedin_text":
        raise Invalid("Video artifact cannot be bound to LinkedIn text")
    return (
        path,
        data,
        dict(
            artifact_id=artifact["id"],
            artifact_sha256=artifact["sha256"],
            bytes=saved_artifact["bytes"],
            content_type="video/mp4",
            duration_seconds=metadata.get("duration_seconds"),
            width=metadata.get("width"),
            height=metadata.get("height"),
            fps=metadata.get("frame_rate"),
            rights_hashes=rights,
            source_hashes=sources,
            rights_basis=(
                "CURRENT_OWNER_SOURCE_ATTESTATIONS"
                if data["inputs"].get("media_bindings")
                else "OWNER_ORIGINAL_RENDER_CONFIRMATION_REQUIRED"
            ),
        ),
    )


def describe(store, app_id, artifact_id):
    """Return safe public metadata and deterministic fingerprints for an app render."""
    from .hypit_jobs import saved

    if not isinstance(artifact_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", artifact_id):
        raise Invalid("Invalid Hypit artifact identifier")
    store.app(app_id)
    with connection(store.path) as db:
        row = db.execute("SELECT * FROM hypit_renders WHERE app_id=? AND id=?", (app_id, artifact_id)).fetchone()
        if row is None:
            raise Invalid("Hypit artifact does not belong to this app")
        data = saved(row)["data"]
        from .creative_rendering import current_request

        current_request(db, store, app_id, data["inputs"]["request"])
        from .hypit_jobs import current_inputs

        current_inputs(db, store, app_id, data["inputs"])
        rights, sources = _hashes(db, store, app_id, data)
    metadata = data.get("artifact", {}).get("metadata")
    if not isinstance(metadata, dict):
        raise Invalid("Saved Hypit artifact metadata is incomplete")
    return dict(
        id=artifact_id,
        sha256=data["artifact"]["sha256"],
        bytes=data["artifact"]["bytes"],
        content_type="video/mp4",
        duration_seconds=metadata.get("duration_seconds"),
        width=metadata.get("width"),
        height=metadata.get("height"),
        fps=metadata.get("frame_rate"),
        rights_hashes=rights,
        source_hashes=sources,
        rights_basis=(
            "CURRENT_OWNER_SOURCE_ATTESTATIONS"
            if data["inputs"].get("media_bindings")
            else "OWNER_ORIGINAL_RENDER_CONFIRMATION_REQUIRED"
        ),
    )


def verify(store, db, app_id, draft, verify_bytes=True):
    """Check exact draft against current app, render and managed-source proof."""
    value = validate_draft(draft)
    if value["app_id"] != app_id:
        raise Invalid("Publication draft belongs to another app")
    if value["kind"] == "linkedin_text":
        if _app_version(db, app_id) != value["manifest_version"]:
            raise Invalid("Publication workspace revision changed")
        return _text_binding(value)
    _, _, snapshot = _resolve(store, app_id, value, verify_bytes=verify_bytes)
    return snapshot


def load(store, app_id, draft):
    """Load one bounded, hash-checked retained video for the internal publisher."""
    value = validate_draft(draft)
    if value["app_id"] != app_id or value["kind"] == "linkedin_text":
        raise Invalid("A video publication draft for this app is required")
    path, data, snapshot = _resolve(store, app_id, value, verify_bytes=False)
    try:
        raw = path.read_bytes()
    except OSError:
        raise Invalid("Hypit artifact could not be read") from None
    actual_hash = hashlib.sha256(raw).hexdigest()
    if len(raw) != snapshot["bytes"] or actual_hash != snapshot["artifact_sha256"]:
        raise Invalid("Hypit artifact changed during publication load")
    from .hypit_media import metadata as inspect_metadata, probe

    decoded = inspect_metadata(
        probe(path.resolve()), data["inputs"]["request"]["shape"], data["inputs"]["request"]["duration_seconds"]
    )
    saved_metadata = data["artifact"]["metadata"]
    if decoded != saved_metadata:
        raise Invalid("Hypit decoded metadata changed")
    try:
        fps = float(decoded["frame_rate"].split("/")[0]) / float(decoded["frame_rate"].split("/")[1])
    except (AttributeError, ValueError, ZeroDivisionError, TypeError):
        raise Invalid("Hypit frame rate metadata is malformed") from None
    if not math.isfinite(fps) or fps <= 0:
        raise Invalid("Hypit frame rate metadata is malformed")
    return dict(
        raw=raw,
        sha256=actual_hash,
        bytes=len(raw),
        duration_seconds=decoded["duration_seconds"],
        width=decoded["width"],
        height=decoded["height"],
        fps=fps,
        content_type="video/mp4",
    )
