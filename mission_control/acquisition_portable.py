"""Atomic portable acquisition histories; integrity is not authenticated authorship."""
from .common import Invalid,canonical,digest,iso_time,now,required
from .creative_analysis import decoded,saved_items
from .creative_portable import captured_source
from .creative_rank_portable import rank_rows
from .acquisition_contract import intent_definition,panel_definition,observation_definition
from .acquisition_workflows import TABLES,calculate,slot,observation_rows


def export_acquisition(db,app_id):
    """Export only retained immutable rows, never derived freshness status."""
    return {kind:saved_items(db,table,app_id) for kind,table in TABLES.items()}


def historical(db,table,app_id,item_id,value_hash):
    """Resolve an exact historical row from retained own-app versions."""
    required(item_id,"Acquisition item ID",120);required(value_hash,"Acquisition hash",64)
    row=db.execute(f"SELECT * FROM {table} WHERE app_id=? AND id=? AND hash=?",(app_id,item_id,value_hash)).fetchone()
    if not row:raise Invalid("Acquisition source history is absent or changed")
    return decoded(row)


def validate_intent(db,app_id,data):
    """Check retained source, selected proof hashes and declared preparation state."""
    fields={"definition","app","app_hash","analysis","source","records","brief","locale","first_value","asa_status","demand","crawl_index","publication"}
    if not isinstance(data,dict) or set(data)!=fields:raise Invalid("Invalid portable intent fields")
    d=intent_definition(data["definition"])
    analysis=historical(db,"creative_analyses",app_id,d["analysis_id"],d["analysis_hash"])
    a=analysis["data"];source=captured_source(db,app_id,a["reference_id"],a["capture_hash"])
    if analysis!=data["analysis"] or source!=data["source"]:raise Invalid("Frozen acquisition source changed")
    validate_intent_state(data,d)
    validate_records(data,app_id)
    validate_intent_brief(db,app_id,data,d,analysis)


def validate_intent_state(data,d):
    """Frozen manifest identity and unexecuted states survive portability."""
    if digest(data["app"])!=data["app_hash"] or data["locale"]!=data["app"]["locale"] or data["first_value"]!=data["app"]["activation"]:raise Invalid("Frozen intent app scope changed")
    expected="PREPARED" if d["store_id"] else "BLOCKED_STORE"
    if (data["asa_status"],data["demand"],data["crawl_index"],data["publication"])!=(expected,"UNKNOWN","NOT_RUN","NOT_RUN"):raise Invalid("Acquisition preparation cannot become measured publication")


def validate_intent_brief(db,app_id,data,d,analysis):
    """Optional linked creative must retain its exact inspected source."""
    if d["brief_id"] is None:
        if data["brief"] is not None:raise Invalid("Unexpected creative brief")
    else:
        brief=data["brief"]
        if not isinstance(brief,dict) or set(brief)!={"id","hash"} or brief["id"]!=d["brief_id"]:raise Invalid("Changed creative brief identity")
        row=historical(db,"creative_briefs",app_id,brief["id"],brief["hash"])
        if row["data"]["analysis"]["id"]!=analysis["id"]:raise Invalid("Creative brief source changed")


def validate_records(data,app_id):
    """Validate historic product evidence without pretending to recheck old freshness."""
    d=data["definition"];expected={d[k+"_id"]:k for k in ("claim","readiness","route")}
    if d["store_id"]:expected[d["store_id"]]="store"
    rows=data["records"]
    if not isinstance(rows,list) or len(rows)!=len(expected):raise Invalid("Frozen acquisition proof is incomplete")
    seen=set()
    for row in rows:
        validate_record(row,data,app_id,expected,seen)
        seen.add(row["id"])


def validate_record(row,data,app_id,expected,seen):
    """Check one selected record's scope, hash, release and language."""
    if not isinstance(row,dict) or set(row)!={"app_id","id","kind","data","source","hash"}:raise Invalid("Invalid frozen acquisition proof")
    if not isinstance(row["id"],str) or row["id"] in seen or row["app_id"]!=app_id or expected.get(row["id"])!=row["kind"]:raise Invalid("Acquisition proof scope changed")
    if digest({"kind":row["kind"],"data":row["data"],"source":row["source"]})!=row["hash"]:raise Invalid("Acquisition proof hash changed")
    if row["data"].get("release")!=data["app"]["release"]:raise Invalid("Acquisition proof release changed")
    validate_record_locale(row,data)


