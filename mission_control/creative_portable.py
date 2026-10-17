"""Portable analysis/brief history; hash integrity never authenticates authorship."""
import json
from .common import Invalid,canonical,digest,iso_time,safe_data
from .creative_analysis import analysis_data,saved_items,decoded
from .creative_briefs import definition,compose
from .creative_library import reference_data


def export_production(db,app_id):
    """Export immutable source/brief versions, excluding derived freshness states."""
    return {"analyses":saved_items(db,"creative_analyses",app_id),"briefs":saved_items(db,"creative_briefs",app_id)}


def history_rows(items,app_id):
    """Validate exact grouped envelopes, bounded revisions and contiguous versions."""
    if not isinstance(items,list) or len(items)>1000:raise Invalid("Portable production history allows at most 1000 items")
    output=[];seen=set()
    for item in items:
        rows=history_item(item,seen)
        for version,row in enumerate(rows,1):validate_row(row,app_id,item["id"],version)
        output.extend(rows);seen.add(item["id"])
    if len(output)>5000:raise Invalid("Portable production history allows at most 5000 revisions")
    return output


def history_item(item,seen):
    """Validate one grouped current pointer before replaying its versions."""
    if not isinstance(item,dict) or set(item)!={"id","versions","current"} or item["id"] in seen:raise Invalid("Invalid or duplicate portable production identity")
    rows=item["versions"]
    if not isinstance(rows,list) or not rows or rows[-1]!=item["current"]:raise Invalid("Portable production current version changed")
    return rows


def validate_row(row,app_id,item_id,version):
    """Require exact scope, version, finite bytes and monotonically replayable identity."""
    if not isinstance(row,dict) or set(row)!={"app_id","id","version","data","hash","created"}:raise Invalid("Invalid portable production row")
    if row["app_id"]!=app_id or row["id"]!=item_id or type(row["version"]) is not int or row["version"]!=version:raise Invalid("Production history scope or version changed")
    safe_data(row["data"]);iso_time(row["created"])
    if digest(row["data"])!=row["hash"]:raise Invalid("Production history hash changed")


def captured_source(db,app_id,reference_id,value_hash):
    """Resolve an actual retained historical capture, never an arbitrary envelope."""
    row=db.execute("SELECT * FROM creative_captures WHERE app_id=? AND reference_id=? AND hash=?",(app_id,reference_id,value_hash)).fetchone()
    if not row:raise Invalid("Analysis source capture is absent from this workspace")
    return decoded(row)


def restore_analysis(db,app_id,rows):
    """Replay inspected analysis versions against their actual source captures."""
    identities={};references={}
    for row in rows:
        data=row["data"];source=captured_source(db,app_id,data.get("reference_id"),data.get("capture_hash"))
        if analysis_data(data,source)!=data:raise Invalid("Portable analysis is not normalized")
        reference=data["reference_id"]
        if identities.get(row["id"],reference)!=reference or references.get(reference,row["id"])!=row["id"]:raise Invalid("Analysis reference identity changed or duplicated")
        identities[row["id"]]=reference;references[reference]=row["id"]
        insert(db,"creative_analyses",row)


def brief_data(db,app_id,data,stamp=None):
    """Validate frozen historic evidence and deterministic original copy without approving it."""
    fields={"definition","app","app_hash","analysis","source","records","content","state","render","publication"}
    if set(data) not in (fields,fields|{"production"}) or (data["state"],data["render"],data["publication"])!=("PREPARED","NOT_RUN","NOT_RUN"):raise Invalid("Invalid portable preparation state")
    d=definition(data["definition"])
    if digest(data["app"])!=data["app_hash"]:raise Invalid("Frozen app manifest changed")
    row=db.execute("SELECT * FROM creative_analyses WHERE app_id=? AND id=? AND hash=?",(app_id,d["analysis_id"],d["analysis_hash"])).fetchone()
    if not row or decoded(row)!=data["analysis"]:raise Invalid("Brief analysis is absent or changed")
    a=data["analysis"]["data"];source=captured_source(db,app_id,a["reference_id"],a["capture_hash"])
    if source!=data["source"] or reference_data(source["data"])!=source["data"]:raise Invalid("Brief source changed")
    frozen_records(data,d,app_id)
    if "production" in data:
        from .production_portable import validate_frozen
        validate_frozen(db,app_id,data["production"],data["app_hash"],source,d["channel"],stamp)
    if compose(data)!=data["content"]:raise Invalid("Original brief content changed from its frozen proof")


def frozen_records(data,d,app_id):
    """Validate every selected frozen record hash and its explicit proof identity."""
    rows=data["records"]
    if not isinstance(rows,list) or len(rows)!=3+len(d["claim_ids"])+len(d["asset_ids"]):raise Invalid("Frozen production evidence is incomplete")
    expected={d[k+"_id"]:k for k in ("readiness","store","route")}
    expected.update({item:"claim" for item in d["claim_ids"]});expected.update({item:"asset" for item in d["asset_ids"]})
    if len(expected)!=len(rows) or len({r.get("id") for r in rows})!=len(rows):raise Invalid("Duplicate production evidence identity")
    for row in rows:
        if row.get("app_id")!=app_id or expected.get(row.get("id"))!=row.get("kind") or digest({"kind":row["kind"],"data":row["data"],"source":row["source"]})!=row.get("hash"):raise Invalid("Frozen production evidence scope or hash changed")


def insert(db,table,row):
    """Insert validated immutable history inside the caller's snapshot transaction."""
    if table not in ("creative_analyses","creative_briefs"):raise Invalid("Unknown production history")
    db.execute(f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",(row["app_id"],row["id"],row["version"],canonical(row["data"]),row["hash"],row["created"]))


def restore_production(db,app_id,payload):
    """Restore all source and brief history atomically; old snapshots remain valid."""
    if payload is None:return
    if not isinstance(payload,dict) or set(payload)!={"analyses","briefs"}:raise Invalid("Invalid portable production schema")
    analyses=history_rows(payload["analyses"],app_id);briefs=history_rows(payload["briefs"],app_id)
    restore_analysis(db,app_id,analyses)
    for row in briefs:
        brief_data(db,app_id,row["data"],row["created"]);insert(db,"creative_briefs",row)
