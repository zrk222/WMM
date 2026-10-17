"""Immutable app-scoped experiment definitions and append-only outcome decisions."""
import json
import hashlib
import re
from .common import Invalid, canonical, digest, iso_time, now, required, safe_data, uid
from .db import connection
from .ledger import opaque, report, eligible_events, funnel_counts, cohort_data
from .experiment_analysis import METRICS, sample_plan, guardrail_data, analyze
from .automation_policy import check_manifest_version

STATES={"PLANNED","OBSERVING","EVALUATED","DECIDED","CANCELLED"}


def definition_data(data):
    """Normalize exact pre-registration fields before binding existing evidence."""
    fields={"name","hypothesis","owner","primary_metric","baseline_rate","minimum_detectable_effect","treatment_allocation","analysis_at",
            "assignment_method","assignment_source","guardrails","stop_rule","rollback_plan","control","treatment"}
    safe_data(data)
    if set(data)!=fields:raise Invalid("Complete the experiment setup fields; extra columns are not accepted")
    result=dict(data)
    for field in ("name","hypothesis","owner","assignment_source","stop_rule","rollback_plan"):
        result[field]=required(data[field],field.replace("_"," "),2000)
    if data["primary_metric"] not in METRICS:raise Invalid("Choose activation, paid conversion or retained-value rate")
    if data["assignment_method"] not in ("RANDOMIZED","OBSERVATIONAL"):raise Invalid("Choose supplied randomized assignment or observational comparison")
    result["analysis_at"]=iso_time(data["analysis_at"]).isoformat()
    result["guardrails"]=guardrail_data(data["guardrails"])
    result["sample_plan"]=sample_plan(data["baseline_rate"],data["minimum_detectable_effect"],data["treatment_allocation"])
    return result


def bind_variant(db,app_id,variant):
    """Freeze current authentic asset and cohort hashes inside the selected app."""
    if not isinstance(variant,dict) or set(variant)!={"cohort_id","asset_id"}:raise Invalid("Each variant needs a cohort and creative asset")
    cohort_id=opaque(variant["cohort_id"],"Cohort ID")
    cohort=db.execute("SELECT * FROM growth_cohorts WHERE app_id=? AND id=?",(app_id,cohort_id)).fetchone()
    asset=db.execute("SELECT * FROM records WHERE app_id=? AND id=? AND kind='asset'",(app_id,variant["asset_id"])).fetchone()
    if not cohort or not asset:raise Invalid("Choose a cohort and creative asset from this app")
    c=json.loads(cohort["data"]);a=json.loads(asset["data"])
    if not a.get("authentic") or not a.get("rights_cleared") or a.get("release")!=c["release"]:
        raise Invalid("Creative asset needs authentic, rights-cleared proof for the cohort release")
    return {"cohort_id":cohort_id,"cohort_hash":cohort["hash"],"cohort":c,"asset_id":asset["id"],"asset_hash":asset["hash"],"creative_sha256":a["sha256"]}


def bind_definition(db,app_id,data,registered_at):
    """Require comparable arms and freeze before any acquisition exposure starts."""
    result=definition_data(data)
    for arm in ("control","treatment"):result[arm]=bind_variant(db,app_id,data[arm])
    c=result["control"]["cohort"];t=result["treatment"]["cohort"]
    fields=("release","platform","locale","currency","starts_at","ends_at","matures_at")
    if c["cohort_id"]==t["cohort_id"] or any(c[k]!=t[k] for k in fields):raise Invalid("Choose two different cohorts with identical release, locale and windows")
    if c["observability"]!="OBSERVED" or t["observability"]!="OBSERVED":raise Invalid("Both arms need observable denominators")
    if iso_time(registered_at)>=iso_time(c["starts_at"]):raise Invalid("Pre-register before acquisition starts; historical tests cannot be labeled preregistered")
    if iso_time(result["analysis_at"])<iso_time(c["matures_at"]):raise Invalid("Analysis must follow the complete maturity window")
    app=json.loads(db.execute("SELECT data FROM apps WHERE id=?",(app_id,)).fetchone()[0])
    if app.get("release")!=c["release"]:raise Invalid("Experiment cohort must match the current app release")
    return result


def decoded(row):
    """Decode durable structured rows without changing their version or hashes."""
    result=dict(row);result["data"]=json.loads(result["data"])
    return result