def validate_record_locale(row,data):
    """Language-scoped claim and destination evidence cannot cross app locales."""
    if row["kind"] in ("claim","store") and row["data"].get("locale")!=data["locale"]:raise Invalid("Acquisition proof locale changed")


def validate_panel(db,app_id,data):
    """Replay fixed test conditions against an exact retained intent revision."""
    if not isinstance(data,dict) or set(data)!={"definition","intent"}:raise Invalid("Invalid panel envelope")
    d=data["definition"]
    if not isinstance(d,dict):raise Invalid("Invalid panel definition")
    intent=historical(db,TABLES["intents"],app_id,d.get("intent_id"),d.get("intent_hash"))
    if data["intent"]!=intent or panel_definition(d,intent)!=d:raise Invalid("Panel intent or normalization changed")


def validate_observation(db,app_id,row,seen):
    """Reject changed panel links, duplicate slots and impossible declaration timing."""
    data=row["data"]
    panel=historical(db,TABLES["panels"],app_id,data.get("panel_id"),data.get("panel_hash"))
    if observation_definition(data,panel,panel["created"])!=data or slot(data) in seen:raise Invalid("Observation slot changed or duplicated")
    if iso_time(row["created"])<iso_time(data["observed_at"]):raise Invalid("Observation predates its recorded attempt")
    seen.add(slot(data))


def validate_report(db,app_id,data):
    """Recompute reports only from exact retained panel and observation rows."""
    if not isinstance(data,dict) or not isinstance(data.get("panel"),dict) or not isinstance(data.get("observations"),list):raise Invalid("Invalid acquisition report envelope")
    p=data["panel"];panel=historical(db,TABLES["panels"],app_id,p.get("id"),p.get("hash"))
    if panel!=p:raise Invalid("Report panel changed")
    cutoff=iso_time(data.get("evaluated_at"))
    if cutoff>iso_time(now()):raise Invalid("Future acquisition report")
    if cutoff<iso_time(panel["created"]):raise Invalid("Acquisition report predates panel declaration")
    rows=report_observations(db,app_id,data,p,cutoff)
    expected=[r for r in observation_rows(db,app_id,p["id"]) if iso_time(r["created"])<=cutoff]
    if rows!=expected:raise Invalid("Report silently omitted observations available at evaluation")
    if calculate(panel,rows,data["evaluated_at"])!=data:raise Invalid("Acquisition report differs from retained observations")


def report_observations(db,app_id,data,p,cutoff):
    """Resolve exact observations, protecting panel scope, ordering and cutoff."""
    seen=set();rows=[]
    for row in data["observations"]:
        if not isinstance(row,dict):raise Invalid("Invalid report observation")
        actual=historical(db,TABLES["observations"],app_id,row.get("id"),row.get("hash"))
        if actual!=row or actual["data"]["panel_id"]!=p["id"] or slot(actual["data"]) in seen or iso_time(actual["created"])>cutoff:raise Invalid("Report observation scope, time or identity changed")
        rows.append(actual);seen.add(slot(actual["data"]))
    rows.sort(key=lambda r:(r["data"]["query_id"],r["data"]["repetition"]))
    return rows


def restore_acquisition(db,app_id,payload):
    """Validate then replay all immutable acquisition rows inside the restore transaction."""
    if payload is None:return
    if not isinstance(payload,dict) or set(payload)!=set(TABLES):raise Invalid("Invalid acquisition snapshot")
    seen=set()
    for kind,table in TABLES.items():
        groups=payload[kind]
        if not isinstance(groups,list) or any(not isinstance(g,dict) or not isinstance(g.get("id"),str) for g in groups):raise Invalid("Invalid acquisition history identity")
        restore_rows(db,app_id,kind,table,groups,seen)


def restore_rows(db,app_id,kind,table,groups,seen):
    """Validate each bounded revision before inserting it in the caller transaction."""
    for row in rank_rows(groups,app_id,"report" if kind=="reports" else kind):
        if kind in ("panels","observations","reports") and row["version"]!=1:raise Invalid("Fixed panel history cannot be revised")
        if kind=="intents":validate_intent(db,app_id,row["data"])
        elif kind=="panels":validate_panel(db,app_id,row["data"])
        elif kind=="observations":validate_observation(db,app_id,row,seen)
        else:validate_report(db,app_id,row["data"])
        db.execute(f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",(app_id,row["id"],row["version"],canonical(row["data"]),row["hash"],row["created"]))
