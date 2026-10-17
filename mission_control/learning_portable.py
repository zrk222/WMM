"""Hash-validated portable learning history; authenticated authority never transfers."""
import json
from .common import Invalid,canonical,digest,iso_time
from .outcome_links import decoded,cost_rows,source_url
from .learning_contract import declare
from .outcome_learning import find,history,STATES

LINK_KEYS={"app_id","experiment_id","arm","version","data","hash","created"}
PROGRAM_KEYS={"app_id","id","data","hash","state","version","preparer","restored","created","updated","events"}
EVENT_KEYS={"app_id","learning_id","version","data","hash","created"}
BASE_KEYS={"definition","app_hash","training","training_hash","maker_role_version","previous_id"}
FLOW={"reserve":({"PROPOSED"},{"RESERVED"}),"evaluate":({"RESERVED","READY","REJECTED"},{"READY","REJECTED"}),
      "approve":({"READY"},{"APPROVED"}),"activate":({"APPROVED"},{"ACTIVE"}),"supersede":({"ACTIVE"},{"SUPERSEDED"}),
      "restore":({"SUPERSEDED"},{"ACTIVE"}),"rollback":({"ACTIVE"},{"ROLLED_BACK"})}


def collection(value,limit,name):
    """Reject malformed or oversized portable collections before writing."""
    if not isinstance(value,list) or len(value)>limit or any(not isinstance(r,dict) for r in value):raise Invalid("Invalid or oversized learning "+name)
    return value


def exact(row,keys,app_id):
    """Every portable row must carry the exact schema and selected app scope."""
    if set(row)!=keys or row["app_id"]!=app_id:raise Invalid("Learning snapshot schema or app scope mismatch")
    if type(row.get("version",1)) is not int or row.get("version",1)<1:raise Invalid("Invalid learning history version")
    if digest(row["data"])!=row["hash"]:raise Invalid("Learning snapshot hash mismatch")


def export_learning(db,app_id):
    """Preserve history while excluding the live active pointer and authority."""
    links=[decoded(r) for r in db.execute("SELECT * FROM creative_outcome_links WHERE app_id=? ORDER BY experiment_id,arm,version",(app_id,))]
    programs=[]
    for identity in db.execute("SELECT id FROM learning_programs WHERE app_id=? ORDER BY created,id",(app_id,)).fetchall():
        row=find(db,app_id,identity[0]);row["events"]=history(db,row);programs.append(row)
    uses=[dict(r) for r in db.execute("SELECT * FROM learning_brief_uses WHERE app_id=? ORDER BY created,brief_id",(app_id,))]
    for row in uses:row["data"]=json.loads(row["data"])
    roles=[dict(r) for r in db.execute("SELECT * FROM learning_experiment_roles WHERE app_id=? ORDER BY experiment_id",(app_id,))]
    return {"schema":"growth.learning.v1","authority":"NOT_TRANSFERRED","links":links,"programs":programs,"uses":uses,"roles":roles}


def frozen_link(db,app_id,row):
    """Validate historical joins without claiming current source eligibility."""
    exact(row,LINK_KEYS,app_id);data=row["data"]
    fields={"request","app_hash","experiment_hash","variant","brief","costs","production_cost_minor","publication_authenticity","cost_treatment"}
    if set(data)!=fields:raise Invalid("Invalid frozen creative outcome fields")
    request=data["request"]
    from .outcome_links import LINK_FIELDS
    if set(request)!=LINK_FIELDS or request["experiment_id"]!=row["experiment_id"] or request["arm"]!=row["arm"] or row["arm"] not in ("control","treatment"):raise Invalid("Frozen creative link identity mismatch")
    experiment=db.execute("SELECT data,hash FROM experiments WHERE app_id=? AND id=?",(app_id,row["experiment_id"])).fetchone()
    if not experiment or data["experiment_hash"]!=experiment["hash"]:raise Invalid("Frozen outcome experiment is missing")
    variant=json.loads(experiment["data"])[row["arm"]]
    frozen_design(db,app_id,data,request,variant)
    frozen_costs(db,app_id,data,request,variant)


def frozen_design(db,app_id,data,request,variant):
    """Check retained exact brief bytes and the authentic variant selection."""
    brief=data["brief"];stored=db.execute("SELECT hash FROM creative_briefs WHERE app_id=? AND id=? AND version=?",(app_id,brief["id"],brief["version"])).fetchone()
    if data["variant"]!=variant or not stored or brief["hash"]!=stored["hash"] or digest(brief["data"])!=brief["hash"] or brief["id"]!=request["brief_id"]:raise Invalid("Frozen creative design does not match retained history")
    if data["app_hash"]!=brief["data"]["app_hash"] or not any(r["id"]==variant["asset_id"] and r["hash"]==variant["asset_hash"] for r in brief["data"]["records"]):raise Invalid("Frozen brief does not include the selected authentic arm")


