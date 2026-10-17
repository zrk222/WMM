"""Atomic source-bound ranking replay; integrity does not authenticate authorship."""
from .common import Invalid,canonical,digest,iso_time,now,required
from .creative_analysis import decoded,saved_items
from .creative_portable import history_item,validate_row,captured_source
from .creative_ranking import TABLES,calculate,policy_data,relevance_data


def export_rankings(db,app_id):
    """Retain declared policy, supplied reviews and complete frozen report inputs."""
    return {kind:saved_items(db,table,app_id) for kind,table in TABLES.items()}


def rank_rows(items,app_id,kind):
    """Validate exact grouped history with a separate bounded report envelope."""
    if not isinstance(items,list) or len(items)>1000:raise Invalid("Ranking history allows at most 1000 items")
    rows=[];seen=set()
    for item in items:
        if not isinstance(item,dict):raise Invalid("Invalid ranking history item")
        required(item.get("id"),"Ranking item ID",120)
        versions=history_item(item,seen);seen.add(item["id"])
        for version,row in enumerate(versions,1):
            if kind=="report":validate_report_row(row,app_id,item["id"],version)
            else:validate_row(row,app_id,item["id"],version)
        rows.extend(versions)
    if len(rows)>5000:raise Invalid("Ranking history allows at most 5000 revisions")
    return rows


def validate_report_row(row,app_id,item_id,version):
    """Allow generated peer denominators without weakening exact scope or hash checks."""
    if not isinstance(row,dict) or set(row)!={"app_id","id","version","data","hash","created"}:raise Invalid("Invalid ranking report row")
    if row["app_id"]!=app_id or row["id"]!=item_id or type(row["version"]) is not int or row["version"]!=version:raise Invalid("Ranking report scope/version changed")
    if len(canonical(row["data"]).encode())>16777216 or digest(row["data"])!=row["hash"]:raise Invalid("Ranking report bytes/hash changed")
    iso_time(row["created"])


