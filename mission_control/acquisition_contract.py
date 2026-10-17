"""Source-bound acquisition hypotheses and predeclared observation contracts."""
import json
from .common import Invalid,digest,iso_time,now,required,safe_data
from .creative_analysis import latest
from .creative_library import latest_capture,source_url
from .creative_briefs import bound_record,latest_proof,critical_findings,stale_findings

INTENT_FIELDS={"owner","problem","asa_seed","aeo_question","territory","native_reviewer","analysis_id","analysis_hash","claim_id","readiness_id","route_id","store_id","brief_id","page_url"}
PANEL_FIELDS={"intent_id","intent_hash","owner","engine","surface","search_mode","model","account_context","geography","repetitions","rubric","queries"}
OBS_FIELDS={"panel_id","panel_hash","query_id","repetition","observed_at","status","raw_response","source_ref","reviewer","mention","citation_url","correct_citation","misinformation","review_note"}


def exact(data,fields):
    """Reject unknown fields and private payloads before resolving evidence."""
    safe_data(data)
    if set(data)!=fields:raise Invalid("Complete the declared acquisition fields without extra columns")
    return dict(data)


def whole(value,name,low,high):
    """Reject ambiguous integer controls, including booleans."""
    if type(value) is not int or not low<=value<=high:raise Invalid(f"{name}: enter a whole number from {low} through {high}")
    return value


def intent_definition(data):
    """Normalize explicit reviewed intent, without extracting claims from research."""
    result=exact(data,INTENT_FIELDS)
    for key in INTENT_FIELDS-{"store_id","brief_id"}:result[key]=required(data[key],key,2000)
    for key in ("store_id","brief_id"):
        if data[key] is not None:result[key]=required(data[key],key,120)
    source_url(data["page_url"])
    if len(result["territory"])!=2 or not result["territory"].isalpha() or not result["territory"].isupper():raise Invalid("Territory: use the two-letter uppercase country code")
    return result


def bind_intent(db,store,app_id,data):
    """Freeze current app, inspected source and actual product proof identities."""
    definition=intent_definition(data)
    app=json.loads(db.execute("SELECT data FROM apps WHERE id=?",(app_id,)).fetchone()[0])
    analysis=latest(db,"creative_analyses",app_id,data["analysis_id"])
    source=latest_capture(db,app_id,analysis["data"]["reference_id"])
    if analysis["hash"]!=data["analysis_hash"] or source["hash"]!=analysis["data"]["capture_hash"]:raise Invalid("Inspect the current source before mapping its intent")
    records=[]
    for kind in ("claim","readiness","route","store"):
        if kind=="store" and data["store_id"] is None:continue
        record=bound_record(db,app_id,data[kind+"_id"],kind,app);latest_proof(db,app_id,record,app)
        records.append({key:record[key] for key in ("app_id","id","kind","data","source","hash")})
    critical_findings(db,app_id)
    brief=bind_brief(db,store,app_id,data,analysis)
    return {"definition":definition,"app":app,"app_hash":digest(app),"analysis":analysis,"source":source,"records":records,"brief":brief,
            "locale":app["locale"],"first_value":app["activation"],"asa_status":"PREPARED" if data["store_id"] else "BLOCKED_STORE",
            "demand":"UNKNOWN","crawl_index":"NOT_RUN","publication":"NOT_RUN"}


def bind_brief(db,store,app_id,data,analysis):
    """Link only a current brief from the same inspected source and app."""
    if data["brief_id"] is None:return None
    brief=latest(db,"creative_briefs",app_id,data["brief_id"])
    if brief["data"]["analysis"]["id"]!=analysis["id"] or stale_findings(db,store,app_id,brief["data"]):raise Invalid("Choose a current creative brief from this source inspection")
    return {"id":brief["id"],"hash":brief["hash"]}


def intent_status(db,store,app_id,row):
    """Changes remain visible rather than silently updating frozen hypotheses."""
    try:return "CURRENT" if bind_intent(db,store,app_id,row["data"]["definition"])==row["data"] else "STALE_EVIDENCE"
    except (Invalid,KeyError,OSError):return "STALE_EVIDENCE"


def queries_data(rows):
    """Require explicit distinct queries with calibration and holdout partitions."""
    if not isinstance(rows,list) or not 2<=len(rows)<=20:raise Invalid("Declare 2 through 20 queries, including calibration and holdout")
    result=[]
    for row in rows:
        row=exact(row,{"id","text","partition"})
        row["id"]=required(row["id"],"Query ID",120);row["text"]=required(row["text"],"Query",2000)
        if row["partition"] not in ("CALIBRATION","HOLDOUT"):raise Invalid("Choose calibration or holdout")
        result.append(row)
    if len({r["id"] for r in result})!=len(result) or len({r["text"].casefold() for r in result})!=len(result):raise Invalid("Panel query IDs and texts must be distinct")
    if {r["partition"] for r in result}!={"CALIBRATION","HOLDOUT"}:raise Invalid("Declare both calibration and holdout queries")
    return result


def panel_definition(data,intent):
    """Freeze actual test conditions; API measurements cannot become consumer UI proof."""
    result=exact(data,PANEL_FIELDS)
    for key in PANEL_FIELDS-{"queries","repetitions"}:result[key]=required(data[key],key,2000)
    if data["intent_id"]!=intent["id"] or data["intent_hash"]!=intent["hash"]:raise Invalid("Intent changed; reload before declaring a panel")
    if data["surface"] not in ("API","CONSUMER_UI"):raise Invalid("Choose API or consumer interface")
    result["repetitions"]=whole(data["repetitions"],"Repetitions",1,5)
    result["queries"]=queries_data(data["queries"])
    return result


def observation_definition(data,panel,created):
    """Bind each reviewed answer or failed attempt to an immutable predeclared slot."""
    result=exact(data,OBS_FIELDS);p=panel["data"]["definition"]
    if data["panel_id"]!=panel["id"] or data["panel_hash"]!=panel["hash"]:raise Invalid("Panel changed or does not belong to this observation")
    if data["query_id"] not in [q["id"] for q in p["queries"]]:raise Invalid("Query is not in the declared panel")
    whole(data["repetition"],"Repetition",1,p["repetitions"])
    observed=iso_time(data["observed_at"])
    if not iso_time(created)<=observed<=iso_time(now()):raise Invalid("Observation must follow panel declaration and cannot be in the future")
    for key,limit in (("raw_response",20000),("source_ref",2000),("reviewer",120),("review_note",2000)):result[key]=required(data[key],key,limit)
    result["observed_at"]=observed.isoformat()
    answer_outcomes(result)
    return result


def answer_outcomes(data):
    """Preserve errors and unreviewed citations, and reject impossible outcomes."""
    if data["status"]=="ERROR":
        failed_outcomes(data)
        return
    if data["status"]!="OK":raise Invalid("Choose a successful answer or failed attempt")
    if type(data["mention"]) is not bool or type(data["misinformation"]) is not bool:raise Invalid("Review mentions and misinformation explicitly")
    if data["correct_citation"] is not None and type(data["correct_citation"]) is not bool:raise Invalid("Citation correctness must be yes, no or unreviewed")
    if data["citation_url"] is not None:source_url(data["citation_url"])
    if data["correct_citation"] is not None and data["citation_url"] is None:raise Invalid("Citation correctness requires an actual citation URL")


def failed_outcomes(data):
    """Failures carry errors only, never guessed answer outcomes."""
    if any(data[k] is not None for k in ("mention","citation_url","correct_citation","misinformation")):raise Invalid("A failed attempt cannot contain answer outcomes")
