"""Original evidence-bound briefs; preparation never implies rendering or publication."""
import sqlite3
import json
from .common import Invalid,amount,digest,iso_time,now,required,safe_data
from .db import connection
from .creative_analysis import latest,append,saved_items
from .creative_library import latest_capture,source_url
from .experiments import asset_intact
from .production_feasibility import bound as production_bound

CHANNELS=("SHORT_VIDEO","LINKEDIN","X")
FIELDS={"analysis_id","analysis_hash","channel","objective","owner","claim_ids","asset_ids","readiness_id","store_id","route_id","currency","budget_minor","duration_seconds"}


def definition(data):
    """Require explicit objective, budget, channel and app evidence identities."""
    safe_data(data)
    if set(data)!=FIELDS:raise Invalid("Complete the brief preparation fields")
    result=dict(data)
    for key in ("objective","owner"):result[key]=required(data[key],key,2000)
    for key in ("analysis_id","analysis_hash","readiness_id","store_id","route_id"):result[key]=required(data[key],key,120)
    if data["channel"] not in CHANNELS:raise Invalid("Choose short video, LinkedIn or X")
    if type(data["duration_seconds"]) is not int or data["duration_seconds"] not in (15,30,45,60):raise Invalid("Choose a 15, 30, 45 or 60 second scene plan")
    amount(data["budget_minor"],"Production budget")
    for key in ("claim_ids","asset_ids"):
        evidence_ids(data[key],key)
    return result


def evidence_ids(ids,key):
    """Require a small explicit selection of distinct evidence identifiers."""
    if not isinstance(ids,list) or not 1<=len(ids)<=5 or any(not isinstance(v,str) for v in ids) or len(set(ids))!=len(ids):raise Invalid("Choose 1 through 5 distinct "+key.replace("_"," "))


def bound_record(db,app_id,item_id,kind,app):
    """Freeze only selected app/release/locale evidence with its canonical hash."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    row=db.execute("SELECT * FROM records WHERE app_id=? AND id=? AND kind=?",(app_id,item_id,kind)).fetchone()
    if not row:raise Invalid("Choose "+kind+" evidence from this app")
    result=dict(row);result["data"]=json.loads(result["data"]);data=result["data"]
    if data.get("release")!=app["release"]:raise Invalid(kind+" does not match the current app release")
    if kind in ("readiness","claim","asset","store") and data.get("locale")!=app["locale"]:raise Invalid(kind+" does not match the current app locale")
    if kind!="asset":checked(data,kind)
    return result


def checked(data,kind):
    """Reject old, future or failed supplied product proofs, including route fallbacks."""
    age=(iso_time(now())-iso_time(data.get("checked_at"))).total_seconds()
    if not 0<=age<=14*86400:raise Invalid(kind+" needs a passing check within 14 days")
    if kind=="store":
        if data.get("availability")!="AVAILABLE":raise Invalid("Store destination must be available")
        source_url(data.get("destination"))
    elif data.get("result")!="PASS":raise Invalid(kind+" proof did not pass")
    if kind=="readiness":
        from .journey_readiness import complete
        if not complete(data):raise Invalid("Complete current journey coverage and resolve critical product findings before preparing marketing")
    if kind=="route":route_checked(data)


def route_checked(data):
    """Require all entry states and an explicit usable fallback description."""
    if not all(data.get(key) is True for key in ("installed","fresh_install","signed_out")):raise Invalid("Test installed, fresh-install and signed-out routes")
    required(data.get("fallback"),"Tested route fallback",2000)


def latest_proof(db,app_id,record,app):
    """A selected old pass cannot hide a newer failure in the applicable scope."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    rows=db.execute("SELECT data FROM records WHERE app_id=? AND kind=? ORDER BY updated DESC,id DESC",(app_id,record["kind"]))
    for row in rows:
        data=json.loads(row[0])
        if data.get("release")!=app["release"]:continue
        if record["kind"] in ("claim","store") and data.get("locale")!=app["locale"]:continue
        if record['kind']=='readiness' and data.get('locale') not in (None,'',app['locale']):continue
        checked(data,record["kind"])
        return