def frozen_costs(db,app_id,data,request,variant):
    """Check historical cost allocation and bounded supplied publication."""
    costs=cost_rows(db,app_id,variant["cohort"],request["cost_events"])
    if data["costs"]!=costs or data["production_cost_minor"]!=sum(c["amount_minor"] for c in costs):raise Invalid("Frozen creative cost allocation changed")
    published=iso_time(request["published_at"]);cohort=variant["cohort"]
    if source_url(request["publication_url"])!=request["publication_url"] or not iso_time(cohort["starts_at"])<=published<iso_time(cohort["ends_at"]):raise Invalid("Frozen publication receipt is invalid")
    if data["publication_authenticity"]!="OPERATOR_SUPPLIED" or data["cost_treatment"]!="ALREADY_INCLUDED_IN_DELIVERY_LEDGER":raise Invalid("Frozen source authenticity was overstated")


def frozen_context(db,app_id,context):
    """Require retained exact definition, assessment and creative source rows."""
    experiment=context["experiment"]
    row=db.execute("SELECT hash FROM experiments WHERE app_id=? AND id=?",(app_id,experiment["id"])).fetchone()
    if not row or experiment["app_id"]!=app_id or row[0]!=experiment["hash"] or digest(experiment["data"])!=row[0]:raise Invalid("Learning experiment definition changed")
    stored=db.execute("SELECT data FROM experiment_assessments WHERE app_id=? AND experiment_id=? AND hash=?",(app_id,experiment["id"],context["assessment_hash"])).fetchone()
    if not stored or json.loads(stored[0])!=context["assessment"] or digest(context["assessment"])!=context["assessment_hash"]:raise Invalid("Learning assessment does not match retained experiment history")
    if context["assessment"]["status"]!="EVALUATED":raise Invalid("Learning source lacks an evaluated assessment")
    for arm in ("control","treatment"):frozen_context_link(db,app_id,experiment["id"],arm,context["links"][arm])


def frozen_context_link(db,app_id,experiment_id,arm,link):
    """Resolve the exact retained revision in this experiment arm."""
    saved=db.execute("SELECT hash FROM creative_outcome_links WHERE app_id=? AND experiment_id=? AND arm=? AND version=?",(app_id,experiment_id,arm,link["version"])).fetchone()
    if not saved or saved[0]!=link["hash"] or digest(link["data"])!=link["hash"]:raise Invalid("Learning creative link history changed")


def frozen_data(db,app_id,data,created):
    """Check semantic source identities even when snapshot hashes were recomputed."""
    if not BASE_KEYS<=set(data) or set(data)-BASE_KEYS-{"holdout","evaluation","evaluation_hash","approval","rollback"}:raise Invalid("Invalid learning proposal payload")
    declare(data["definition"]);frozen_context(db,app_id,data["training"])
    if digest(data["training"])!=data["training_hash"] or data["definition"]["training_experiment_id"]!=data["training"]["experiment"]["id"]:raise Invalid("Learning training identity changed")
    if type(data["maker_role_version"]) is not int or data["maker_role_version"]<1:raise Invalid("Invalid historical maker role version")
    if "holdout" in data:frozen_holdout(db,app_id,data,created)
    if "evaluation" in data:frozen_evaluation(db,app_id,data)
    if "approval" in data:frozen_approval(data["approval"])


def frozen_approval(approval):
    """Historical approval is structured evidence and never fresh authority."""
    if set(approval)!={"principal","role_version","reviewed_hash","reviewed_version"} or type(approval["role_version"]) is not int or approval["role_version"]<1:raise Invalid("Invalid historical independent approval")
    if type(approval["reviewed_version"]) is not int or approval["reviewed_version"]<1:raise Invalid("Invalid historical reviewed version")


def frozen_holdout(db,app_id,data,created):
    """Preserve the temporal pre-exposure design declaration."""
    reserved=data["holdout"];experiment=reserved["experiment"]
    if set(reserved)!={"experiment","briefs","reserved_at","pattern_instantiation"} or reserved["pattern_instantiation"]!="OPERATOR_ATTESTED":raise Invalid("Invalid historical holdout declaration")
    saved=db.execute("SELECT hash FROM experiments WHERE app_id=? AND id=?",(app_id,experiment["id"])).fetchone()
    if not saved or experiment["app_id"]!=app_id or saved[0]!=experiment["hash"]:raise Invalid("Historical holdout experiment changed")
    if not iso_time(created)<iso_time(experiment["created"])<=iso_time(reserved["reserved_at"])<iso_time(experiment["data"]["control"]["cohort"]["starts_at"]):raise Invalid("Holdout was not reserved before exposure")
    for arm in ("control","treatment"):frozen_holdout_brief(db,app_id,reserved["briefs"][arm])


