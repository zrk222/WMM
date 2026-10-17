"""Predeclared exploratory ranking; supplied relevance is independent of attention."""
import math
from .common import Invalid,amount,canonical,digest,fraction,iso_time,now,required,safe_data
from .db import connection
from .creative_analysis import append,saved_items
from .creative_library import Library,latest_capture
from .creative_attention import attention,freshness
from .production_feasibility import context as production_context,assess

TABLES={"policy":"creative_rank_policies","relevance":"creative_relevance","report":"creative_rank_reports"}
DIMENSIONS=("relevance","attention","freshness","cost")


def bounded_integer(value,name,low,high):
    """Reject boolean ratings and unbounded selection controls."""
    if type(value) is not int or not low<=value<=high:raise Invalid(f"{name}: choose a whole number {low} through {high}")
    return value


def policy_data(data):
    """Freeze explicit proposed weights before applying any ranking."""
    safe_data(data)
    if set(data)!={"mode","weights","max_per_creator","max_per_format","slate_size","holdout_after","rationale"}:raise Invalid("Complete the ranking policy fields")
    if data["mode"] not in ("SIMPLE_RELEVANCE","EXPLORATORY"):raise Invalid("Choose a ranking mode")
    weights=data["weights"]
    if not isinstance(weights,dict) or set(weights)!=set(DIMENSIONS):raise Invalid("Enter all four ranking weights")
    for k in DIMENSIONS:fraction(weights[k],k+" weight")
    policy_weights(data,weights)
    bounded_integer(data["max_per_creator"],"Creator cap",1,3);bounded_integer(data["slate_size"],"Slate size",1,12)
    bounded_integer(data["max_per_format"],"Format cap",1,12)
    if iso_time(data["holdout_after"])>iso_time(now()):raise Invalid("Holdout cutoff cannot be in the future")
    required(data["rationale"],"Policy rationale",2000)
    return data


def policy_weights(data,weights):
    """Reject implicit renormalization and exploration posing as simple relevance."""
    if not math.isclose(sum(weights.values()),1,rel_tol=0,abs_tol=1e-9) or weights["relevance"]<0.5:raise Invalid("Weights must sum to 1; relevance must be at least 0.5")
    if data["mode"]=="SIMPLE_RELEVANCE" and weights!={"relevance":1,"attention":0,"freshness":0,"cost":0}:raise Invalid("Simple relevance uses only relevance weight 1")


def relevance_data(data):
    """Validate a supplied review without extracting psychological or audience claims."""
    safe_data(data)
    if set(data)!={"reference_id","capture_hash","app_hash","job_fit","audience_fit","proof_fit","rationale","cost_minor"}:raise Invalid("Complete the app relevance review fields")
    for key in ("reference_id","capture_hash","app_hash"):required(data[key],key,120)
    for key in ("job_fit","audience_fit","proof_fit"):bounded_integer(data[key],key,0,3)
    required(data["rationale"],"Relevance rationale",2000);amount(data["cost_minor"],"Proposed production cost")
    return data


def current_rows(db,table,app_id):
    """Use immutable latest revisions only, with stable ordering by identity."""
    return sorted([item["current"] for item in saved_items(db,table,app_id)],key=lambda r:r["id"])


def source_pool(sources,reference_ids):
    """Make the chosen denominator explicit and bounded instead of silently sampling."""
    if not isinstance(reference_ids,list) or not 1<=len(reference_ids)<=100:raise Invalid("Select 1 through 100 source posts for this ranking")
    if any(not isinstance(i,str) for i in reference_ids) or len(set(reference_ids))!=len(reference_ids):raise Invalid("Select distinct source IDs")
    mapped={s["id"]:s for s in sources}
    if any(i not in mapped for i in reference_ids):raise Invalid("Selected source does not belong to this app")
    return [{**mapped[i],"captures":mapped[i]["captures"][-2:]} for i in sorted(reference_ids)]


def ranking_inputs(store,app_id,reference_ids):
    """Freeze source snapshots, app manifest and current supplied review versions."""
    app=store.app(app_id)
    sources=Library(store).list(app_id)
    with connection(store.path) as db:
        policies=current_rows(db,TABLES["policy"],app_id)
        reviews=current_rows(db,TABLES["relevance"],app_id)
        production=production_context(db,app_id)
    return bind_inputs(app,sources,policies,reviews,reference_ids,production)