def critical_findings(db,app_id):
    """Confirmed P0 product evidence blocks fresh briefs until resolved."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    for row in db.execute("SELECT data FROM records WHERE app_id=? AND kind='review'",(app_id,)):
        data=json.loads(row[0])
        if data.get("confirmed") is True and data.get("severity")=="P0":raise Invalid("Resolve the confirmed P0 before preparing this brief")


def bind(db,store,app_id,data):
    """Freeze current app, inspection, selected proof and actual scene bytes."""
    if type(db) is not sqlite3.Connection: raise TypeError('Native SQLite connection required')
    requested=definition(data);app=json.loads(db.execute("SELECT data FROM apps WHERE id=?",(app_id,)).fetchone()[0])
    for key in ("name","job","audience","activation","release","locale","currency"):required(app.get(key),"App "+key)
    if data["currency"]!=app["currency"]:raise Invalid("Production budget currency must match this app")
    analysis=latest(db,"creative_analyses",app_id,data["analysis_id"])
    if analysis["hash"]!=data["analysis_hash"]:raise Invalid("Analysis changed; reload the current inspection")
    capture=latest_capture(db,app_id,analysis["data"]["reference_id"])
    if capture["hash"]!=analysis["data"]["capture_hash"]:raise Invalid("Source changed; correct the inspection before preparing a brief")
    records=bind_proofs(db,store,app_id,app,data);critical_findings(db,app_id)
    frozen={"definition":requested,"app":app,"app_hash":digest(app),"analysis":analysis,"source":capture,"records":records,"production":production_bound(db,app_id,app,capture,data["channel"])}
    return dict(frozen,content=compose(frozen),state="PREPARED",render="NOT_RUN",publication="NOT_RUN")


def bind_proofs(db,store,app_id,app,data):
    """Bind current product checks and verify authentic, rights-cleared asset bytes."""
    selected=[(data[key+"_id"],key) for key in ("readiness","store","route")]
    selected += [(item,"claim") for item in data["claim_ids"]]+[(item,"asset") for item in data["asset_ids"]]
    records=[]
    for item_id,kind in selected:
        record=bound_record(db,app_id,item_id,kind,app)
        if kind=="asset":asset_checked(store,app_id,record["data"])
        else:latest_proof(db,app_id,record,app)
        records.append(record)
    return records


def asset_checked(store,app_id,data):
    """Require real current scene bytes and explicit authenticity and usage rights."""
    if data.get("authentic") is not True or data.get("rights_cleared") is not True:raise Invalid("Screens must be authentic and rights cleared")
    if not asset_intact(store.path.parent/"files"/app_id,data):raise Invalid("Scene image is missing or changed; upload and verify it again")


def compose(frozen):
    """Create original copy from explicit app hypotheses and exact approved claims."""
    app=frozen["app"];d=frozen["definition"];analysis=frozen["analysis"]["data"]
    claims=[r["data"]["claim"] for r in frozen["records"] if r["kind"]=="claim"]
    destination=next(r["data"]["destination"] for r in frozen["records"] if r["kind"]=="store")
    hooks=["What would a useful next step look like for "+d["objective"]+"?", "Before your next decision, try one concrete example with "+app["name"]+".", "From a question to a next step: an inside look at "+app["name"]+"."]
    scenes=[{"asset_id":r["id"],"file_id":r["data"]["file_id"],"sha256":r["data"]["sha256"],"instruction":"Capture this actual screen at a readable size; use a fictional test without private information."} for r in frozen["records"] if r["kind"]=="asset"]
    content={"hooks":hooks,"copy":channel_copy(d["channel"],app,d,hooks,claims,destination),"beats":scene_beats(d,hooks,claims,destination),
             "screens":scenes,"demo_steps":["Open the tested first-value route: "+destination,"Enter a clearly labeled fictional example about "+d["objective"],"Demonstrate the exact approved behavior: "+claims[0],"Verify the real result and saved/reloaded state before recording."],
             "captions":[hooks[0],*claims,"Try the demonstrated workflow: "+destination],"sound_off":"Burn in readable captions; keep actual controls visible and avoid rapid or tiny screen text.",
             "limitations":["App job and campaign objective are hypotheses, not measured benefits.","This is a prepared brief. Rendering, publication, spend and audience outcomes remain unexecuted.",*app.get("excluded_claims",[])],
             "cta":"Try the demonstrated workflow","destination":destination,"first_value":app["activation"],"mechanism":{"family":analysis["format_family"],"source_url":frozen["source"]["data"]["url"],"observations":analysis["observations"],"uncertainty":analysis["uncertainty"],"basis":"Operator inspected; source language and footage are not copied"}}
    return content


def channel_copy(channel,app,data,hooks,claims,destination):
    """Keep approved claims exact and reject X overflow instead of cutting sentences."""
    if channel=="X":
        value=app["name"]+": "+claims[0]+"\nTry the demonstrated workflow: "+destination
        if len(value)>280:raise Invalid("Approved claim and destination exceed 280 characters; choose a shorter approved claim")
        return value
    if channel=="LINKEDIN":return hooks[0]+"\n\nFor "+app["audience"]+", this is the workflow we want to test.\n\n"+"\n".join(claims)+"\n\nWatch the actual in-app demonstration, then try it: "+destination
    return "\n".join([hooks[0],"Question to test: "+data["objective"],*claims,"Try the demonstrated workflow: "+destination])


def scene_beats(data,hooks,claims,destination):
    """Declare a four-part original scene plan, not observed competitor timings."""
    quarter=data["duration_seconds"]/4
    lines=[hooks[0],"Question to test: "+data["objective"],"\n".join(claims),"Try the demonstrated workflow: "+destination]
    return [{"start_seconds":i*quarter,"end_seconds":(i+1)*quarter,"script":line,"basis":"ORIGINAL_PROPOSED","scene":["Original presenter or title","Actual question-entry screen","Actual approved app behavior","Actual first-value route and CTA"][i]} for i,line in enumerate(lines)]


def stale_findings(db,store,app_id,data):
    """Recheck selected current proof and scene bytes without altering saved copy."""
    issues=[]
    try:
        current=bind(db,store,app_id,data["definition"])
        if proof_identity(current)!=proof_identity(data):issues.append("Source, app manifest or selected evidence changed after preparation")
    except (Invalid,OSError,KeyError) as exc:issues.append(str(exc) if isinstance(exc,Invalid) else "A required source or asset is unavailable")
    return issues


def proof_identity(data):
    """Ignore restore bookkeeping; compare semantic sources and evidence hashes."""
    return (data["app_hash"],data["analysis"]["hash"],data["source"]["hash"],[(r["id"],r["hash"]) for r in data["records"]],digest(data["content"]),digest(data.get("production")))


class Briefs:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Expose actual content and history with current proof/stale diagnostics."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            items=saved_items(db,"creative_briefs",app_id)
            for item in items:
                item["findings"]=stale_findings(db,self.store,app_id,item["current"]["data"])
                item["evidence_status"]="STALE_EVIDENCE" if item["findings"] else "CURRENT"
            return items

    def save(self,app_id,body):
        """Prepare or revise immutable original briefs against current app proof."""
        self.store.app(app_id)
        if set(body) not in ({"data"},{"id","version","data"}):raise Invalid("Invalid brief save fields")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            data=bind(db,self.store,app_id,body["data"])
            return append(db,"creative_briefs",app_id,data,body)
