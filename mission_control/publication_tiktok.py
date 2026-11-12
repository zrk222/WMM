"""TikTok Direct Post with creator checks and bounded FILE_UPLOAD chunks."""

import re
from datetime import datetime, timezone
from .common import Invalid
from .social_contract import display
from . import publication_transport as http


def _bound(draft, context):
    if (
        draft["provider"] != "tiktok"
        or context.provider != "tiktok"
        or draft["destination_id"] != context.destination_id
    ):
        raise Invalid("TikTok destination changed")


def _data(response):
    value = response.data
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("error"), dict)
        or value["error"].get("code") != "ok"
        or not isinstance(value.get("data"), dict)
    ):
        raise Invalid("TikTok did not confirm the request; inspect the provider result before retrying")
    return value["data"]


def _creator_options(data):
    options = data.get("privacy_level_options")
    maximum = data.get("max_video_post_duration_sec")
    allowed = {"PUBLIC_TO_EVERYONE", "MUTUAL_FOLLOW_FRIENDS", "FOLLOWER_OF_CREATOR", "SELF_ONLY"}
    if not isinstance(options, list) or not options or any(item not in allowed for item in options):
        raise Invalid("TikTok creator settings could not be verified")
    if type(maximum) is not int or maximum <= 0:
        raise Invalid("TikTok creator settings could not be verified")
    if any(type(data.get(field)) is not bool for field in ("comment_disabled", "duet_disabled", "stitch_disabled")):
        raise Invalid("TikTok creator settings could not be verified")


def creator_info(context):
    """Explicit pre-consent read; caller renders choices and obtains consent."""
    if context.provider != "tiktok":
        raise Invalid("TikTok connection required")
    data = _data(http.request(context, "POST", "/v2/post/publish/creator_info/query/", json_body={}))
    _creator_options(data)
    identity = {
        field: display(data.get(field), "TikTok creator name") for field in ("creator_username", "creator_nickname")
    }
    return {
        **identity,
        **{
            key: data[key]
            for key in (
                "privacy_level_options",
                "max_video_post_duration_sec",
                "comment_disabled",
                "duet_disabled",
                "stitch_disabled",
            )
        },
    }


def _artifact(a):
    if (
        not isinstance(a.get("raw"), bytes)
        or not a["raw"]
        or a.get("bytes") != len(a["raw"])
        or a["bytes"] > 4_000_000_000
    ):
        raise Invalid("Video does not meet TikTok media restrictions")
    if (
        a.get("content_type") not in ("video/mp4", "video/quicktime", "video/webm")
        or not isinstance(a.get("duration_seconds"), (int, float))
        or not 0 < a["duration_seconds"] <= 600
    ):
        raise Invalid("Video does not meet TikTok media restrictions")
    _artifact_dimensions(a)


def _artifact_dimensions(a):
    if (
        type(a.get("width")) is not int
        or type(a.get("height")) is not int
        or not 360 <= a["width"] <= 4096
        or not 360 <= a["height"] <= 4096
    ):
        raise Invalid("Video does not meet TikTok media restrictions")
    if not isinstance(a.get("fps"), (int, float)) or not 23 <= a["fps"] <= 60:
        raise Invalid("Video does not meet TikTok media restrictions")


def chunk_plan(size):
    if type(size) is not int or not 0 < size <= 4_000_000_000:
        raise Invalid("Invalid TikTok file size")
    chunk = min(size, 10_000_000)
    count = size // chunk
    if not 1 <= count <= 1000:
        raise Invalid("TikTok chunk count exceeds provider limit")
    return chunk, count


def _state(status, asset_id=None, session=None, observation=None, remote_id=None):
    return dict(status=status, remote_id=remote_id, asset_id=asset_id, session=session, observation=observation or {})


def _review_creator(info, settings, artifact):
    if info != artifact.get("approved_creator_info"):
        raise Invalid("TikTok creator options changed; review a fresh preflight")
    if (
        settings["privacy_level"] not in info["privacy_level_options"]
        or artifact["duration_seconds"] > info["max_video_post_duration_sec"]
    ):
        raise Invalid("TikTok creator eligibility changed; review settings again")
    for field in ("duet", "comment", "stitch"):
        if info[field + "_disabled"] and not settings["disable_" + field]:
            raise Invalid("TikTok creator interaction settings changed; review again")