def bind_inputs(app,sources,policies,reviews,reference_ids,production=None):
    """Reuse one current context for report history instead of rereading per report."""
    sources=source_pool(sources,reference_ids)
    if not policies:raise Invalid("Declare your ranking policy before running")
    selected=set(reference_ids)
    inputs={"app":app["data"],"app_hash":digest(app["data"]),"policy":policies[-1],"sources":sources,
            "reviews":[r for r in reviews if r["data"]["reference_id"] in selected]}
    if production is not None:inputs["production"]={"profile":production["profile"],"requirements":[r for r in production["requirements"] if r["data"]["reference_id"] in selected]}
    return inputs


def review_for(inputs,source):
    """Exclude missing or stale reviews, keeping attention independent."""
    rows=[r for r in inputs["reviews"] if r["data"]["reference_id"]==source["id"]]
    if not rows:return None,"App relevance has not been reviewed"
    r=rows[0];d=r["data"]
    if d["app_hash"]!=inputs["app_hash"] or d["capture_hash"]!=source["current"]["hash"]:return None,"App or source changed; correct the relevance review"
    return r,None


def rank_row(inputs,source,evaluated_at):
    """Expose each scoring component and missingness before composing an exploration value."""
    data=source["current"]["data"];review,error=review_for(inputs,source)
    observed=attention(source,inputs["sources"],evaluated_at)
    speed=attention(source,inputs["sources"],evaluated_at,"velocity")
    row={"reference_id":source["id"],"title":data["title"],"creator_id":data["creator_id"],"format":data["format"],
         "attention":observed,"velocity":speed,"eligible":error is None,"exclusion":error,"relevance":None,"components":None,"score":None,
         "partition":partition(data,inputs["policy"]["data"]["holdout_after"])}
    if error:return row
    d=review["data"];fit=sum(d[k] for k in ("job_fit","audience_fit","proof_fit"))/9
    row["relevance"]={"value":fit,"basis":"OPERATOR_SUPPLIED","review_id":review["id"],"review_hash":review["hash"],"rationale":d["rationale"]}
    components={"relevance":fit,"attention":observed["score"] or 0,"freshness":freshness(data,evaluated_at) or 0,"cost":100/(100+d["cost_minor"])}
    weights=inputs["policy"]["data"]["weights"]
    row["components"]=components;row["score"]=sum(components[k]*weights[k] for k in DIMENSIONS)
    return row


def partition(data,cutoff):
    """Temporal source partition is not proof of untouched downstream holdout."""
    if not data["published_at"]:return "UNASSIGNED"
    return "CALIBRATION" if iso_time(data["published_at"])<iso_time(cutoff) else "HOLDOUT"


def select_slate(rows,policy,baseline=False):
    """Apply deterministic creator caps to both exploratory and relevance baselines."""
    eligible=[r for r in rows if r["eligible"]];counts={};formats={};selected=[];excluded=[]
    key=lambda r:(-(r["relevance"]["value"] if baseline else r["score"]),r["reference_id"])
    for row in sorted(eligible,key=key):
        creator=row["creator_id"] or "UNKNOWN";reason=selection_reason(row,policy,counts,formats,selected)
        if reason:
            excluded.append({"reference_id":row["reference_id"],"reason":reason});continue
        selected.append(row["reference_id"]);counts[creator]=counts.get(creator,0)+1;formats[row["format"]]=formats.get(row["format"],0)+1
    return {"selected":selected,"excluded":excluded}


def selection_reason(row,policy,counts,formats,selected):
    """Expose the first declared diversity/cap constraint preventing selection."""
    creator=row["creator_id"] or "UNKNOWN";cap=policy["max_per_creator"] if row["creator_id"] else 1
    if counts.get(creator,0)>=cap:return "Creator diversity cap"
    if formats.get(row["format"],0)>=policy["max_per_format"]:return "Format diversity cap"
    if len(selected)>=policy["slate_size"]:return "Slate size cap"
    return None


