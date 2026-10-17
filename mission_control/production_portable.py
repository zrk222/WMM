"""Transactional capability history; portable hashes do not prove real-world rights."""
from .common import Invalid,canonical
from .creative_analysis import saved_items,decoded
from .production_contract import declaration
from .production_feasibility import TABLES,assess

def export_capabilities(db,app_id):
    """Preserve immutable declarations without exporting readiness or authority."""
    return {kind:saved_items(db,table,app_id) for kind,table in TABLES.items()}

def restore_capabilities(db,app_id,payload):
    """Validate every scoped row before replay inside the snapshot transaction."""
    if payload is None:return
    from .creative_portable import history_rows,captured_source
    if not isinstance(payload,dict) or set(payload)!=set(TABLES):raise Invalid("Invalid portable production capability")
    rows={kind:history_rows(payload[kind],app_id) for kind in TABLES}
    if len({r["id"] for r in rows["profile"]})>1:raise Invalid("Only one versioned app production profile is allowed")
    for kind in TABLES:
        identities={};sources={}
        for row in rows[kind]:
            d=declaration(row["data"],kind)
            if kind=="requirement":
                captured_source(db,app_id,d["reference_id"],d["capture_hash"])
                ref=d["reference_id"]
                if identities.get(row["id"],ref)!=ref or sources.get(ref,row["id"])!=row["id"]:raise Invalid("Production requirement source changed or duplicated")
                identities[row["id"]]=ref;sources[ref]=row["id"]
            db.execute(f"INSERT INTO {TABLES[kind]} VALUES(?,?,?,?,?,?)",(app_id,row["id"],row["version"],canonical(d),row["hash"],row["created"]))

def retained(db,app_id,kind,row):
    """Require exact retained history; never accept a detached frozen declaration."""
    if not isinstance(row,dict) or row.get("app_id")!=app_id:raise Invalid("Frozen production scope changed")
    actual=db.execute(f"SELECT * FROM {TABLES[kind]} WHERE app_id=? AND id=? AND version=?",(app_id,row.get("id"),row.get("version"))).fetchone()
    if not actual or decoded(actual)!=row:raise Invalid("Frozen production history changed or is absent")

def validate_frozen(db,app_id,evidence,app_hash,source,channel=None,stamp=None):
    """Verify brief production sources independently of present-day capability."""
    if not isinstance(evidence,dict) or set(evidence)!={"profile","requirement"}:raise Invalid("Invalid frozen production evidence")
    for kind,row in evidence.items():retained(db,app_id,kind,row)
    p=evidence["profile"]["data"];q=evidence["requirement"]["data"]
    if p["app_hash"]!=app_hash or q["reference_id"]!=source["reference_id"] or q["capture_hash"]!=source["hash"]:raise Invalid("Frozen production app/source binding changed")
    if stamp is not None:
        inputs={"profile":evidence["profile"],"requirements":[evidence["requirement"]]}
        report=assess(inputs,{"id":source["reference_id"],"current":source},app_hash,stamp,channel)
        if report["status"]!="READY":raise Invalid("Frozen production was infeasible: "+"; ".join(report["reasons"]))
