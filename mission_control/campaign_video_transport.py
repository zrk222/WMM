"""Pinned Page Reels stages. Acknowledgements do not establish publication.

Protocol: Meta's Facebook API collection, Reels Publishing:
https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api
Meta's archived sample collection:
https://github.com/fbsamples/Facebook-Reels-Publishing-API-Postman-Collection
These document the staged protocol; current v26 entitlement and behavior still
require separately authorized live verification.
"""

from dataclasses import dataclass, field
import hashlib
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .campaign_contract import exact, numeric
from .campaign_transport import Unconfirmed
from .common import Invalid
from .hypit_media import MAX_BYTES, validate_video
from .social_auth import app_secret_proof
from .social_contract import opaque
from .social_transport import exchange, SocialError

VERSION = "v26.0"
GRAPH = "https://graph.facebook.com"
UPLOAD = "https://rupload.facebook.com"


@dataclass(frozen=True, repr=False)
class Context:
    """Server-created connection material; never serialize to a job or receipt."""

    page_id: str
    token: str = field(repr=False)
    app_secret: str = field(repr=False)
    alive: object = field(repr=False)


def _context(context):
    if type(context) is not Context or not callable(context.alive):
        raise Invalid("A server-owned Reel transport context is required")
    numeric(context.page_id)
    opaque(context.token, "Page credential")
    opaque(context.app_secret, "app secret")
    return context


def _exchange(host, method, route, body, headers, context):
    """Use existing pinned TLS/framing with no redirect or automatic retry."""
    try:
        value = exchange(urlsplit(host), method, route, body, headers, context.alive, time.monotonic() + 30)
        if value.get("error"):
            raise Unconfirmed("Reel provider response was not confirmed")
        return value
    except (SocialError, OSError, TimeoutError):
        raise Unconfirmed("Reel provider operation was not confirmed") from None


def _headers(context, scheme="Bearer"):
    return {
        "Accept": "application/json",
        "Accept-Encoding": "identity",
        "Cache-Control": "no-store",
        "Authorization": scheme + " " + context.token,
    }


def _form(context, fields):
    body = urlencode(dict(fields, appsecret_proof=app_secret_proof(context.token, context.app_secret))).encode("ascii")
    if len(body) > 32768:
        raise Invalid("Reel metadata exceeds the supported size")
    headers = _headers(context)
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    return body, headers


def create(page, metadata, context) -> object:
    """Create one Page upload session; provider URL is checked, never followed."""
    context = _context(context)
    numeric(page)
    exact(metadata, ())
    if page != context.page_id:
        raise Invalid("Reel Page differs from the protected connection")
    body, headers = _form(context, {"upload_phase": "start"})
    result = _exchange(GRAPH, "POST", "/" + VERSION + "/me/video_reels", body, headers, context)
    try:
        identity = numeric(result.get("video_id"))
    except Invalid:
        raise Unconfirmed("Reel creation identity was not confirmed") from None
    if result.get("upload_url") != UPLOAD + "/video-upload/" + VERSION + "/" + identity:
        raise Unconfirmed("Reel upload destination was not confirmed")
    return {"video_id": identity, "state": "CREATED"}


def _chunks(raw, context, deadline):
    for offset in range(0, len(raw), 65536):
        context.alive()
        if time.monotonic() >= deadline:
            raise TimeoutError("Reel upload deadline expired")
        yield raw[offset : offset + 65536]


def upload(video_id, artifact, context) -> object:
    """Validate and send an immutable bounded local MP4 snapshot, not a URL."""
    context = _context(context)
    numeric(video_id)
    exact(artifact, ("path", "sha256", "bytes", "duration_seconds"))
    if not isinstance(artifact["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
        raise Invalid("Invalid Reel artifact hash")
    if type(artifact["bytes"]) is not int or not 0 < artifact["bytes"] <= MAX_BYTES:
        raise Invalid("Invalid Reel artifact size")
    seconds = artifact["duration_seconds"]
    if type(seconds) is not int or not 4 <= seconds <= 60:
        raise Invalid("Reel duration must be 4 through 60 seconds")
    try:
        path = Path(artifact["path"])
        context.alive()
        if path.is_symlink() or not path.is_file():
            raise Invalid("Reel artifact is unavailable")
        with path.open("rb") as source:
            raw = source.read(MAX_BYTES + 1)
        if len(raw) != artifact["bytes"] or hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
            raise Invalid("Reel artifact bytes changed")
        with tempfile.TemporaryDirectory(prefix="wmm-reel-snapshot-") as directory:
            snapshot = Path(directory) / "video.mp4"
            with snapshot.open("xb") as dest:
                dest.write(raw)
            checked = validate_video(snapshot, "PORTRAIT", seconds)
        if checked["sha256"] != artifact["sha256"] or checked["bytes"] != artifact["bytes"]:
            raise Invalid("Reel decoded snapshot changed")
    except (OSError, TypeError, ValueError):
        raise Invalid("Reel artifact is unavailable") from None
    deadline = time.monotonic() + 30
    headers = _headers(context, "OAuth")
    headers.update(
        {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(raw)),
            "offset": "0",
            "file_size": str(len(raw)),
        }
    )
    result = _exchange(
        UPLOAD, "POST", "/video-upload/" + VERSION + "/" + video_id, _chunks(raw, context, deadline), headers, context
    )
    if result.get("success") is not True:
        raise Unconfirmed("Reel upload was not acknowledged")
    return {"video_id": video_id, "state": "UPLOAD_ACKNOWLEDGED"}


def read(video_id, context) -> object:
    """Expose only documented phase observations, with no inferred publication."""
    context = _context(context)
    numeric(video_id)
    query = urlencode({"fields": "status", "appsecret_proof": app_secret_proof(context.token, context.app_secret)})
    result = _exchange(GRAPH, "GET", "/" + VERSION + "/" + video_id + "?" + query, None, _headers(context), context)
    status = result.get("status")
    if result.get("id") != video_id or not isinstance(status, dict):
        raise Unconfirmed("Exact Reel status was not confirmed")
    phases = {}
    for key in ("uploading_phase", "processing_phase", "publishing_phase"):
        value = status.get(key)
        if value is None:
            phases[key] = None
            continue
        if not isinstance(value, dict) or value.get("status") not in (
            "not_started",
            "in_progress",
            "complete",
            "error",
        ):
            raise Unconfirmed("Reel phase status was not confirmed")
        phases[key] = value["status"]
    overall = status.get("video_status")
    if overall not in ("uploading", "processing", "ready", "error"):
        raise Unconfirmed("Reel status was not confirmed")
    return dict(video_id=video_id, video_status=overall, **phases)


def publish(video_id, metadata, context) -> object:
    """Request finish once; success is an acknowledgement, not readback proof."""
    context = _context(context)
    numeric(video_id)
    exact(metadata, ("caption",))
    caption = metadata["caption"]
    if (
        not isinstance(caption, str)
        or not caption.strip()
        or len(caption) > 5000
        or re.search(r"[\x00-\x08\x0b-\x1f\x7f\ud800-\udfff]", caption)
    ):
        raise Invalid("Use a bounded printable Reel caption")
    body, headers = _form(
        context, dict(upload_phase="finish", video_id=video_id, video_state="PUBLISHED", description=caption)
    )
    result = _exchange(GRAPH, "POST", "/" + VERSION + "/me/video_reels", body, headers, context)
    if result.get("success") is not True:
        raise Unconfirmed("Reel publication request was not acknowledged")
    return {"video_id": video_id, "state": "PUBLISH_ACKNOWLEDGED"}