def calculate(inputs,evaluated_at):
    """Persist deterministic evidence and an honest not-evaluated baseline comparison."""
    rows=[production_row(inputs,s,rank_row(inputs,s,evaluated_at),evaluated_at) for s in inputs["sources"]]
    if not any(r["eligible"] for r in rows):
        reasons=sorted({r["exclusion"] for r in rows if r["exclusion"]})
        raise Invalid("Review at least one current source for this app before ranking: "+"; ".join(reasons)[:1600])
    policy=inputs["policy"]["data"]
    return {"algorithm":"robust-source-v1","inputs":inputs,"input_hash":digest(inputs),"evaluated_at":evaluated_at,"rows":rows,
            "slate":select_slate(rows,policy),"simple_baseline":select_slate(rows,policy,True),
            "coverage":{"sources":len(rows),"eligible":sum(r["eligible"] for r in rows),"comparable_attention":sum(r["attention"]["score"] is not None for r in rows)},
            "evaluation":"NOT_EVALUATED","outcomes":"NOT_RUN","limits":"Proposed weights; selected-pool coverage only. No calibrated superiority, confidence, competitor ROI or outcome claim."}


def production_row(inputs,source,row,stamp):
    """Historical legacy reports stay reproducible; new inputs enforce capability."""
    if "production" not in inputs:return row
    report=assess(inputs["production"],source,inputs["app_hash"],stamp)
    row["production"]=report
    if report["status"]!="READY":
        row["eligible"]=False;row["exclusion"]="; ".join(filter(None,[row["exclusion"],*report["reasons"]]));row["score"]=None
    return row


class Rankings:
    def __init__(self,store):self.store=store

    def save(self,app_id,kind,body):
        """Version policy and relevance through typed app-scoped forms."""
        app=self.store.app(app_id);safe_data(body)
        if kind not in ("policy","relevance") or set(body) not in ({"data"},{"id","version","data"}):raise Invalid("Invalid ranking save fields")
        data=policy_data(body["data"]) if kind=="policy" else relevance_data(body["data"])
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            old=current_rows(db,TABLES[kind],app_id)
            if kind=="relevance":self.validate_review(db,app_id,app,data)
            identity="reference_id" if kind=="relevance" else None
            matches=old if kind=="policy" else [r for r in old if r["data"]["reference_id"]==data["reference_id"]]
            if matches and "id" not in body:raise Invalid("This review or policy exists; use Correct or Revise")
            return append(db,TABLES[kind],app_id,data,body,identity)

    def validate_review(self,db,app_id,app,data):
        """Require current app and source, so stale relevance cannot inherit new meaning."""
        source=latest_capture(db,app_id,data["reference_id"]);app=self.store.app(app_id)
        if source["hash"]!=data["capture_hash"] or digest(app["data"])!=data["app_hash"]:raise Invalid("App or source changed; reload this review")

    def run(self,app_id,body):
        """Save an immutable report only after policy and eligible evidence exist."""
        safe_data(body)
        if set(body)!={"reference_ids"}:raise Invalid("Choose the source pool for this ranking")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            inputs=ranking_inputs(self.store,app_id,body["reference_ids"]);data=calculate(inputs,now())
            if len(canonical(data).encode())>16777216:raise Invalid("Ranking exceeds 16 MB; choose a smaller pool")
            return append(db,TABLES["report"],app_id,data,{"data":data})

    def list(self,app_id):
        """Retain reports and flag changed inputs without rewriting their original scores."""
        app=self.store.app(app_id)
        with connection(self.store.path) as db:
            items={kind:saved_items(db,table,app_id) for kind,table in TABLES.items()}
            production=production_context(db,app_id)
        sources=Library(self.store).list(app_id);policies=[r["current"] for r in items["policy"]]
        reviews=sorted([r["current"] for r in items["relevance"]],key=lambda r:r["id"]);cache={}
        for item in items["report"]:
            data=item["current"]["data"]
            try:
                ids=tuple(s["id"] for s in data["inputs"]["sources"])
                if ids not in cache:cache[ids]=digest(bind_inputs(app,sources,policies,reviews,list(ids),production))
                item["input_status"]="CURRENT" if cache[ids]==data["input_hash"] else "STALE_INPUTS"
            except Invalid:item["input_status"]="STALE_INPUTS"
        items["app_hash"]=digest(app["data"])
        return items
