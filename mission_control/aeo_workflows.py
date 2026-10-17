"""Immutable, app-bound public checks; network reads never hold a SQL transaction."""
from datetime import timedelta
import json
import time
from .common import Invalid, canonical, digest, now, iso_time, uid
from .db import connection
from .aeo_contract import fields, require, number, sha, url, report, repairs
from .aeo_transport import PublicReader, public_url, origin
from .aeo_inspection import inspect_page
from .creative_analysis import latest
from .acquisition_contract import intent_status

FRESH_SECONDS = 604800


def app_row(db, app_id):
    """Read one manifest inside the caller's transaction."""
    row=db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    if row is None:
        raise KeyError("App workspace not found")
    return {"id":row["id"],"data":json.loads(row["data"]),"version":row["version"]}


def binding(db, store, app_id, body):
    """Bind exact current manifest and optional intent; no arbitrary third-party target."""
    fields(body, "app_version app_hash url intent_id intent_hash")
    app=app_row(db,app_id)
    require(type(body["app_version"]) is int and body["app_version"] == app["version"], "App changed. Reload before checking.")
    require(sha(body["app_hash"]) == digest(app["data"]), "App changed. Reload before checking.")
    target=public_url(body["url"])
    website=app["data"].get("website")
    require(bool(website), "Save this app's public HTTPS website in App setup first.")
    require(origin(target) == origin(public_url(website)), "Choose a page on this app's declared website.")
    intent=intent_binding(db,store,app_id,body,target)
    return {"app":app,"app_hash":digest(app["data"]),"intent":intent,"target":target}


def intent_binding(db, store, app_id, body, target):
    """An intent must be current, app-owned and point to the exact checked page."""
    if body["intent_id"] is None:
        require(body["intent_hash"] is None, "Choose both intent identity and hash.")
        return None
    require(isinstance(body["intent_id"],str) and len(body["intent_id"]) <= 120)
    sha(body["intent_hash"])
    row=latest(db,"acquisition_intents",app_id,body["intent_id"])
    require(row["hash"] == body["intent_hash"], "Intent changed. Reload before checking.")
    require(intent_status(db,store,app_id,row) == "CURRENT", "Repair the intent's evidence before checking its page.")
    require(public_url(row["data"]["definition"]["page_url"]) == target, "Use the exact selected intent page.")
    return row


def decode(row):
    """Decode local storage while preserving provenance outside asserted data."""
    return {"app_id":row["app_id"],"id":row["id"],"data":json.loads(row["data"]),
            "hash":row["hash"],"created":row["created"],"origin":row["origin"]}


def rows(db, app_id):
    """Return only immutable history for the chosen workspace."""
    return [decode(r) for r in db.execute("SELECT * FROM aeo_checks WHERE app_id=? ORDER BY created DESC,id", (app_id,))]


def currentness(db, store, app_id, row):
    """Imported assertions and changed or expired native checks cannot appear current."""
    if row["origin"] != "LOCAL_OBSERVATION":
        return "IMPORTED_ASSERTION"
    data=row["data"]; bound=data["binding"]; app=app_row(db,app_id)
    if app != bound["app"] or digest(app["data"]) != bound["app_hash"]:
        return "STALE_APP"
    if bound["intent"] is not None:
        try:
            old=bound["intent"]; current=latest(db,"acquisition_intents",app_id,old["id"])
            if current != old or intent_status(db,store,app_id,current) != "CURRENT":
                return "STALE_INTENT"
        except (Invalid,KeyError):
            return "STALE_INTENT"
    age=(iso_time(now())-iso_time(data["observed_at"])).total_seconds()
    return "CURRENT" if 0 <= age <= FRESH_SECONDS else "STALE_TIME"


class Checks:
    """Explicit read-only diagnosis and durable failure recovery."""
    def __init__(self, store):
        """Use the independent Mission Control database only."""
        self.store=store

    def list(self, app_id):
        """Return fresh manifest binding, passive history and actionable setup."""
        with connection(self.store.path) as db:
            app=app_row(db,app_id)
            history=[dict(row,evidence_status=currentness(db,self.store,app_id,row)) for row in rows(db,app_id)]
        return {"app_version":app["version"],"app_hash":digest(app["data"]),"website":app["data"].get("website") or "",
                "checks":history,"fresh_seconds":FRESH_SECONDS,"indexing":"NOT_VERIFIED","citations":"NOT_MEASURED","growth":"NOT_MEASURED"}

    def run(self, app_id, body, reader=None):
        """Read once and refuse to commit if the app or intent changed during IO."""
        with connection(self.store.path) as db:
            bound=binding(db,self.store,app_id,body)
            self.capacity(db,app_id)
        started_at=now(); clock=time.monotonic(); reader=reader or PublicReader()
        result=inspect_page(bound["target"],reader)
        elapsed=round((time.monotonic()-clock)*1000)
        data={"binding":bound,"started_at":started_at,"observed_at":now(),"report":result,
              "budget":{"requests":reader.requests,"redirects":reader.redirects,"elapsed_ms":elapsed},
              "repairs":repairs(result)}
        validate_data(data,app_id)
        row={"app_id":app_id,"id":uid(),"data":data,"hash":digest(data),"created":data["observed_at"],"origin":"LOCAL_OBSERVATION"}
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            require(binding(db,self.store,app_id,body) == bound, "App or intent changed during the check. Reload and run again.")
            self.capacity(db,app_id)
            insert(db,row,"LOCAL_OBSERVATION")
        return row

    def capacity(self, db, app_id):
        """Bound persistent growth before and after the network operation."""
        count=db.execute("SELECT count(*) FROM aeo_checks WHERE app_id=?",(app_id,)).fetchone()[0]
        require(count < 500, "AEO history limit reached. Export the workspace before archival.")


def insert(db, row, provenance):
    """Append one immutable observation with server-controlled provenance."""
    db.execute("INSERT INTO aeo_checks VALUES(?,?,?,?,?,?)",
               (row["app_id"],row["id"],canonical(row["data"]),row["hash"],row["created"],provenance))


def validate_data(data, app_id):
    """Validate native or portable facts before retaining any evidence."""
    fields(data,"binding started_at observed_at report budget repairs")
    require(len(canonical(data).encode()) <= 1048576, "AEO observation exceeds 1 MB.")
    bound=fields(data["binding"],"app app_hash intent target")
    app=fields(bound["app"],"id data version")
    require(app["id"] == app_id and isinstance(app["data"],dict))
    number(app["version"],2147483647); require(app["version"] > 0)
    require(sha(bound["app_hash"]) == digest(app["data"]))
    require(origin(url(bound["target"])) == origin(public_url(app["data"].get("website"))))
    started=iso_time(data["started_at"]); observed=iso_time(data["observed_at"])
    require(started.utcoffset() == timedelta(0) and observed.utcoffset() == timedelta(0) and started <= observed <= iso_time(now()))
    report(data["report"]); require(data["report"]["target"] == bound["target"])
    budget=fields(data["budget"],"requests redirects elapsed_ms")
    number(budget["requests"],6); number(budget["redirects"],3); number(budget["elapsed_ms"],31000)
    require(budget["requests"] >= 1 and budget["redirects"] <= budget["requests"])
    require(data["repairs"] == repairs(data["report"]))
