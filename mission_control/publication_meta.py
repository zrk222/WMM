"""Instagram Reels through an owner-authorized Facebook Login Page grant.

https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/content-publishing/
https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
"""

import hashlib, re
from datetime import datetime, timezone
from .common import Invalid
from .social_registry import META_VERSION
from . import publication_transport as http


def _check(draft, context):
    if (
        draft["provider"] != "instagram"
        or draft["kind"] != "instagram_reel"
        or context.provider != "instagram"
        or context.login_family != "facebook"
        or draft["destination_id"] != context.destination_id
    ):
        raise Invalid("Instagram requires the verified Facebook Page linked destination")
    if draft.get("link") is not None:
        raise Invalid("Instagram Reel link must be included in the approved caption")
    return _id(draft["destination_id"])


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,32}", value):
        raise Invalid("Invalid Instagram identity")
    return value


def _artifact(draft, artifact):
    if (
        not isinstance(artifact, dict)
        or not isinstance(artifact.get("raw"), bytes)
        or len(artifact["raw"]) != artifact.get("bytes")
        or hashlib.sha256(artifact["raw"]).hexdigest() != artifact.get("sha256")
        or artifact["sha256"] != draft["artifact"]["sha256"]
    ):
        raise Invalid("Invalid approved Instagram artifact")


def _state(status, remote_id=None, asset_id=None, session=None, observation=None):
    return dict(status=status, remote_id=remote_id, asset_id=asset_id, session=session, observation=observation or {})


def create(draft, artifact, context):
    identity = _check(draft, context)
    _artifact(draft, artifact)
    response = http.request(
        context,
        "POST",
        "/" + META_VERSION + "/" + identity + "/media",
        form={
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": draft["caption"],
            "share_to_feed": str(draft["settings"]["share_to_feed"]).lower(),
        },
    )
    asset = _id(response.data.get("id"))
    uri = response.data.get("uri")
    expected = "https://rupload.facebook.com/ig-api-upload/" + META_VERSION + "/" + asset
    if uri != expected:
        raise Invalid("Instagram upload session did not match container")
    return _state("CREATED", asset_id=asset, session={"upload_url": uri}, observation={"container": "CREATED"})


def upload(draft, artifact, state, context):
    _check(draft, context)
    _artifact(draft, artifact)
    asset = _id(state.get("asset_id"))
    if (
        state.get("status") != "CREATED"
        or state.get("session", {}).get("upload_url")
        != "https://rupload.facebook.com/ig-api-upload/" + META_VERSION + "/" + asset
    ):
        raise Invalid("Instagram upload state does not permit an effect")
    response = http.upload(
        context,
        state["session"]["upload_url"],
        artifact["raw"],
        content_type="application/octet-stream",
        method="POST",
        bearer=True,
        auth_scheme="OAuth",
        headers={"offset": "0", "file_size": str(artifact["bytes"])},
    )
    if response.data.get("success") is not True:
        raise Invalid("Instagram upload acknowledgement incomplete")
    return _state("PROCESSING", asset_id=asset, observation={"upload": "ACKNOWLEDGED"})


def publish(draft, state, context):
    identity = _check(draft, context)
    asset = _id(state.get("asset_id"))
    if state.get("status") != "READY_TO_PUBLISH":
        raise Invalid("Instagram container is not ready")
    response = http.request(
        context, "POST", "/" + META_VERSION + "/" + identity + "/media_publish", form={"creation_id": asset}
    )
    remote = _id(response.data.get("id"))
    issues = response.data.get("config_issue")
    return _state(
        "PUBLISH_ACKNOWLEDGED",
        remote_id=remote,
        asset_id=asset,
        observation={
            "publication": "ACKNOWLEDGED",
            "config_issue": issues if isinstance(issues, str) and re.fullmatch(r"[A-Z_]{1,80}", issues) else None,
            "public_visibility": "NOT_VERIFIED",
        },
    )


def read(draft, state, context):
    _check(draft, context)
    asset = _id(state.get("asset_id"))
    if state.get("status") in ("PROCESSING", "CREATED"):
        response = http.request(
            context, "GET", "/" + META_VERSION + "/" + asset, query={"fields": "status_code,status"}
        )
        if str(response.data.get("id")) != asset:
            raise Invalid("Instagram container identity changed")
        status = response.data.get("status_code")
        if status not in ("IN_PROGRESS", "FINISHED", "ERROR", "EXPIRED", "PUBLISHED"):
            raise Invalid("Unknown Instagram container status")
        mapped = {
            "IN_PROGRESS": "PROCESSING",
            "FINISHED": "READY_TO_PUBLISH",
            "ERROR": "FAILED",
            "EXPIRED": "FAILED",
            "PUBLISHED": "UNKNOWN",
        }[status]
        return _state(mapped, asset_id=asset, observation={"container_status": status})
    remote = _id(state.get("remote_id"))
    response = http.request(
        context,
        "GET",
        "/" + META_VERSION + "/" + remote,
        query={"fields": "id,media_type,permalink,like_count,comments_count"},
    )
    if str(response.data.get("id")) != remote:
        raise Invalid("Instagram media identity changed")
    media_type = response.data.get("media_type")
    if media_type not in ("VIDEO", "IMAGE", "CAROUSEL_ALBUM"):
        raise Invalid("Instagram media type could not be verified")
    counts = {"views": None}
    for name, field in (("likes", "like_count"), ("comments", "comments_count")):
        value = response.data.get(field)
        if value is not None and (type(value) is not int or not 0 <= value <= 9007199254740991):
            raise Invalid("Instagram statistic is invalid")
        counts[name] = value
    metrics = {
        "source": "instagram.media",
        "scope": "this_media",
        "unit": "count",
        "counts": counts,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "missing": "NOT_RETURNED",
        "views_reason": "INSIGHTS_NOT_REQUESTED",
    }
    return _state(
        "PUBLISHED",
        remote_id=remote,
        asset_id=asset,
        observation={"media_type": media_type, "public_visibility": "NOT_VERIFIED", "metrics": metrics},
    )
