"""Guided, app-scoped acquisition preparation and immutable query-panel reports."""
from .common import Invalid,digest,now,required
from .db import connection
from .creative_analysis import append,latest,saved_items
from .acquisition_contract import bind_intent,intent_status,panel_definition,observation_definition

TABLES={"intents":"acquisition_intents","panels":"acquisition_panels","observations":"acquisition_observations","reports":"acquisition_reports"}


def slot(data):
    """Identify the exact fixed-panel attempt, without pooling test conditions."""
    return data["panel_id"],data["query_id"],data["repetition"]


def panel_current(db,store,app_id,panel):
    """A panel remains historical when its selected intent or product proof changes."""
    intent=latest(db,TABLES["intents"],app_id,panel["data"]["definition"]["intent_id"])
    return intent["hash"]==panel["data"]["intent"]["hash"] and intent_status(db,store,app_id,intent)=="CURRENT"


def require_panel(db,store,app_id,panel_id):
    """Block current acquisition actions until changed product sources are reviewed."""
    panel=latest(db,TABLES["panels"],app_id,panel_id)
    if not panel_current(db,store,app_id,panel):raise Invalid("Panel intent or product evidence changed; declare a new current panel")
    return panel


def partition_counts(panel,observations,partition):
    """Keep successes, errors and missing slots in distinct denominators."""
    queries=[q["id"] for q in panel["data"]["definition"]["queries"] if q["partition"]==partition]
    rows=[r["data"] for r in observations if r["data"]["query_id"] in queries]
    ok=[r for r in rows if r["status"]=="OK"];citations=[r for r in ok if r["citation_url"] is not None]
    page=panel["data"]["intent"]["data"]["definition"]["page_url"]
    result={"expected":len(queries)*panel["data"]["definition"]["repetitions"],"attempted":len(rows),"successful":len(ok),"errors":len(rows)-len(ok),
            "mentions":sum(r["mention"] for r in ok),"citations":len(citations),"correct_citations":sum(r["correct_citation"] is True for r in citations),
            "pending_review":sum(r["correct_citation"] is None for r in citations),"misinformation":sum(r["misinformation"] for r in ok),
            "correct_exact_destination":sum(r["correct_citation"] is True and r["citation_url"]==page for r in citations)}
    result["missing"]=result["expected"]-result["attempted"]
    for key in ("mentions","citations","misinformation"):result[key+"_per_answer"]=result[key]/len(ok) if ok else None
    reviewed=len(citations)-result["pending_review"]
    result["reviewed_citation_accuracy"]=result["correct_citations"]/reviewed if reviewed else None
    return result


def calculate(panel,observations,evaluated_at):
    """Reproducible descriptive report, retaining raw source rows and their hashes."""
    return {"panel":panel,"observations":observations,"evaluated_at":evaluated_at,
            "inputs_hash":digest({"panel":panel,"observations":observations}),
            "partitions":{p:partition_counts(panel,observations,p) for p in ("CALIBRATION","HOLDOUT")},
            "provider_execution":"NOT_RUN","publication":"NOT_RUN","growth_outcomes":"NOT_RUN",
            "limits":"Operator-supplied observations; repeated answers are correlated. API and consumer UI are different surfaces. Temporal holdout designation is not proof of an untouched external experiment."}


def observation_rows(db,app_id,panel_id):
    """Retain the exact ordered denominator for one panel only."""
    rows=[v["current"] for v in saved_items(db,TABLES["observations"],app_id) if v["current"]["data"]["panel_id"]==panel_id]
    return sorted(rows,key=lambda r:(r["data"]["query_id"],r["data"]["repetition"]))


def worksheet_rows(report,app_id):
    """Export known outcomes into the existing advisory pipeline without dropping slots."""
    if any(p["missing"] or p["pending_review"] for p in report["partitions"].values()):raise Invalid("Fill every panel slot and review citation correctness before attaching pipeline evidence")
    rows=[];definition=report["panel"]["data"]["definition"]
    for row in report["observations"]:
        d=row["data"];ok=d["status"]=="OK"
        rows.append({"app_id":app_id,"engine":definition["engine"]+" / "+definition["surface"]+" / "+definition["search_mode"],"locale":report["panel"]["data"]["intent"]["data"]["locale"],
                     "query_id":d["query_id"],"observation_id":row["id"],"observed_at":d["observed_at"],"source_ref":d["source_ref"],"status":"ok" if ok else "error",
                     "mention":d["mention"],"citation":d["citation_url"] is not None if ok else None,"correct_citation":bool(d["correct_citation"]) if ok else None,"citation_url":d["citation_url"]})
    return {"app_id":app_id,"as_of":report["evaluated_at"],"aeo":rows}