def frozen_holdout_brief(db,app_id,brief):
    """A frozen holdout brief must exist byte-for-byte in retained history."""
    row=db.execute("SELECT hash FROM creative_briefs WHERE app_id=? AND id=? AND version=?",(app_id,brief["id"],brief["version"])).fetchone()
    if not row or row[0]!=brief["hash"] or digest(brief["data"])!=brief["hash"]:raise Invalid("Historical holdout design changed")


def frozen_evaluation(db,app_id,data):
    """A rehashed success still needs the declared numeric holdout conditions."""
    result=data["evaluation"]
    if digest(result)!=data.get("evaluation_hash") or result.get("outcome") not in ("READY","REJECTED"):raise Invalid("Learning evaluation hash or outcome mismatch")
    if result["outcome"]!="READY":
        if not result.get("issues"):raise Invalid("Rejected learning needs its actual reason")
        return
    frozen_context(db,app_id,result["holdout"])
    if digest(result["holdout"])!=result["holdout_hash"] or result["training_hash"]!=data["training_hash"] or result["issues"]:raise Invalid("Learning evaluation source mismatch")
    if result["holdout"]["experiment"]["id"]!=data["holdout"]["experiment"]["id"]:raise Invalid("Learning evaluated a different holdout")
    frozen_numeric(data,result)


def frozen_numeric(data,result):
    """Require the exact declared effect and contribution conditions."""
    effect=result["holdout"]["assessment"]["effect"];reports=result["holdout"]["assessment"]["reports"]
    values={arm:reports[arm]["contribution_after_acquisition_minor"]/reports[arm]["installs"] for arm in ("control","treatment")}
    if effect["interval"][0]<data["definition"]["minimum_holdout_difference"] or values["treatment"]<values["control"] or values!=result["contribution_per_install"]:raise Invalid("Learning passed without its predeclared outcome and contribution conditions")


def restore_links(db,app_id,rows):
    """Replay contiguous immutable joins before restoring learning references."""
    versions={}
    for row in collection(rows,5000,"links"):
        frozen_link(db,app_id,row);key=(row["experiment_id"],row["arm"]);expected=versions.get(key,0)+1
        if row["version"]!=expected:raise Invalid("Outcome link versions are missing or duplicated")
        versions[key]=expected
        db.execute("INSERT INTO creative_outcome_links VALUES(?,?,?,?,?,?,?)",(app_id,*key,row["version"],canonical(row["data"]),row["hash"],row["created"]))
    if len(versions)>1000:raise Invalid("Too many outcome link identities")


def restore_program(db,app_id,row):
    """Replay allowed transitions; retain signed-in names only as untrusted history."""
    exact(row,PROGRAM_KEYS,app_id);events=collection(row["events"],5000,"events")
    if [e.get("version") for e in events]!=list(range(1,row["version"]+1)):raise Invalid("Learning transition versions are missing or duplicated")
    previous=None;state=None;stamp=None
    for event in events:
        value=restore_event(event,app_id,row,stamp)
        replay_edge(previous,state,value)
        frozen_data(db,app_id,value["data"],row["created"])
        previous=value;state=value["state"];stamp=event["created"]
        db.execute("INSERT INTO learning_events VALUES(?,?,?,?,?,?)",(app_id,row["id"],event["version"],canonical(value),event["hash"],event["created"]))
    if not previous or state!=row["state"] or previous["data"]!=row["data"] or stamp!=row["updated"]:raise Invalid("Learning final state disagrees with history")
    db.execute("INSERT INTO learning_programs VALUES(?,?,?,?,?,?,?,?,?,?)",(app_id,row["id"],canonical(row["data"]),row["hash"],state,row["version"],row["preparer"],1,row["created"],row["updated"]))


def replay_edge(previous,state,value):
    """Check the initial declaration or a permitted subsequent transition."""
    if previous is not None:return validate_transition(previous,state,value)
    if value["operation"]!="propose" or value["state"]!="PROPOSED" or value["previous_hash"] is not None:raise Invalid("Learning history must start with its actual proposal")


def restore_event(event,app_id,row,stamp):
    """Validate each exact receipt before replaying its lifecycle edge."""
    exact(event,EVENT_KEYS,app_id)
    if event["learning_id"]!=row["id"]:raise Invalid("Learning transition belongs to another proposal")
    value=event["data"]
    if set(value)!={"operation","actor","previous_hash","state","data","created"} or value["created"]!=event["created"]:raise Invalid("Invalid learning transition receipt")
    if stamp and iso_time(event["created"])<iso_time(stamp):raise Invalid("Learning transition timestamp order changed")
    if value["operation"]=="approve" and value["actor"]==row["preparer"]:raise Invalid("Historical approval was not independent")
    return value