def lookup(db,app_id,experiment_id):
    """Resolve exact scoped experiment; another app can never open or mutate it."""
    row=db.execute("SELECT * FROM experiments WHERE app_id=? AND id=?",(app_id,experiment_id)).fetchone()
    if not row:raise Invalid("Experiment does not belong to this workspace")
    return decoded(row)


def evidence_reports(db,app_id,definition,as_of):
    """Read both immutable cohorts and events in one consistent transaction."""
    reports={};subjects={}
    for arm in ("control","treatment"):
        variant=definition[arm];cohort=variant["cohort"]
        events=[json.loads(r[0]) for r in db.execute("SELECT data FROM growth_events WHERE app_id=? AND cohort_id=?",(app_id,variant["cohort_id"]))]
        reports[arm]=report(cohort,events,iso_time(as_of));reports[arm].pop("as_of",None)
        cutoff=iso_time(definition["analysis_at"])
        fixed=[e for e in events if iso_time(e["occurred_at"])<=cutoff]
        counts=funnel_counts(fixed,iso_time(cohort["starts_at"]),iso_time(cohort["ends_at"]),iso_time(cohort["matures_at"]))
        reports[arm].update(counts)
        for metric,key in METRICS.items():
            reports[arm][metric]=counts[key]/counts["installs"] if counts["installs"] else None
        reports[arm]["outcome_cutoff"]=definition["analysis_at"]
        reports[arm]["paid_cac_minor"]=reports[arm]["acquisition_cost_minor"]/counts["paid"] if counts["paid"] and reports[arm]["status"]=="SUPPLIED_RECONCILED" else None
        installers,_=eligible_events(events,iso_time(cohort["starts_at"]),iso_time(cohort["ends_at"]))
        subjects[arm]=set(installers)
    return reports,len(subjects["control"]&subjects["treatment"])


def quality_findings(db,app_id,definition,folder):
    """Changed release, creative versions and current confirmed P0 block comparison."""
    issues=[]
    app=json.loads(db.execute("SELECT data FROM apps WHERE id=?",(app_id,)).fetchone()[0])
    if app.get("release")!=definition["control"]["cohort"]["release"]:issues.append("App release changed after registration")
    for arm in ("control","treatment"):
        row=db.execute("SELECT hash,data FROM records WHERE app_id=? AND id=?",(app_id,definition[arm]["asset_id"])).fetchone()
        if not row or row["hash"]!=definition[arm]["asset_hash"]:issues.append(arm+" creative evidence changed after registration")
        elif not asset_intact(folder,json.loads(row["data"])):issues.append(arm+" creative file is missing or changed")
    rows=db.execute("SELECT data FROM records WHERE app_id=? AND kind='review'",(app_id,))
    for row in rows:
        finding=json.loads(row[0])
        if finding.get("confirmed") is True and finding.get("severity")=="P0":issues.append("Confirmed critical product finding requires repair")
    return issues


def asset_intact(folder,data):
    """Verify bounded local file identifiers and current bytes, not metadata alone."""
    file_id=data.get("file_id","")
    if not re.fullmatch(r"[a-f0-9-]+\.(?:png|jpg|jpeg)",file_id):return False
    path=folder/file_id
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==data.get("sha256")