def insert_rank(db,table,row):
    """Use only internally allowlisted tables inside the caller's restore transaction."""
    if table not in TABLES.values():raise Invalid("Unknown ranking history")
    db.execute(f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",(row["app_id"],row["id"],row["version"],canonical(row["data"]),row["hash"],row["created"]))


def retained_row(db,table,app_id,row):
    """Require the exact historical policy/review, not only matching source text."""
    if not isinstance(row,dict) or table not in TABLES.values():raise Invalid("Invalid frozen ranking row")
    required(row.get("id"),"Ranking item ID",120)
    if type(row.get("version")) is not int:raise Invalid("Invalid ranking item version")
    actual=db.execute(f"SELECT * FROM {table} WHERE app_id=? AND id=? AND version=?",(app_id,row.get("id"),row.get("version"))).fetchone()
    if not actual or decoded(actual)!=row:raise Invalid("Frozen ranking policy/review changed or absent")


def retained_pool(db,app_id,sources,evaluated_at):
    """Resolve every frozen capture against retained app history and source identity."""
    if not isinstance(sources,list) or not 1<=len(sources)<=100:raise Invalid("Invalid frozen ranking source pool")
    ids=[]
    for source in sources:
        if not isinstance(source,dict) or set(source)!={"app_id","id","identity","captures","current"}:raise Invalid("Invalid frozen source envelope")
        required(source["id"],"Source ID",120);ids.append(source["id"])
        retained_source(db,app_id,source,evaluated_at)
    if ids!=sorted(set(ids)):raise Invalid("Ranking pool identity or ordering changed")


def retained_source(db,app_id,source,evaluated_at):
    """Bound the velocity window to two genuine contiguous observations."""
    row=db.execute("SELECT * FROM creative_references WHERE app_id=? AND id=?",(app_id,source["id"])).fetchone()
    if not row or dict(row)!={k:source[k] for k in ("app_id","id","identity")}:raise Invalid("Frozen ranking source belongs to another app")
    captures=source["captures"]
    if not isinstance(captures,list) or not 1<=len(captures)<=2 or source["current"]!=captures[-1]:raise Invalid("Invalid ranking observation window")
    retained_captures(db,app_id,source["id"],captures,evaluated_at)


def retained_captures(db,app_id,reference_id,captures,evaluated_at):
    """Verify exact captured bytes before checking the contiguous velocity pair."""
    for capture in captures:
        if not isinstance(capture,dict):raise Invalid("Invalid ranking capture")
        actual=captured_source(db,app_id,reference_id,capture.get("hash"))
        if actual!=capture or iso_time(capture["data"]["captured_at"])>iso_time(evaluated_at):raise Invalid("Frozen ranking capture changed or dated after report")
    if len(captures)==2 and captures[1]["version"]!=captures[0]["version"]+1:raise Invalid("Ranking velocity window is not contiguous")


def report_data(db,app_id,data):
    """Recompute every output from exact retained inputs, never trust restored scores."""
    if not isinstance(data,dict) or "inputs" not in data or "evaluated_at" not in data:raise Invalid("Invalid ranking report")
    inputs=data["inputs"]
    fields={"app","app_hash","policy","sources","reviews"}
    if not isinstance(inputs,dict) or set(inputs) not in (fields,fields|{"production"}):raise Invalid("Invalid ranking input envelope")
    if digest(inputs["app"])!=inputs["app_hash"]:raise Invalid("Ranking app manifest changed")
    if iso_time(data["evaluated_at"])>iso_time(now()):raise Invalid("Ranking report cannot be dated in future")
    retained_row(db,TABLES["policy"],app_id,inputs["policy"])
    retained_pool(db,app_id,inputs["sources"],data["evaluated_at"])
    retained_reviews(db,app_id,inputs["reviews"])
    if "production" in inputs:retained_production(db,app_id,inputs["production"])
    if calculate(inputs,data["evaluated_at"])!=data:raise Invalid("Ranking components or selection changed")


def retained_production(db,app_id,production):
    """Authenticate frozen production references against restored scoped history."""
    from .production_portable import retained
    if not isinstance(production,dict) or set(production)!={"profile","requirements"}:raise Invalid("Invalid ranking production context")
    if production["profile"] is not None:retained(db,app_id,"profile",production["profile"])
    if not isinstance(production["requirements"],list) or len(production["requirements"])>100:raise Invalid("Invalid ranking production requirements")
    ids=[r.get("id") for r in production["requirements"] if isinstance(r,dict)]
    if len(ids)!=len(production["requirements"]) or len(set(ids))!=len(ids):raise Invalid("Duplicate or invalid production requirements")
    for row in production["requirements"]:retained(db,app_id,"requirement",row)


def retained_reviews(db,app_id,reviews):
    """Require distinct ordered review identities from this app's retained history."""
    if not isinstance(reviews,list) or len(reviews)>100:raise Invalid("Invalid ranking relevance pool")
    if any(not isinstance(r,dict) or not isinstance(r.get("id"),str) for r in reviews):raise Invalid("Invalid ranking review identity")
    ids=[r["id"] for r in reviews]
    if ids!=sorted(set(ids)):raise Invalid("Ranking review identity/ordering changed")
    for row in reviews:retained_row(db,TABLES["relevance"],app_id,row)


def restore_reviews(db,app_id,rows):
    """Retain review identity and validate the historical source capture before replay."""
    identities={};references={}
    for row in rows:
        d=relevance_data(row["data"]);ref=d["reference_id"]
        captured_source(db,app_id,ref,d["capture_hash"])
        if identities.get(row["id"],ref)!=ref or references.get(ref,row["id"])!=row["id"]:raise Invalid("Ranking review source identity changed")
        identities[row["id"]]=ref;references[ref]=row["id"]
        insert_rank(db,TABLES["relevance"],row)


def restore_rankings(db,app_id,payload):
    """Replay all ranking history in the existing all-or-nothing snapshot transaction."""
    if payload is None:return
    if not isinstance(payload,dict) or set(payload)!=set(TABLES):raise Invalid("Invalid ranking snapshot schema")
    rows={kind:rank_rows(payload[kind],app_id,kind) for kind in TABLES}
    if len({r["id"] for r in rows["policy"]})>1:raise Invalid("This app must have one versioned ranking policy")
    for row in rows["policy"]:
        policy_data(row["data"]);insert_rank(db,TABLES["policy"],row)
    restore_reviews(db,app_id,rows["relevance"])
    for row in rows["report"]:
        report_data(db,app_id,row["data"]);insert_rank(db,TABLES["report"],row)