def validate_transition(previous,state,value):
    """Replay only declared lifecycle edges and preserve frozen source identity."""
    operation=value["operation"];allowed=FLOW.get(operation)
    if not allowed or state not in allowed[0] or value["state"] not in allowed[1] or value["previous_hash"]!=digest(previous["data"]):raise Invalid("Invalid learning transition or prior hash")
    if any(previous["data"][k]!=value["data"][k] for k in BASE_KEYS):raise Invalid("A learning transition rewrote its frozen proposal")
    if "holdout" in previous["data"] and value["data"].get("holdout")!=previous["data"]["holdout"]:raise Invalid("A learning transition changed its reserved holdout")
    validate_decision(previous,value)


def validate_decision(previous,value):
    """Evaluation and approval cannot rewrite or mislabel their inspected result."""
    operation=value["operation"]
    if operation=="evaluate" and value["state"]!=value["data"]["evaluation"]["outcome"]:raise Invalid("Learning state disagrees with evaluated result")
    if operation=="approve" and value["data"]["approval"]["reviewed_hash"]!=digest(previous["data"]):raise Invalid("Approval did not inspect the exact evaluated payload")


def restore_roles(db,app_id,rows,programs):
    """Preserve used experiment partitions; they confer no membership authority."""
    by_id={p["id"]:p for p in programs}
    for row in collection(rows,1000,"partitions"):
        if set(row)!={"app_id","experiment_id","role","learning_id"} or row["app_id"]!=app_id or row["learning_id"] not in by_id:raise Invalid("Invalid learning experiment partition")
        data=by_id[row["learning_id"]]["data"]
        expected=partition_id(data,row["role"])
        if expected!=row["experiment_id"]:raise Invalid("Learning experiment partition changed")
        db.execute("INSERT INTO learning_experiment_roles VALUES(?,?,?,?)",(app_id,row["experiment_id"],row["role"],row["learning_id"]))
    partitions_complete(rows,programs)


def partition_id(data,role):
    """Resolve the single allowed experiment identity for a partition role."""
    if role=="TRAIN":return data["definition"]["training_experiment_id"]
    if role=="HOLDOUT":return data.get("holdout",{}).get("experiment",{}).get("id")
    raise Invalid("Unknown learning partition")


def partitions_complete(rows,programs):
    """Each retained proposal must retain its training and holdout exclusion."""
    actual={r["experiment_id"]:r["role"] for r in rows}
    for program in programs:
        data=program["data"]
        if actual.get(data["definition"]["training_experiment_id"])!="TRAIN":raise Invalid("Training partition missing")
        if "holdout" in data and actual.get(data["holdout"]["experiment"]["id"])!="HOLDOUT":raise Invalid("Holdout partition missing")


def restore_uses(db,app_id,rows,programs):
    """Retain exact brief/use evidence without enabling imported influence."""
    by_id={p["id"]:p for p in programs}
    for row in collection(rows,1000,"brief uses"):
        exact(row,{"app_id","brief_id","learning_id","data","hash","created"},app_id);data=row["data"]
        program=by_id.get(row["learning_id"]);brief=db.execute("SELECT hash,data FROM creative_briefs WHERE app_id=? AND id=? ORDER BY version",(app_id,row["brief_id"])).fetchall()
        states=program["events"] if program else []
        matching=[e["data"]["data"] for e in states if e["data"]["state"]=="ACTIVE" and digest(e["data"]["data"])==data.get("learning_hash")]
        if not matching or data.get("learning_id")!=row["learning_id"] or data.get("brief_id")!=row["brief_id"] or data.get("evaluation_hash")!=matching[0]["evaluation_hash"]:raise Invalid("Learning use does not match approved historical influence")
        matched=[r for r in brief if r["hash"]==data.get("brief_hash")]
        if not matched or "Creative method to test: "+matching[0]["definition"]["pattern"] not in json.loads(matched[0]["data"])["definition"]["objective"]:raise Invalid("Learning use brief changed")
        db.execute("INSERT INTO learning_brief_uses VALUES(?,?,?,?,?,?)",(app_id,row["brief_id"],row["learning_id"],canonical(data),row["hash"],row["created"]))


def restore_learning(db,app_id,payload):
    """Restore all validated history in the outer atomic workspace transaction."""
    if payload is None:return
    if set(payload)!={"schema","authority","links","programs","uses","roles"} or payload["schema"]!="growth.learning.v1" or payload["authority"]!="NOT_TRANSFERRED":raise Invalid("Invalid portable learning history")
    programs=collection(payload["programs"],1000,"programs")
    if sum(len(p.get("events",[])) for p in programs)>5000:raise Invalid("Too many learning history events")
    restore_links(db,app_id,payload["links"])
    for program in programs:restore_program(db,app_id,program)
    restore_roles(db,app_id,payload["roles"],programs);restore_uses(db,app_id,payload["uses"],programs)
