"""Current outcome and untouched holdout contracts for local descriptive learning."""
import json
from .common import Invalid,digest,fraction,iso_time,now,required
from .experiments import lookup,evidence_reports,quality_findings
from .experiment_analysis import analyze
from .outcome_links import joined,app_hash,bound_brief
from .review_access import member,exact_role


def assessment(db,store,app_id,experiment_id,context=None):
    """Recompute exact latest mature assessment; cached green is not truth."""
    key=("assessment",app_id,experiment_id)
    if context is not None and key in context:return context[key]
    experiment=lookup(db,app_id,experiment_id)
    if experiment["state"] in ("PLANNED","CANCELLED") or iso_time(now())<iso_time(experiment["data"]["analysis_at"]):raise Invalid("Observe and evaluate this experiment after its fixed analysis date")
    reports,overlap=evidence_reports(db,app_id,experiment["data"],now())
    result=analyze(experiment["data"],reports,overlap,quality_findings(db,app_id,experiment["data"],store.path.parent/"files"/app_id))
    result["definition_hash"]=experiment["hash"]
    latest=db.execute("SELECT * FROM experiment_assessments WHERE app_id=? AND experiment_id=? ORDER BY version DESC LIMIT 1",(app_id,experiment_id)).fetchone()
    if not latest or latest["hash"]!=digest(result):raise Invalid("Outcomes changed; evaluate the experiment again before learning")
    if result["status"]!="EVALUATED":raise Invalid("Resolve experiment maturity, samples, financial and retained-value guardrails")
    value={"experiment":experiment,"assessment":result,"assessment_hash":latest["hash"],"links":joined(db,store,app_id,experiment)}
    if context is not None:context[key]=value
    return value


def training(db,store,app_id,experiment_id,context=None):
    """Require the operator's current bounded-next-test decision."""
    result=dict(assessment(db,store,app_id,experiment_id,context))
    action=db.execute("SELECT data FROM experiment_actions WHERE app_id=? AND experiment_id=? ORDER BY id DESC",(app_id,experiment_id)).fetchall()
    decisions=[json.loads(r[0]) for r in action if json.loads(r[0]).get("operation")=="decide"]
    if not decisions or decisions[0].get("decision")!="NEXT_TEST" or decisions[0].get("assessment_hash")!=result["assessment_hash"]:raise Invalid("Record a current next-test decision on the training experiment")
    result["decision"]=decisions[0]
    return result


def declare(body):
    """Validate the original hypothesis and predeclared practical holdout bound."""
    if set(body)!={"name","pattern","training_experiment_id","minimum_holdout_difference"}:raise Invalid("Complete the learning proposal fields")
    result=dict(body);result["name"]=required(body["name"],"Pattern name",120);result["pattern"]=required(body["pattern"],"Original creative method",2000)
    result["training_experiment_id"]=required(body["training_experiment_id"],"Training experiment",120)
    fraction(body["minimum_holdout_difference"],"Minimum holdout difference")
    if not 0<body["minimum_holdout_difference"]<1:raise Invalid("Minimum holdout difference must be greater than zero and below one")
    return result


def active_id(db,app_id):
    """Read the actual app-specific local guidance pointer."""
    row=db.execute("SELECT learning_id FROM learning_active WHERE app_id=?",(app_id,)).fetchone()
    return row[0] if row else None


def reserve_role(db,app_id,experiment_id,role,learning_id):
    """A seen training test can never be reused as an untouched holdout."""
    old=db.execute("SELECT role FROM learning_experiment_roles WHERE app_id=? AND experiment_id=?",(app_id,experiment_id)).fetchone()
    if old and (role=="HOLDOUT" or old[0]!="TRAIN"):raise Invalid("This experiment has already been used for training or a holdout")
    db.execute("INSERT OR IGNORE INTO learning_experiment_roles VALUES(?,?,?,?)",(app_id,experiment_id,role,learning_id))


def source_current(db,store,row,context=None):
    """Freeze training, app, role and exact immutable source link identities."""
    data=row["data"];app_id=row["app_id"]
    if row["restored"]:raise Invalid("Imported history transfers no learning authority; create a new proposal")
    if data["app_hash"]!=app_hash(db,app_id):raise Invalid("App manifest changed; prepare a new learning proposal")
    exact_role(db,app_id,row["preparer"],data["maker_role_version"],"MAKER")
    current=training(db,store,app_id,data["definition"]["training_experiment_id"],context)
    if digest(current)!=data["training_hash"]:raise Invalid("Training outcomes or sources changed; prepare a new proposal")
    return current