class Experiments:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Return exact saved definitions, assessments and decision freshness."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN")
            rows=[decoded(r) for r in db.execute("SELECT * FROM experiments WHERE app_id=? ORDER BY created DESC,id",(app_id,))]
            for row in rows:
                row["assessments"]=[decoded(r) for r in db.execute("SELECT * FROM experiment_assessments WHERE app_id=? AND experiment_id=? ORDER BY version",(app_id,row["id"]))]
                row["actions"]=[decoded(r) for r in db.execute("SELECT * FROM experiment_actions WHERE app_id=? AND experiment_id=? ORDER BY id",(app_id,row["id"]))]
                decisions=[a for a in row["actions"] if a["data"]["operation"]=="decide"]
                row["decision_status"]="STALE_ASSESSMENT" if decisions and row["assessments"] and decisions[-1]["data"]["assessment_hash"]!=row["assessments"][-1]["hash"] else "CURRENT" if decisions else "NOT_RECORDED"
        return rows

    def create(self,app_id,body):
        """Freeze the complete immutable test plan in an app-scoped transaction."""
        self.store.app(app_id);stamp=now();experiment_id=uid()
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            plan = dict(body)
            check_manifest_version(db, app_id, plan.pop("manifest_version", None))
            data=bind_definition(db,app_id,plan,stamp)
            issues=quality_findings(db,app_id,data,self.store.path.parent/"files"/app_id)
            if issues:raise Invalid("; ".join(issues))
            db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",(app_id,experiment_id,canonical(data),digest(data),"PLANNED",1,stamp,stamp))
            self.audit(db,app_id,experiment_id,"registered",digest(data))
        return next(e for e in self.list(app_id) if e["id"]==experiment_id)

    def audit(self,db,app_id,experiment_id,operation,source_hash):
        """Append only compact public lifecycle evidence to the audit trail."""
        db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,"experiment."+operation,canonical({"id":experiment_id,"source_hash":source_hash}),now()))

    def act(self,app_id,experiment_id,body):
        """Apply versioned, idempotent local actions; never claim external execution."""
        self.store.app(app_id);safe_data(body)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current=lookup(db,app_id,experiment_id)
            action_hash=digest(body)
            old=db.execute("SELECT hash FROM experiment_actions WHERE app_id=? AND experiment_id=? AND hash=?",(app_id,experiment_id,action_hash)).fetchone()
            if old:return {"status":"ALREADY_RECORDED","version":current["version"]}
            if type(body.get("version")) is not int or body["version"]!=current["version"]:raise Invalid("Experiment changed; reload before recording an action")
            if body.get("operation")=="observe":
                issues=quality_findings(db,app_id,current["data"],self.store.path.parent/"files"/app_id)
                if issues:raise Invalid("; ".join(issues))
            state=action_state(db,current,body)
            db.execute("INSERT INTO experiment_actions(app_id,experiment_id,hash,data,created) VALUES(?,?,?,?,?)",(app_id,experiment_id,action_hash,canonical(body),now()))
            db.execute("UPDATE experiments SET state=?,version=version+1,updated=? WHERE app_id=? AND id=?",(state,now(),app_id,experiment_id))
            if state=="CANCELLED":
                from .experiment_schedules import disable
                schedule=db.execute("SELECT * FROM experiment_schedules WHERE app_id=? AND experiment_id=?",(app_id,experiment_id)).fetchone()
                if schedule:disable(db,schedule,"CANCELLED")
            self.audit(db,app_id,experiment_id,body["operation"],action_hash)
        return {"status":state,"external_execution":"NOT_RUN"}

    def evaluate(self,app_id,experiment_id,scheduled=None):
        """Wait for fixed date; append current semantic assessment only when changed."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current=lookup(db,app_id,experiment_id);definition=current["data"]
            if scheduled is not None:
                from .experiment_schedules import check_scheduled
                check_scheduled(db,current,scheduled)
            if current["state"] in ("PLANNED","CANCELLED"):raise Invalid("Record observed exposure before evaluation; cancelled tests cannot run")
            if iso_time(now())<iso_time(definition["analysis_at"]):return {"status":"AWAITING_ANALYSIS","analysis_at":definition["analysis_at"],"effect":None}
            reports,overlap=evidence_reports(db,app_id,definition,now())
            result=analyze(definition,reports,overlap,quality_findings(db,app_id,definition,self.store.path.parent/"files"/app_id))
            result["definition_hash"]=current["hash"]
            result_hash=digest(result)
            latest=db.execute("SELECT hash FROM experiment_assessments WHERE app_id=? AND experiment_id=? ORDER BY version DESC LIMIT 1",(app_id,experiment_id)).fetchone()
            inserted=not latest or latest["hash"]!=result_hash
            if inserted:
                db.execute("INSERT INTO experiment_assessments VALUES(?,?,?,?,?,?)",(app_id,experiment_id,result_hash,canonical(result),now(),current["version"]+1))
                db.execute("UPDATE experiments SET state='EVALUATED',version=version+1,updated=? WHERE app_id=? AND id=?",(now(),app_id,experiment_id))
                self.audit(db,app_id,experiment_id,"evaluated",result_hash)
            return {"hash":result_hash,"result":result,"new_assessment":bool(inserted)}


def action_state(db,current,body):
    """Validate exact lifecycle operations and permitted transition receipts."""
    operation=body.get("operation")
    if current["state"]=="CANCELLED":raise Invalid("This test is cancelled; register a new experiment")
    if operation=="observe":return observe_state(current,body)
    if operation=="decide":return decide_state(db,current,body)
    if operation=="cancel":
        if set(body)!={"operation","version","reason"}:raise Invalid("Cancellation needs version and reason")
        required(body["reason"],"Cancellation reason",2000);return "CANCELLED"
    if operation=="rollback":
        if current["state"]!="DECIDED" or set(body)!={"operation","version","target","source","reason"}:raise Invalid("Record a decision before its proposed rollback")
        for key in ("target","source","reason"):required(body[key],key,2000)
        return "DECIDED"
    raise Invalid("Choose observe, decide, cancel or record proposed rollback")


def observe_state(current,body):
    """Require operator exposure evidence; no launch or provider verification implied."""
    if current["state"]!="PLANNED" or set(body)!={"operation","version","source","observed_at"}:raise Invalid("Record first exposure once, with its actual source and timestamp")
    required(body["source"],"Exposure receipt",2000)
    observed=iso_time(body["observed_at"]);window=current["data"]["control"]["cohort"]
    if not iso_time(window["starts_at"])<=observed<iso_time(window["ends_at"]) or observed>iso_time(now()):raise Invalid("Observed exposure must be within the acquisition window and not future")
    return "OBSERVING"


def decide_state(db,current,body):
    """Bind a reasoned decision to the latest assessment without authorizing scale."""
    if current["state"] not in ("EVALUATED","DECIDED") or set(body)!={"operation","version","assessment_hash","decision","reason"}:raise Invalid("Evaluate this test before recording a decision")
    latest=db.execute("SELECT * FROM experiment_assessments WHERE app_id=? AND experiment_id=? ORDER BY version DESC LIMIT 1",(current["app_id"],current["id"])).fetchone()
    if not latest or latest["hash"]!=body["assessment_hash"]:raise Invalid("Assessment changed; inspect its latest result before deciding")
    if body["decision"] not in ("COLLECT","REPAIR","STOP","NEXT_TEST"):raise Invalid("Choose collect, repair, stop or next bounded test")
    if body["decision"]=="NEXT_TEST" and json.loads(latest["data"])["status"]!="EVALUATED":raise Invalid("Resolve missing evidence and guardrails before proposing the next test")
    required(body["reason"],"Decision reason",2000)
    return "DECIDED"


def snapshot_data(items):
    """Bound restored lifecycle collections before opening a write transaction."""
    if not isinstance(items,list) or len(items)>1000:raise Invalid("Snapshot has too many experiments")
    if any(not isinstance(e,dict) for e in items):raise Invalid("Invalid experiment snapshot")
    for field in ("assessments","actions"):
        groups=[e.get(field) for e in items]
        if any(not isinstance(g,list) for g in groups) or sum(len(g) for g in groups)>5000:raise Invalid("Invalid or oversized experiment history")
    return items


def validate_frozen(db,app_id,row):
    """Validate historical immutable definitions without imposing today's release."""
    if set(row)!={"app_id","id","data","hash","state","version","created","updated","assessments","actions"} or row["app_id"]!=app_id:
        raise Invalid("Experiment snapshot has invalid fields or app scope")
    opaque(row["id"],"Experiment ID")
    if row["state"] not in STATES or type(row["version"]) is not int or row["version"]<1:raise Invalid("Invalid experiment state or version")
    data=row["data"];base=dict(data);base.pop("sample_plan",None)
    for arm in ("control","treatment"):
        variant=data[arm]
        validate_frozen_variant(db,app_id,variant)
        base[arm]={"cohort_id":variant["cohort_id"],"asset_id":variant["asset_id"]}
    normalized=definition_data(base)
    normalized.update({arm:data[arm] for arm in ("control","treatment")})
    if digest(normalized)!=row["hash"] or digest(data)!=row["hash"]:raise Invalid("Experiment definition hash mismatch")
    validate_frozen_windows(row)


