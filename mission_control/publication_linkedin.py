"""LinkedIn organic adapter; no retry of uncertain effects.

https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/videos-api
https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api
"""

import hashlib
import re
from urllib.parse import quote

from . import publication_transport as http
from .common import Invalid

_HEADERS = {"Linkedin-Version": "202609", "X-Restli-Protocol-Version": "2.0.0"}


def _owner(draft, context):
    if (
        draft["provider"] != "linkedin"
        or context.provider != "linkedin"
        or draft["destination_id"] != context.destination_id
    ):
        raise Invalid("Publication destination changed")
    identity = draft["destination_id"]
    if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identity):
        return "urn:li:person:" + identity
    if re.fullmatch(r"urn:li:(?:person|organization):[A-Za-z0-9_-]{1,100}", identity):
        return identity
    raise Invalid("Invalid LinkedIn destination")


def _urn(value, kind):
    if not isinstance(value, str) or not re.fullmatch(r"urn:li:" + kind + r":[A-Za-z0-9_-]{1,150}", value):
        raise Invalid("Invalid LinkedIn provider identity")
    return value


def _state(status, remote_id=None, asset_id=None, session=None, observation=None):
    return dict(status=status, remote_id=remote_id, asset_id=asset_id, session=session, observation=observation or {})


def _artifact(draft, artifact):
    if not isinstance(artifact, dict) or not isinstance(artifact.get("raw"), bytes):
        raise Invalid("Invalid approved LinkedIn artifact")
    if (
        len(artifact["raw"]) != artifact.get("bytes")
        or hashlib.sha256(artifact["raw"]).hexdigest() != artifact.get("sha256")
        or artifact.get("sha256") != draft["artifact"]["sha256"]
    ):
        raise Invalid("Invalid approved LinkedIn artifact")


def _range(part, position, total):
    if not isinstance(part, dict) or not isinstance(part.get("uploadUrl"), str):
        raise Invalid("LinkedIn upload ranges invalid")
    if type(part.get("firstByte")) is not int or type(part.get("lastByte")) is not int:
        raise Invalid("LinkedIn upload ranges invalid")
    if part["firstByte"] != position or part["lastByte"] < position or part["lastByte"] >= total:
        raise Invalid("LinkedIn upload ranges invalid")
    return part["lastByte"] + 1


def _instructions(value, total):
    instructions = value.get("uploadInstructions")
    token = value.get("uploadToken")
    if not isinstance(instructions, list) or not instructions or not isinstance(token, str):
        raise Invalid("LinkedIn upload session unavailable")
    position = 0
    for part in instructions:
        position = _range(part, position, total)
    if position != total:
        raise Invalid("LinkedIn upload ranges incomplete")
    return instructions, token


def create(draft, artifact, context):
    owner = _owner(draft, context)
    if draft["kind"] == "linkedin_text":
        return _state("READY_TO_PUBLISH")
    if draft["kind"] != "linkedin_video":
        raise Invalid("Invalid approved LinkedIn artifact")
    _artifact(draft, artifact)
    result = http.request(
        context,
        "POST",
        "/rest/videos",
        query={"action": "initializeUpload"},
        headers=_HEADERS,
        json_body={
            "initializeUploadRequest": {
                "owner": owner,
                "fileSizeBytes": artifact["bytes"],
                "uploadCaptions": False,
                "uploadThumbnail": False,
            }
        },
    )
    value = result.data.get("value", {})
    asset = _urn(value.get("video"), "video")
    instructions, token = _instructions(value, artifact["bytes"])
    return _state(
        "CREATED",
        asset_id=asset,
        session={"instructions": instructions, "upload_token": token, "parts": []},
        observation={"asset": "INITIALIZED"},
    )


def _part(context, artifact, asset, session, parts, instructions):
    part = instructions[len(parts)]
    a = part["firstByte"]
    b = part["lastByte"]
    result = http.upload(
        context, part["uploadUrl"], artifact["raw"][a : b + 1], content_type="application/octet-stream", expected=(200,)
    )
    etag = result.headers.get("etag")
    if not isinstance(etag, str) or not etag or len(etag) > 4096 or any(ord(c) < 32 for c in etag):
        raise Invalid("LinkedIn upload acknowledgement incomplete")
    etag = etag.strip('"')
    if not etag:
        raise Invalid("LinkedIn upload acknowledgement incomplete")
    parts.append(etag)
    return _state(
        "UPLOAD_IN_PROGRESS",
        asset_id=asset,
        session={**session, "parts": parts},
        observation={"uploaded_parts": len(parts)},
    )