def create(draft, artifact, context):
    _bound(draft, context)
    _artifact(artifact)
    settings = draft["settings"]
    _review_creator(creator_info(context), settings, artifact)
    caption = draft["caption"] + ("\n\n" + draft["link"] if draft.get("link") else "")
    if len(caption.encode("utf-16-le")) // 2 > 2200:
        raise Invalid("TikTok caption exceeds provider limit")
    size, count = chunk_plan(artifact["bytes"])
    body = {
        "post_info": {"title": caption, **settings},
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": artifact["bytes"],
            "chunk_size": size,
            "total_chunk_count": count,
        },
    }
    data = _data(http.request(context, "POST", "/v2/post/publish/video/init/", json_body=body))
    identity = data.get("publish_id")
    url = data.get("upload_url")
    if (
        not isinstance(identity, str)
        or not re.fullmatch(r"[A-Za-z0-9_.~:-]{1,64}", identity)
        or not isinstance(url, str)
        or not url
    ):
        raise Invalid("TikTok initialization result is incomplete; effect is unknown")
    return _state(
        "CREATED",
        identity,
        {"url": url, "bytes": artifact["bytes"], "chunk_size": size, "count": count, "offset": 0},
        {"phase": "UPLOAD_INITIALIZED"},
    )


def _upload_offsets(s, total):
    offset = s.get("offset")
    chunk = s.get("chunk_size")
    count = s.get("count")
    if type(offset) is not int or type(chunk) is not int or type(count) is not int:
        raise Invalid("TikTok upload requires status reconciliation")
    if (chunk, count) != chunk_plan(total) or not 0 <= offset < total or offset % chunk != 0:
        raise Invalid("TikTok upload requires status reconciliation")
    index = offset // chunk
    if index >= count:
        raise Invalid("TikTok upload offset is invalid")
    return offset, (total if index == count - 1 else offset + chunk)


def _upload_session(state, total):
    s = state.get("session") or {}
    if s.get("bytes") != total or not state.get("asset_id") or not s.get("url"):
        raise Invalid("TikTok upload requires status reconciliation")
    offset, end = _upload_offsets(s, total)
    return s, offset, end


def upload(draft, artifact, state, context):
    _bound(draft, context)
    _artifact(artifact)
    total = artifact["bytes"]
    s, offset, end = _upload_session(state, total)
    result = http.upload(
        context,
        s["url"],
        artifact["raw"][offset:end],
        content_type=artifact["content_type"],
        content_range=f"bytes {offset}-{end - 1}/{total}",
        expected=(201,) if end == total else (206,),
    )
    if result.status not in (201, 206):
        raise Invalid("TikTok upload was not confirmed")
    return _state(
        "UPLOADED" if end == total else "UPLOAD_IN_PROGRESS",
        state["asset_id"],
        {**s, "offset": end},
        {"phase": "UPLOAD_ACCEPTED" if end == total else "UPLOAD_IN_PROGRESS", "uploaded_bytes": end},
    )


def publish(draft, state, context):
    _bound(draft, context)
    if not state.get("asset_id") or state.get("status") not in (
        "UPLOADED",
        "PROCESSING",
        "PUBLISH_ACKNOWLEDGED",
        "PUBLISHED",
    ):
        raise Invalid("TikTok upload is not confirmed")
    # TikTok starts Direct Post after the final upload; do not issue a duplicate init.
    return _state(
        "PROCESSING",
        state["asset_id"],
        state.get("session"),
        {"phase": "AWAITING_PROVIDER_PROCESSING"},
        state.get("remote_id"),
    )


def _video_counts(video):
    counts = {}
    for name, field in (
        ("views", "view_count"),
        ("likes", "like_count"),
        ("comments", "comment_count"),
        ("shares", "share_count"),
    ):
        value = video.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 9007199254740991):
            raise Invalid("TikTok statistic is invalid")
        counts[name] = value
    return counts