def validate_frozen_variant(db,app_id,variant):
    """Require exact historical source references inside this restored workspace."""
    if set(variant)!={"cohort_id","cohort_hash","cohort","asset_id","asset_hash","creative_sha256"}:raise Invalid("Invalid frozen variant")
    cohort=cohort_data(variant["cohort"])
    stored=db.execute("SELECT hash FROM growth_cohorts WHERE app_id=? AND id=?",(app_id,variant["cohort_id"])).fetchone()
    if not stored or stored[0]!=digest(cohort) or variant["cohort_hash"]!=stored[0] or cohort["cohort_id"]!=variant["cohort_id"]:
        raise Invalid("Frozen cohort does not match restored source")
    if not db.execute("SELECT id FROM records WHERE app_id=? AND id=? AND kind='asset'",(app_id,variant["asset_id"])).fetchone():raise Invalid("Frozen creative source is absent")
    for key in ("asset_hash","creative_sha256"):
        if not re.fullmatch("[a-f0-9]{64}",str(variant[key])):raise Invalid("Invalid frozen source hash")


def validate_frozen_windows(row):
    """Preserve preregistration and comparable windows across portable restore."""
    d=row["data"];c=d["control"]["cohort"];t=d["treatment"]["cohort"]
    fields=("release","platform","locale","currency","starts_at","ends_at","matures_at")
    if c["cohort_id"]==t["cohort_id"] or any(c[k]!=t[k] for k in fields):raise Invalid("Snapshot arms are not comparable")
    if c["observability"]!="OBSERVED" or t["observability"]!="OBSERVED":raise Invalid("Snapshot arms lack observed denominators")
    if iso_time(row["created"])>=iso_time(c["starts_at"]) or iso_time(d["analysis_at"])<iso_time(c["matures_at"]):raise Invalid("Invalid preregistration or analysis window")
    if iso_time(row["updated"])<iso_time(row["created"]):raise Invalid("Invalid experiment history timestamps")