def holdout(db,store,row,request):
    """Reserve a newly registered future test before any event is observed."""
    data=row["data"];app_id=row["app_id"];candidate=lookup(db,app_id,required(request["experiment_id"],"Holdout experiment",120))
    source=data["training"]["experiment"]["data"];target=candidate["data"]
    if candidate["state"]!="PLANNED" or iso_time(candidate["created"])<=iso_time(row["created"]):raise Invalid("Register a new planned holdout after creating this proposal")
    if iso_time(target["control"]["cohort"]["starts_at"])<=iso_time(now()):raise Invalid("Reserve the holdout before acquisition begins")
    if target["primary_metric"]!=source["primary_metric"]:raise Invalid("Holdout primary metric must match the training hypothesis")
    for key in ("release","locale","currency"):
        if target["control"]["cohort"][key]!=source["control"]["cohort"][key]:raise Invalid("Holdout release, locale and currency must match training")
    cohorts=[target[arm]["cohort_id"] for arm in ("control","treatment")]
    if db.execute("SELECT 1 FROM growth_events WHERE app_id=? AND cohort_id IN (?,?) LIMIT 1",(app_id,*cohorts)).fetchone():raise Invalid("Holdout cohorts already contain observed events")
    briefs={arm:bound_brief(db,store,app_id,request[arm+"_brief_id"],target[arm]) for arm in ("control","treatment")}
    return {"experiment":candidate,"briefs":briefs,"reserved_at":now(),"pattern_instantiation":"OPERATOR_ATTESTED"}


def overlap_subjects(db,app_id,train,test):
    """Count disjointness without returning personal or pseudonymous identifiers."""
    def subjects(experiment):
        ids=[experiment["data"][arm]["cohort_id"] for arm in ("control","treatment")]
        return {json.loads(r[0])["subject_id"] for r in db.execute("SELECT data FROM growth_events WHERE app_id=? AND cohort_id IN (?,?)",(app_id,*ids)) if json.loads(r[0])["type"]=="INSTALL"}
    return len(subjects(train)&subjects(test))


def evaluation(db,store,row,context=None):
    """Apply predeclared descriptive holdout and contribution conditions."""
    source=source_current(db,store,row,context);reserved=row["data"].get("holdout")
    if not reserved:raise Invalid("Reserve a new untouched holdout first")
    current=assessment(db,store,row["app_id"],reserved["experiment"]["id"],context)
    if current["experiment"]["hash"]!=reserved["experiment"]["hash"]:raise Invalid("Reserved holdout definition changed")
    for arm in ("control","treatment"):
        if current["links"][arm]["data"]["brief"]["hash"]!=reserved["briefs"][arm]["hash"]:raise Invalid("Holdout creative does not match its reserved design")
    issues=[];effect=current["assessment"]["effect"];reports=current["assessment"]["reports"]
    if overlap_subjects(db,row["app_id"],source["experiment"],current["experiment"]):issues.append("Training and holdout share observed install subjects")
    if effect["interval"][0]<row["data"]["definition"]["minimum_holdout_difference"]:issues.append("Holdout lower difference bound does not meet the predeclared minimum")
    control=reports["control"]["contribution_after_acquisition_minor"]/reports["control"]["installs"]
    treatment=reports["treatment"]["contribution_after_acquisition_minor"]/reports["treatment"]["installs"]
    if treatment<control:issues.append("Treatment contribution per install is below control")
    return {"outcome":"REJECTED" if issues else "READY","issues":issues,"training_hash":digest(source),"holdout":current,
            "holdout_hash":digest(current),"contribution_per_install":{"control":control,"treatment":treatment},
            "scope":"Descriptive supplied outcomes; no causal lift, verified assignment or authenticated publication"}


def eligible(db,store,row,checker=False,context=None):
    """Revalidate adoption against current outcomes and current role versions."""
    result=evaluation(db,store,row,context)
    if result["outcome"]!="READY" or digest(result)!=row["data"].get("evaluation_hash"):raise Invalid("Guidance evaluation is unavailable or changed; review current outcomes")
    if checker:
        approval=row["data"].get("approval")
        if not approval or approval["principal"]==row["preparer"]:raise Invalid("Independent approval is required")
        exact_role(db,row["app_id"],approval["principal"],approval["role_version"],"CHECKER")
    return result