def _video_read(identity, remote, state, context):
    if not isinstance(remote, str) or not re.fullmatch(r"[0-9]{1,20}", remote):
        raise Invalid("TikTok video identity is invalid")
    data = _data(
        http.request(
            context,
            "POST",
            "/v2/video/query/",
            query={"fields": "id,view_count,like_count,comment_count,share_count"},
            json_body={"filters": {"video_ids": [remote]}},
        )
    )
    videos = data.get("videos")
    if (
        not isinstance(videos, list)
        or len(videos) != 1
        or not isinstance(videos[0], dict)
        or videos[0].get("id") != remote
    ):
        raise Invalid("TikTok video readback unavailable")
    metrics = {
        "source": "tiktok.video.query",
        "scope": "this_video",
        "unit": "count",
        "counts": _video_counts(videos[0]),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "missing": "NOT_RETURNED",
    }
    return _state(
        "PUBLISHED",
        identity,
        state.get("session"),
        {"phase": "VIDEO_QUERY", "visibility": "PUBLIC_CONFIRMED", "metrics": metrics},
        remote,
    )


def _status_ids(data):
    ids = data.get("publicaly_available_post_id", [])
    if (
        not isinstance(ids, list)
        or len(ids) > 20
        or any(type(x) not in (str, int) or not re.fullmatch(r"[0-9]{1,20}", str(x)) for x in ids)
    ):
        raise Invalid("TikTok post IDs could not be verified")
    return [str(x) for x in ids]


def _status_observation(phase, ids, data, session):
    observation = {
        "phase": phase,
        "visibility": "PUBLIC_CONFIRMED" if ids else "NOT_PUBLICLY_CONFIRMED",
        "public_post_ids": ids,
    }
    observation["metrics"] = {
        "source": "tiktok.publish.status",
        "scope": "this_video",
        "unit": "count",
        "counts": {"views": None, "likes": None, "comments": None, "shares": None},
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "missing": "VIDEO_QUERY_REQUIRES_ONE_PUBLIC_ID" if len(ids) != 1 else "AVAILABLE_ON_NEXT_VIDEO_QUERY",
    }
    if phase == "FAILED":
        reason = data.get("fail_reason")
        observation["failure_reason"] = (
            reason if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,100}", reason) else "unknown"
        )
    if phase == "PROCESSING_UPLOAD" and session:
        observation["uploaded_bytes"] = session["offset"]
    return observation


def _status_read(identity, state, context):
    data = _data(http.request(context, "POST", "/v2/post/publish/status/fetch/", json_body={"publish_id": identity}))
    phase = data.get("status")
    allowed = {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD", "SEND_TO_USER_INBOX", "PUBLISH_COMPLETE", "FAILED"}
    if phase not in allowed:
        raise Invalid("TikTok publication status is unknown")
    ids = _status_ids(data)
    session = state.get("session")
    if phase == "PROCESSING_UPLOAD" and "uploaded_bytes" in data and session:
        offset = data["uploaded_bytes"]
        if type(offset) is not int or not 0 <= offset <= session["bytes"]:
            raise Invalid("TikTok uploaded byte count is invalid")
        session = {**session, "offset": offset}
    mapped = {
        "PROCESSING_UPLOAD": "UPLOAD_IN_PROGRESS",
        "PROCESSING_DOWNLOAD": "PROCESSING",
        "SEND_TO_USER_INBOX": "PROCESSING",
        "PUBLISH_COMPLETE": "PUBLISHED",
        "FAILED": "FAILED",
    }[phase]
    return _state(
        mapped, identity, session, _status_observation(phase, ids, data, session), ids[0] if len(ids) == 1 else None
    )


def read(draft, state, context):
    _bound(draft, context)
    identity = state.get("asset_id")
    if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z0-9_.~:-]{1,64}", identity):
        raise Invalid("TikTok publish ID unavailable; owner reconciliation is required")
    remote = state.get("remote_id")
    if state.get("status") == "PUBLISHED" and remote is not None:
        return _video_read(identity, remote, state, context)
    return _status_read(identity, state, context)