def restore_experiments(db,app_id,items):
    """Restore scope and transition-validated history in the workspace transaction."""
    if items is None:return
    for row in snapshot_data(items):
        validate_frozen(db,app_id,row)
        db.execute("INSERT INTO experiments VALUES(?,?,?,?,?,?,?,?)",(app_id,row["id"],canonical(row["data"]),row["hash"],"PLANNED",1,row["created"],row["created"]))
        restore_history(db,app_id,row)


def restore_history(db,app_id,row):
    """Replay an unambiguous contiguous version history; hashes are not signatures."""
    transitions=[]
    for assessment in row["assessments"]:
        transitions.append((assessment.get("version"),"assessment",assessment))
    for action in row["actions"]:
        transitions.append((action.get("data",{}).get("version",0)+1,"action",action))
    if any(type(t[0]) is not int for t in transitions):raise Invalid("Invalid history version")
    transitions.sort(key=lambda t:t[0])
    if [t[0] for t in transitions]!=list(range(2,row["version"]+1)):raise Invalid("History versions are missing or duplicated")
    state="PLANNED";previous=row["created"]
    for version,kind,item in transitions:
        if iso_time(item["created"])<iso_time(previous) or iso_time(item["created"])>iso_time(row["updated"]):raise Invalid("History timestamp order mismatch")
        state=restore_transition(db,row,version,kind,item)
        db.execute("UPDATE experiments SET state=?,version=?,updated=? WHERE app_id=? AND id=?",(state,version,item["created"],app_id,row["id"]))
        previous=item["created"]
    if state!=row["state"]:raise Invalid("Snapshot state disagrees with its history")


def restore_transition(db,row,version,kind,item):
    """Require exact schemas and state-linked assessment and decision hashes."""
    app_id=row["app_id"];experiment_id=row["id"]
    fields={"app_id","experiment_id","hash","data","created","version"} if kind=="assessment" else {"id","app_id","experiment_id","hash","data","created"}
    if set(item)!=fields or item["app_id"]!=app_id or item["experiment_id"]!=experiment_id:raise Invalid("History scope or schema mismatch")
    safe_data(item["data"])
    if digest(item["data"])!=item["hash"]:raise Invalid("History content hash mismatch")
    current=lookup(db,app_id,experiment_id)
    if kind=="action":
        state=action_state(db,current,item["data"])
        db.execute("INSERT INTO experiment_actions(app_id,experiment_id,hash,data,created) VALUES(?,?,?,?,?)",(app_id,experiment_id,item["hash"],canonical(item["data"]),item["created"]))
        return state
    validate_assessment(current,row,item)
    db.execute("INSERT INTO experiment_assessments VALUES(?,?,?,?,?,?)",(app_id,experiment_id,item["hash"],canonical(item["data"]),item["created"],version))
    return "EVALUATED"


def validate_assessment(current,row,item):
    """Reject early, unlinked or fabricated statuses when replaying history."""
    if current["state"] in ("PLANNED","CANCELLED") or item["data"].get("definition_hash")!=row["hash"]:raise Invalid("Assessment is not linked to an observed experiment")
    if item["data"].get("status") not in ("EVALUATED","INCONCLUSIVE","BLOCKED") or iso_time(item["created"])<iso_time(row["data"]["analysis_at"]):raise Invalid("Invalid assessment status or early assessment")