def upload(draft, artifact, state, context):
    _owner(draft, context)
    asset = _urn(state.get("asset_id"), "video")
    session = state.get("session")
    if (
        not isinstance(session, dict)
        or not isinstance(session.get("instructions"), list)
        or not isinstance(session.get("parts"), list)
    ):
        raise Invalid("LinkedIn upload session unavailable")
    _artifact(draft, artifact)
    parts = list(session["parts"])
    instructions = session["instructions"]
    if state["status"] not in ("CREATED", "UPLOAD_IN_PROGRESS"):
        raise Invalid("LinkedIn upload state does not permit an effect")
    if len(parts) < len(instructions):
        return _part(context, artifact, asset, session, parts, instructions)
    if len(parts) != len(instructions):
        raise Invalid("LinkedIn upload state does not permit an effect")
    http.request(
        context,
        "POST",
        "/rest/videos",
        query={"action": "finalizeUpload"},
        headers=_HEADERS,
        json_body={
            "finalizeUploadRequest": {"video": asset, "uploadToken": session["upload_token"], "uploadedPartIds": parts}
        },
        expected=(200,),
        response_json=False,
    )
    return _state("PROCESSING", asset_id=asset, observation={"asset": "FINALIZE_ACKNOWLEDGED"})


def publish(draft, state, context):
    owner = _owner(draft, context)
    if state.get("remote_id") is not None or state.get("status") != "READY_TO_PUBLISH":
        raise Invalid("LinkedIn content is not ready")
    caption = draft["caption"] + ("\n" + draft["link"] if draft.get("link") else "")
    body = {
        "author": owner,
        "commentary": caption,
        "visibility": draft["settings"]["visibility"],
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if draft["kind"] == "linkedin_video":
        body["content"] = {"media": {"id": _urn(state.get("asset_id"), "video"), "title": draft["title"]}}
    elif draft["kind"] != "linkedin_text":
        raise Invalid("Invalid LinkedIn publication kind")
    response = http.request(
        context, "POST", "/rest/posts", json_body=body, headers=_HEADERS, expected=(201,), response_json=False
    )
    remote = _urn(response.headers.get("x-restli-id"), "(?:ugcPost|share)")
    return _state(
        "PUBLISH_ACKNOWLEDGED",
        remote_id=remote,
        asset_id=state.get("asset_id"),
        observation={"publication": "ACKNOWLEDGED", "public_visibility": "NOT_VERIFIED"},
    )


def read(draft, state, context):
    owner = _owner(draft, context)
    if state.get("remote_id") is None and state.get("status") == "PROCESSING":
        asset = _urn(state.get("asset_id"), "video")
        response = http.request(context, "GET", "/rest/videos/" + quote(asset, safe=""), headers=_HEADERS)
        if response.data.get("id") != asset:
            raise Invalid("LinkedIn video identity changed")
        status = response.data.get("status")
        if status not in ("AVAILABLE", "PROCESSING", "WAITING_UPLOAD", "PROCESSING_FAILED"):
            raise Invalid("Unknown LinkedIn video status")
        return _state(
            "READY_TO_PUBLISH"
            if status == "AVAILABLE"
            else "PROCESSING"
            if status in ("PROCESSING", "WAITING_UPLOAD")
            else "FAILED",
            asset_id=asset,
            observation={"asset_status": status},
        )
    remote = _urn(state.get("remote_id"), "(?:ugcPost|share)")
    response = http.request(
        context, "GET", "/rest/posts/" + quote(remote, safe=""), query={"viewContext": "AUTHOR"}, headers=_HEADERS
    )
    if response.data.get("id") != remote or response.data.get("author") != owner:
        raise Invalid("LinkedIn post identity changed")
    status = response.data.get("lifecycleState")
    if status not in ("PUBLISHED", "DRAFT", "PROCESSING"):
        raise Invalid("Unknown LinkedIn post status")
    return _state(
        "PUBLISHED" if status == "PUBLISHED" else "PROCESSING",
        remote_id=remote,
        asset_id=state.get("asset_id"),
        observation={"lifecycle_state": status, "public_visibility": "NOT_VERIFIED"},
    )
