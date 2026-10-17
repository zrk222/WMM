"""Transactional portable native media. Integrity is not authenticated authorship."""
import base64
import json
from pathlib import Path
import re
import tempfile
from .common import Invalid,canonical,digest,iso_time,safe_data
from .creative_analysis import decoded
from .creative_rendering import render_rows,artifact_file
from .media_native import MAX_BYTES,SHAPES,caption_lines,validate_video


def export_media(store,app_id):
    """Export exact retained envelopes and validated actual bytes, never placeholder videos."""
    from .db import connection
    with connection(store.path) as db:rows=render_rows(db,app_id)
    files=[]
    for row in rows:
        path,data=artifact_file(store,app_id,row["id"])
        if validate_video(path,data["request"])!=data["artifact"]:raise Invalid("Video metadata changed; repair the artifact before export")
        files.append(dict(id=row["id"],base64=base64.b64encode(path.read_bytes()).decode()))
    return dict(rows=rows,files=files)


def media_envelope(app_id,row):
    """Validate one immutable app-scoped envelope before reading nested source data."""
    if not isinstance(row,dict) or set(row)!={"app_id","id","job_id","data","hash","created"}:raise Invalid("Invalid render history envelope")
    if row["app_id"]!=app_id or not re.fullmatch(r"[a-f0-9-]{36}",str(row["id"])) or not re.fullmatch(r"[a-f0-9-]{36}",str(row["job_id"])):raise Invalid("Invalid render identity or app scope")
    safe_data(row["data"]);iso_time(row["created"])
    if digest(row["data"])!=row["hash"]:raise Invalid("Render history hash changed")
    return row["data"]


def media_row(db,app_id,row):
    """Validate exact immutable envelope and retained historical source linkage."""
    data=media_envelope(app_id,row)
    if set(data)!={"request","artifact","renderer","publication","visual_review","audio"}:raise Invalid("Invalid rendered media fields")
    if (data["renderer"],data["publication"],data["visual_review"],data["audio"])!=("NATIVE_FFMPEG","NOT_RUN","REQUIRED","SILENT_CAPTIONED"):raise Invalid("Portable rendering cannot assert publication or visual approval")
    source_request(db,app_id,data["request"])


def source_request(db,app_id,request):
    """Bind exact historical brief and source caption timing without asserting freshness."""
    if not isinstance(request,dict) or set(request)!={"brief_id","brief_hash","shape","brief","captions","duration_seconds"} or request["shape"] not in SHAPES:raise Invalid("Invalid frozen render request")
    retained=db.execute("SELECT * FROM creative_briefs WHERE app_id=? AND id=? AND hash=?",(app_id,request["brief_id"],request["brief_hash"])).fetchone()
    if not retained or decoded(retained)!=request["brief"]:raise Invalid("Render source brief is not retained in this app")
    brief=request["brief"]["data"]
    if brief["definition"]["channel"]!="SHORT_VIDEO" or request["duration_seconds"]!=brief["definition"]["duration_seconds"]:raise Invalid("Rendered source timing or channel changed")
    if request["captions"]!=[b["script"] for b in brief["content"]["beats"]]:raise Invalid("Rendered original captions changed")
    for caption in request["captions"]:caption_lines(caption,request["duration_seconds"]/4,request["shape"])


def portable_bytes(items):
    """Decode a bounded one-to-one file manifest without writing untrusted names."""
    if not isinstance(items,list) or len(items)>1000:raise Invalid("Too many portable render files")
    files={}
    for item in items:
        if not isinstance(item,dict) or set(item)!={"id","base64"} or item["id"] in files:raise Invalid("Invalid or duplicate render file")
        if not isinstance(item["base64"],str) or len(item["base64"])>MAX_BYTES*2:raise Invalid("Portable video exceeds its size limit")
        raw=base64.b64decode(item["base64"],validate=True)
        if not 0<len(raw)<=MAX_BYTES:raise Invalid("Portable video exceeds its size limit")
        files[item["id"]]=raw
    return files


def restore_media(db,app_id,payload):
    """Re-decode all media before inserting history; return only validated files for commit."""
    if payload is None:return {}
    media_payload(payload)
    files=portable_bytes(payload["files"]);seen=set();jobs=set()
    for row in payload["rows"]:
        media_row(db,app_id,row)
        if row["id"] in seen or row["job_id"] in jobs or row["id"] not in files:raise Invalid("Duplicate or missing portable media identity")
        validate_bytes(files[row["id"]],row["data"])
        db.execute("INSERT INTO creative_renders VALUES(?,?,?,?,?,?)",(app_id,row["id"],row["job_id"],canonical(row["data"]),row["hash"],row["created"]))
        seen.add(row["id"]);jobs.add(row["job_id"])
    if seen!=set(files):raise Invalid("Portable media contains unreferenced files")
    return files


def media_payload(payload):
    """Require a bounded exact portable container before transactional replay."""
    if not isinstance(payload,dict) or set(payload)!={"rows","files"} or not isinstance(payload["rows"],list) or len(payload["rows"])>1000:raise Invalid("Invalid portable media history")


def validate_bytes(raw,data):
    """Probe supplied MP4 in an owned temporary folder before accepting its exact hash."""
    with tempfile.TemporaryDirectory(prefix="growth-media-verify-") as folder:
        path=Path(folder)/"video.mp4";path.write_bytes(raw)
        if validate_video(path,data["request"])!=data["artifact"]:raise Invalid("Portable video bytes or metadata changed")
