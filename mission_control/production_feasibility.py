"""Immutable capability history and explainable pre-production exclusions."""
from .common import Invalid,digest,now,safe_data
from .db import connection
from .creative_analysis import append,saved_items
from .creative_library import latest_capture,Library
from .production_contract import declaration,fresh
TABLES={"profile":"production_profiles","requirement":"production_requirements"}

def context(db,app_id):
    """Read only current declared capability and requirement revisions."""
    return current_context({kind:saved_items(db,table,app_id) for kind,table in TABLES.items()})


def current_context(items):
    """Project current versions from one loaded history without additional reads."""
    profiles=items["profile"]
    return {"profile":profiles[0]["current"] if profiles else None,
            "requirements":[r["current"] for r in items["requirement"]]}

def assess(inputs,source,app_hash,stamp,channel=None):
    """Expose missingness and every incompatible production requirement."""
    profile=inputs["profile"]
    requirements=[r for r in inputs["requirements"] if r["data"]["reference_id"]==source["id"]]
    reasons=[]
    if not profile:reasons.append("Set up current production capability")
    if not requirements:reasons.append("Review this source's production requirements")
    if reasons:return {"status":"BLOCKED","reasons":reasons,"evidence":None}
    requirement=requirements[0];p=profile["data"];q=requirement["data"]
    if p["app_hash"]!=app_hash:reasons.append("App changed; revise production capability")
    if q["capture_hash"]!=source["current"]["hash"]:reasons.append("Source changed; correct production requirements")
    if not fresh(p,stamp) or not fresh(q,stamp):reasons.append("Refresh production reviews within 30 days")
    reasons+=mismatches(p,q,channel)
    return {"status":"BLOCKED" if reasons else "READY","reasons":reasons,"evidence":{"profile":profile,"requirement":requirement}}

def mismatches(profile,requirement,channel):
    """Keep source execution, resources, capture and rights independent."""
    p,q=profile,requirement;reasons=[]
    for key,capability in (("execution","executions"),("talent","talent"),("audio","audio")):
        if q[key] not in p[capability]:reasons.append("Unavailable "+key+": "+q[key])
    for key in ("editing_level","cost_minor","time_minutes"):
        if q[key]>p[key]:reasons.append("Exceeds declared "+key.replace("_"," "))
    if q["requires_capture"] and not p["capture_available"]:reasons.append("Authentic capture is unavailable")
    if not q["rights_available"]:reasons.append("Source adaptation rights are not cleared")
    if channel is not None and channel not in p["channels"]:reasons.append("Channel is outside declared production capability")
    return reasons

def bound(db,app_id,app,source,channel):
    """Reject missing or infeasible production before freezing a new brief."""
    report=assess(context(db,app_id),{"id":source["reference_id"],"current":source},digest(app),now(),channel)
    if report["status"]!="READY":raise Invalid("Production blocked: "+"; ".join(report["reasons"]))
    return report["evidence"]

class Capabilities:
    def __init__(self,store):self.store=store

    def save(self,app_id,kind,body):
        """Append one app profile or one per-source requirement with optimistic revisions."""
        self.store.app(app_id);safe_data(body)
        if kind not in TABLES or set(body) not in ({"data"},{"id","version","data"}):raise Invalid("Invalid production setup fields")
        data=declaration(body["data"],kind)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            import json
            app=json.loads(db.execute("SELECT data FROM apps WHERE id=?",(app_id,)).fetchone()[0])
            rows=saved_items(db,TABLES[kind],app_id)
            if kind=="profile":
                if data["app_hash"]!=digest(app):raise Invalid("App changed; reload production setup")
                matches=rows
            else:
                if latest_capture(db,app_id,data["reference_id"])["hash"]!=data["capture_hash"]:raise Invalid("Source changed; reload production requirements")
                matches=[r for r in rows if r["current"]["data"]["reference_id"]==data["reference_id"]]
            if matches and "id" not in body:raise Invalid("Production setup exists; use Revise or Correct")
            return append(db,TABLES[kind],app_id,data,body,"reference_id" if kind=="requirement" else None)

    def list(self,app_id):
        """Expose persisted setup and current app/source evaluations without writes."""
        app=self.store.app(app_id);sources=Library(self.store).list(app_id)
        with connection(self.store.path) as db:
            items={kind:saved_items(db,table,app_id) for kind,table in TABLES.items()}
        inputs=current_context(items)
        items["app_hash"]=digest(app["data"])
        items["evaluations"]=[{"reference_id":s["id"],"title":s["current"]["data"]["title"],**assess(inputs,s,items["app_hash"],now())} for s in sources]
        return items
