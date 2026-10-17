"""Operator-inspected source facts and suggestions; no media or text is invented."""
import json
import math
from .common import Invalid,canonical,digest,iso_time,now,required,safe_data,uid
from .db import connection
from .creative_library import latest_capture

ROLES=("HOOK","PROBLEM","STAKES","REVEAL","DEMO","PROOF","OBJECTION","CTA")
TABLES={"creative_analyses","creative_briefs","creative_rank_policies","creative_relevance","creative_rank_reports","acquisition_intents","acquisition_panels","acquisition_observations","acquisition_reports","production_profiles","production_requirements"}


def analysis_data(data,capture):
    """Validate inspected provenance and phases, keeping unsupported phases absent."""
    safe_data(data)
    fields={"reference_id","capture_hash","inspection_kind","inspection_confirmed","inspected_at","analyst","format_family","duration_seconds","observations","uncertainty"}
    if set(data)!=fields:raise Invalid("Complete the inspection fields without unsupported columns")
    if data["capture_hash"]!=capture["hash"]:raise Invalid("Source capture changed; inspect the latest capture")
    if data["inspection_kind"] not in ("DIRECT_VIEW","PERMITTED_TRANSCRIPT") or data["inspection_confirmed"] is not True:raise Invalid("Confirm that you actually inspected permitted media or transcript")
    result=dict(data)
    for key,bound in (("analyst",120),("format_family",200),("uncertainty",2000)):result[key]=required(data[key],key.replace("_"," "),bound)
    result["inspected_at"]=iso_time(data["inspected_at"]).isoformat()
    if iso_time(result["inspected_at"])>iso_time(now()):raise Invalid("Inspection cannot be in the future")
    publication=capture["data"]["published_at"]
    if publication and iso_time(result["inspected_at"])<iso_time(publication):raise Invalid("Inspection cannot precede source publication")
    result["observations"]=observations_data(data)
    return result


def observations_data(data):
    """Normalize unique role observations and validate timing only when inspected."""
    rows=data["observations"]
    if not isinstance(rows,list) or not 1<=len(rows)<=8:raise Invalid("Record between 1 and 8 inspected phases")
    duration=data["duration_seconds"]
    if duration is not None:timing_number(duration,"Observed duration",3600)
    if data["inspection_kind"]!="DIRECT_VIEW" and duration is not None:raise Invalid("A transcript cannot establish media duration")
    result=[observation(row,data["inspection_kind"],duration) for row in rows]
    if len({r["role"] for r in result})!=len(result):raise Invalid("Each phase role may appear only once")
    return result


def timing_number(value,name,maximum):
    """Reject nonfinite, boolean or out-of-range source times."""
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=maximum:raise Invalid(name+": enter finite seconds within the inspected duration")
    return value


def observation(row,kind,duration):
    """Distinguish analyst suggestion from source observation and paired timing."""
    if not isinstance(row,dict) or set(row)!={"role","basis","detail","evidence_note","start_seconds","end_seconds"}:raise Invalid("Complete each phase's source and basis fields")
    if row["role"] not in ROLES or row["basis"] not in ("OBSERVED","SUGGESTED"):raise Invalid("Choose a phase and observed or suggested basis")
    result=dict(row)
    for key in ("detail","evidence_note"):result[key]=required(row[key],key.replace("_"," "),2000)
    observation_timing(row,kind,duration)
    return result


def observation_timing(row,kind,duration):
    """Require observed direct-view provenance for any paired source interval."""
    if row["start_seconds"] is not None or row["end_seconds"] is not None:
        if kind!="DIRECT_VIEW" or row["basis"]!="OBSERVED" or duration is None:raise Invalid("Timing requires directly inspected media and an observed phase")
        start=timing_number(row["start_seconds"],"Phase start",duration);end=timing_number(row["end_seconds"],"Phase end",duration)
        if start>=end:raise Invalid("Phase end must follow phase start")


def decoded(row):
    """Decode saved history without re-signing or changing data."""
    result=dict(row);result["data"]=json.loads(result["data"]);return result


def latest(db,table,app_id,item_id):
    """Resolve one current version from an internal allowlisted table and app."""
    if table not in TABLES:raise Invalid("Unknown production history")
    item_id=required(item_id,"Production item ID",120)
    row=db.execute(f"SELECT * FROM {table} WHERE app_id=? AND id=? ORDER BY version DESC LIMIT 1",(app_id,item_id)).fetchone()
    if not row:raise Invalid("Production item does not belong to this app")
    return decoded(row)


def append(db,table,app_id,data,body,identity=None):
    """Append with optimistic version, bounded storage and immutable source identity."""
    if table not in TABLES:raise Invalid("Unknown production history")
    item_id=body.get("id") or uid();version=1
    if "id" in body:
        old=latest(db,table,app_id,item_id)
        if type(body["version"]) is not int or old["version"]!=body["version"]:raise Invalid("Production item changed; reload before revising")
        if identity and old["data"][identity]!=data[identity]:raise Invalid("Revision cannot change this source identity")
        if old["hash"]==digest(data):return old
        version=old["version"]+1
    capacity(db,table,app_id,version)
    stamp=now();value_hash=digest(data)
    db.execute(f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",(app_id,item_id,version,canonical(data),value_hash,stamp))
    db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,table+".saved",canonical({"id":item_id,"version":version,"hash":value_hash}),stamp))
    return latest(db,table,app_id,item_id)


def capacity(db,table,app_id,version):
    """Bound identity and revision counts before each insert."""
    count=db.execute(f"SELECT count(*),count(DISTINCT id) FROM {table} WHERE app_id=?",(app_id,)).fetchone()
    if count[0]>=5000 or (version==1 and count[1]>=1000):raise Invalid("Archive this app before exceeding 1000 items or 5000 revisions")


def saved_items(db,table,app_id):
    """Return all immutable versions grouped by item, newest item first."""
    if table not in TABLES:raise Invalid("Unknown production history")
    grouped={}
    for row in db.execute(f"SELECT * FROM {table} WHERE app_id=? ORDER BY created,id,version",(app_id,)):
        item=decoded(row);grouped.setdefault(item["id"],[]).append(item)
    return [{"id":item_id,"versions":rows,"current":rows[-1]} for item_id,rows in reversed(list(grouped.items()))]


class Analyses:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Show stale capture status without replacing historic observations."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            items=saved_items(db,"creative_analyses",app_id)
            for item in items:
                data=item["current"]["data"];capture=latest_capture(db,app_id,data["reference_id"])
                item["source_status"]="CURRENT" if data["capture_hash"]==capture["hash"] else "STALE_SOURCE"
            return items

    def save(self,app_id,body):
        """Validate current capture and append a new analysis or explicit correction."""
        self.store.app(app_id)
        if set(body) not in ({"data"},{"id","version","data"}):raise Invalid("Invalid inspection save fields")
        safe_data(body["data"])
        reference_id=required(body["data"].get("reference_id"),"Source reference ID",120)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            capture=latest_capture(db,app_id,reference_id);data=analysis_data(body["data"],capture)
            existing=[r for r in saved_items(db,"creative_analyses",app_id) if r["current"]["data"]["reference_id"]==data["reference_id"]]
            if existing and "id" not in body:raise Invalid("This source has an analysis; use Correct inspection")
            return append(db,"creative_analyses",app_id,data,body,"reference_id")
