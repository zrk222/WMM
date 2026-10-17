"""Proof-bound, owned native rendering with immutable app-scoped artifacts."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time
from .common import Invalid,canonical,digest,now,required,uid
from .db import connection
from .creative_analysis import latest,decoded
from .creative_briefs import stale_findings
from .media_native import SHAPES,capability,caption_lines,render_native


def render_request(db,store,app_id,body):
    """Freeze only the exact latest current short-video brief and supported readable copy."""
    if not isinstance(body,dict) or set(body)!={"brief_id","brief_hash","shape"}:raise Invalid("Choose a current brief and portrait or landscape video")
    if body["shape"] not in SHAPES:raise Invalid("Choose portrait or landscape")
    brief=latest(db,"creative_briefs",app_id,body["brief_id"])
    if brief["hash"]!=body["brief_hash"]:raise Invalid("Brief changed; reload before rendering")
    if brief["data"]["definition"]["channel"]!="SHORT_VIDEO":raise Invalid("Choose a short-video brief for MP4 rendering")
    findings=stale_findings(db,store,app_id,brief["data"])
    if findings:raise Invalid("Repair current brief proof: "+"; ".join(findings))
    duration=brief["data"]["definition"]["duration_seconds"];captions=[b["script"] for b in brief["data"]["content"]["beats"]]
    for script in captions:caption_lines(script,duration/4,body["shape"])
    return dict(body,brief=brief,captions=captions,duration_seconds=duration)


def current_request(db,store,app_id,request):
    """Reject any semantic change, including forged worker input and later proof failures."""
    body={key:request[key] for key in ("brief_id","brief_hash","shape")}
    if render_request(db,store,app_id,body)!=request:raise Invalid("Frozen render inputs changed; prepare a new job")


def owned(db,job):
    """Keep attempt identity and cancellation authoritative throughout artifact creation."""
    row=db.execute("SELECT status,attempts FROM jobs WHERE id=? AND app_id=?",(job["id"],job["app_id"])).fetchone()
    if not row or row["status"]!="RUNNING" or row["attempts"]!=job["attempts"]:raise Invalid("Render cancelled or superseded; no artifact was committed")


def heartbeat(store,job,stop=None):
    """Renew only the owned attempt; worker shutdown terminates its private process."""
    if stop is not None and stop.is_set():raise Invalid("Worker stopped; retry the saved render")
    with connection(store.path) as db:
        owned(db,job)
        db.execute("UPDATE jobs SET lease=?,updated=? WHERE id=? AND attempts=? AND status=?",(time.time()+60,now(),job["id"],job["attempts"],"RUNNING"))


def folder_for(store,app_id):
    """Use only a validated existing app namespace for media storage."""
    store.app(app_id)
    return store.path.parent/"renders"/app_id


def artifact_file(store,app_id,render_id):
    """Validate saved scope and bytes before preview or downloading an actual MP4."""
    if not isinstance(render_id,str) or not re.fullmatch(r"[a-f0-9-]{36}",render_id):raise Invalid("Invalid render identifier")
    with connection(store.path) as db:
        row=db.execute("SELECT * FROM creative_renders WHERE app_id=? AND id=?",(app_id,render_id)).fetchone()
    if not row:raise Invalid("Video does not belong to this app")
    data=decoded(row)["data"];path=folder_for(store,app_id)/(render_id+".mp4")
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=data["artifact"]["sha256"]:raise Invalid("Video is missing or changed; render a new version")
    return path,data


def render_rows(db,app_id):
    """Read immutable envelopes with no derived state for portability."""
    return [decoded(row) for row in db.execute("SELECT * FROM creative_renders WHERE app_id=? ORDER BY created DESC,id",(app_id,))]


class Renders:
    def __init__(self,store):self.store=store

    def queue(self,app_id,body):
        """Queue validated immutable local work; replays return their original durable job."""
        from .worker import enqueue
        self.store.app(app_id)
        if set(body)!={"data","request_key"}:raise Invalid("Render needs its guided fields and retry identity")
        if capability()["status"]!="READY":raise Invalid(capability()["repair"])
        with connection(self.store.path) as db:request=render_request(db,self.store,app_id,body["data"])
        return enqueue(self.store,app_id,"render",request,body["request_key"])

    def list(self,app_id):
        """Expose saved bytes and source freshness independently from job status."""
        self.store.app(app_id)
        with connection(self.store.path) as db:rows=render_rows(db,app_id)
        for row in rows:
            try:
                artifact_file(self.store,app_id,row["id"])
                with connection(self.store.path) as db:current_request(db,self.store,app_id,row["data"]["request"])
                row["status"]="CURRENT"
            except (Invalid,OSError,KeyError):row["status"]="STALE_OR_UNAVAILABLE"
        return dict(capability=capability(),items=rows)

    def execute(self,job,stop=None):
        """Render privately then revalidate proof and owned job inside an atomic commit."""
        app_id=job["app_id"];request=job["data"];root=folder_for(self.store,app_id)
        root.mkdir(parents=True,exist_ok=True)
        with connection(self.store.path) as db:
            owned(db,job);current_request(db,self.store,app_id,request)
            previous=db.execute("SELECT * FROM creative_renders WHERE app_id=? AND job_id=?",(app_id,job["id"])).fetchone()
        if previous:
            row=decoded(previous);artifact_file(self.store,app_id,row["id"])
            return dict(render_id=row["id"],artifact_hash=row["data"]["artifact"]["sha256"],publication="NOT_RUN")
        with tempfile.TemporaryDirectory(prefix="render-",dir=root) as temporary:
            folder=Path(temporary);screens=self.copy_screens(folder,app_id,request)
            output,artifact=render_native(folder,request,screens,lambda:heartbeat(self.store,job,stop))
            heartbeat(self.store,job,stop)
            return self.commit(job,request,artifact,output)

    def copy_screens(self,folder,app_id,request):
        """Copy selected actual bytes to private paths and verify hashes after copying."""
        result=[]
        for index,screen in enumerate(request["brief"]["data"]["content"]["screens"]):
            source=self.store.path.parent/"files"/app_id/screen["file_id"]
            target=folder/("screen"+str(index)+source.suffix)
            shutil.copyfile(source,target)
            if hashlib.sha256(target.read_bytes()).hexdigest()!=screen["sha256"]:raise Invalid("Scene bytes changed while rendering; upload and verify again")
            result.append(target)
        return result

    def commit(self,job,request,artifact,output):
        """Commit only owned fresh media; remove exclusively created output on DB failure."""
        app_id=job["app_id"];render_id=uid();target=folder_for(self.store,app_id)/(render_id+".mp4");created=False
        data=dict(request=request,artifact=artifact,renderer="NATIVE_FFMPEG",publication="NOT_RUN",visual_review="REQUIRED",audio="SILENT_CAPTIONED")
        try:
            with connection(self.store.path) as db:
                db.execute("BEGIN IMMEDIATE");owned(db,job);current_request(db,self.store,app_id,request)
                with target.open("xb") as destination:created=True;destination.write(output.read_bytes())
                db.execute("INSERT INTO creative_renders VALUES(?,?,?,?,?,?)",(app_id,render_id,job["id"],canonical(data),digest(data),now()))
                db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,"render.completed",canonical({"id":render_id,"hash":digest(data)}),now()))
        except Exception:
            if created:target.unlink(missing_ok=True)
            raise
        return dict(render_id=render_id,artifact_hash=artifact["sha256"],publication="NOT_RUN")