class Acquisition:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Expose immutable history, currentness and exact source chains to the UI."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            result={kind:saved_items(db,table,app_id) for kind,table in TABLES.items()}
            for item in result["intents"]:item["evidence_status"]=intent_status(db,self.store,app_id,item["current"])
            for kind in ("panels","reports"):
                for item in result[kind]:
                    panel=item["current"] if kind=="panels" else item["current"]["data"]["panel"]
                    item["evidence_status"]="CURRENT" if panel_current(db,self.store,app_id,panel) else "STALE_EVIDENCE"
            return result

    def save(self,app_id,kind,body):
        """Apply exact guided actions inside an app-scoped writer transaction."""
        self.store.app(app_id)
        if kind not in ("intents","panels","observations"):raise Invalid("Choose intent, panel or observation")
        if set(body) not in ({"data"},{"id","version","data"}):raise Invalid("Invalid acquisition save fields")
        if kind!="intents" and set(body)!={"data"}:raise Invalid("Panels and observations are immutable; declare a new panel instead")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if kind=="intents":return append(db,TABLES[kind],app_id,bind_intent(db,self.store,app_id,body["data"]),body)
            if kind=="panels":return self.declare_panel(db,app_id,body)
            return self.observe(db,app_id,body)

    def declare_panel(self,db,app_id,body):
        """Declare a new fixed protocol before any outcomes exist."""
        data=body["data"];intent=latest(db,TABLES["intents"],app_id,data.get("intent_id") if isinstance(data,dict) else None)
        if intent_status(db,self.store,app_id,intent)!="CURRENT":raise Invalid("Correct the intent's current product evidence before declaring a panel")
        definition=panel_definition(data,intent)
        return append(db,TABLES["panels"],app_id,{"definition":definition,"intent":intent},{})

    def observe(self,db,app_id,body):
        """Idempotent identical slot retries; conflicting observations never overwrite."""
        data=body["data"];panel_id=required(data.get("panel_id") if isinstance(data,dict) else None,"Panel ID",120)
        panel=require_panel(db,self.store,app_id,panel_id)
        data=observation_definition(data,panel,panel["created"])
        for row in observation_rows(db,app_id,panel_id):
            if slot(row["data"])==slot(data):
                if row["data"]==data:return row
                raise Invalid("This fixed slot has an observation; it cannot be overwritten")
        return append(db,TABLES["observations"],app_id,data,{})

    def report(self,app_id,body):
        """Save the exact fixed panel and all observed/missing attempts in a report."""
        self.store.app(app_id)
        if set(body)!={"panel_id"}:raise Invalid("Choose exactly one fixed panel")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");panel=require_panel(db,self.store,app_id,body["panel_id"])
            return append(db,TABLES["reports"],app_id,calculate(panel,observation_rows(db,app_id,panel["id"]),now()),{})

    def attach(self,app_id,body):
        """Explicitly attach current complete observations to the existing stage worksheet."""
        from .metrics import acquisition_metrics
        self.store.app(app_id)
        if set(body)!={"report_id"}:raise Invalid("Choose exactly one saved report")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE");row=latest(db,TABLES["reports"],app_id,body["report_id"]);report=row["data"]
            panel=require_panel(db,self.store,app_id,report["panel"]["id"])
            if report["observations"]!=observation_rows(db,app_id,panel["id"]):raise Invalid("Observations changed; generate a current report first")
            analysis=worksheet_rows(report,app_id);acquisition_metrics(analysis,app_id)
            data={"analysis":analysis,"panel_report_id":row["id"],"panel_report_hash":row["hash"],"intent_hash":panel["data"]["intent"]["hash"],"release":panel["data"]["intent"]["data"]["app"]["release"],"scope":"Supplied fixed-panel observation; no publication, indexing or growth proof"}
            rid="acquisition-"+row["id"]
            old=db.execute("SELECT hash FROM records WHERE app_id=? AND id=?",(app_id,rid)).fetchone()
            expected=digest({"kind":"acquisition","data":data,"source":row["hash"]})
            if old and old["hash"]!=expected:raise Invalid("Attached report identity conflicts with existing evidence")
            if not old:self.store._write_record(db,app_id,rid,"acquisition","Fixed answer-engine panel",row["hash"],data,"panel-report",None)
            return {"id":rid,"report_hash":row["hash"]}
