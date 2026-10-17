"""Versioned supplied publication and creative-cost joins; no attribution inference."""
import json
from .common import Invalid,canonical,digest,iso_time,now,required
from .db import connection
from .creative_analysis import latest
from .creative_briefs import stale_findings
from .creative_library import source_url
from .experiments import lookup,asset_intact

LINK_FIELDS={"experiment_id","arm","brief_id","publication_url","published_at","cost_events"}


def decoded(row):
    """Decode immutable content and reject corrupted hashes."""
    result=dict(row); result["data"]=json.loads(result["data"])
    if digest(result["data"])!=result["hash"]:raise Invalid("Saved outcome link integrity failed")
    return result


def current_link(db,app_id,experiment_id,arm):
    """Resolve the latest scoped revision, never another app's row."""
    row=db.execute("SELECT * FROM creative_outcome_links WHERE app_id=? AND experiment_id=? AND arm=? ORDER BY version DESC LIMIT 1",(app_id,experiment_id,arm)).fetchone()
    if not row:raise Invalid("Link both creative arms to briefs, publication receipts and cost rows")
    return decoded(row)


def app_hash(db,app_id):
    """Bind the complete current app manifest."""
    row=db.execute("SELECT data FROM apps WHERE id=?",(app_id,)).fetchone()
    if not row:raise Invalid("App workspace not found")
    return digest(json.loads(row[0]))


def cost_rows(db,app_id,cohort,selected):
    """Read exact included delivery costs without subtracting them a second time."""
    if not isinstance(selected,list) or not 1<=len(selected)<=20:raise Invalid("Choose 1 through 20 creative production cost rows, including explicit zero if applicable")
    result=[]; identities=set()
    for item in selected:
        identity=cost_identity(item)
        if identity in identities:raise Invalid("A production cost row cannot be allocated twice")
        identities.add(identity)
        row=db.execute("SELECT data,hash FROM growth_events WHERE app_id=? AND cohort_id=? AND provider=? AND external_id=?",(app_id,cohort["cohort_id"],*identity)).fetchone()
        if not row:raise Invalid("Creative cost must belong to the selected variant cohort")
        event=json.loads(row["data"])
        if event["type"]!="COST_DELIVERY" or event["currency"]!=cohort["currency"] or iso_time(event["occurred_at"])>iso_time(now()):raise Invalid("Select current delivery-cost evidence in the cohort currency")
        result.append({"provider":identity[0],"event_id":identity[1],"hash":row["hash"],"amount_minor":event["amount_minor"],"source":event["source"]})
    return sorted(result,key=lambda r:(r["provider"],r["event_id"]))


def cost_identity(item):
    """Validate one exact provider/event pair before database resolution."""
    if not isinstance(item,dict) or set(item)!={"provider","event_id"}:raise Invalid("Choose the exact provider and event ID for each cost")
    return required(item["provider"],"Cost provider",120),required(item["event_id"],"Cost event",120)


def bind_link(db,store,app_id,data):
    """Freeze an exact current creative/variant/publication/cost allocation."""
    if not isinstance(data,dict) or set(data)!=LINK_FIELDS or data["arm"] not in ("control","treatment"):raise Invalid("Complete the exact creative outcome link fields")
    experiment=lookup(db,app_id,required(data["experiment_id"],"Experiment",120)); variant=experiment["data"][data["arm"]]
    brief=bound_brief(db,store,app_id,data["brief_id"],variant)
    publication=source_url(data["publication_url"]); published=iso_time(data["published_at"])
    cohort=variant["cohort"]
    if not iso_time(cohort["starts_at"])<=published<iso_time(cohort["ends_at"]) or published>iso_time(now()):raise Invalid("Publication time must be observed within the acquisition window")
    costs=cost_rows(db,app_id,cohort,data["cost_events"])
    return {"request":dict(data,publication_url=publication,published_at=published.isoformat()),"app_hash":app_hash(db,app_id),
            "experiment_hash":experiment["hash"],"variant":variant,"brief":brief,"costs":costs,
            "production_cost_minor":sum(c["amount_minor"] for c in costs),"publication_authenticity":"OPERATOR_SUPPLIED",
            "cost_treatment":"ALREADY_INCLUDED_IN_DELIVERY_LEDGER"}


def bound_brief(db,store,app_id,brief_id,variant):
    """Freeze the actual current design before outcomes or publication exist."""
    brief=latest(db,"creative_briefs",app_id,required(brief_id,"Brief",120))
    findings=stale_findings(db,store,app_id,brief["data"])
    if findings:raise Invalid("Refresh the selected brief's current proof: "+"; ".join(findings))
    assets={r["id"]:r["hash"] for r in brief["data"]["records"] if r["kind"]=="asset"}
    if assets.get(variant["asset_id"])!=variant["asset_hash"]:raise Invalid("The brief must include the experiment's exact variant asset")
    return brief


def validate_link(db,store,app_id,experiment,row):
    """Recheck semantic identity without imposing today's age on historic proof."""
    data=row["data"]; request=data["request"]; variant=experiment["data"][request["arm"]]
    if row["app_id"]!=app_id or row["experiment_id"]!=experiment["id"] or row["arm"]!=request["arm"]:raise Invalid("Outcome link scope mismatch")
    brief=latest(db,"creative_briefs",app_id,request["brief_id"])
    checks=(data["app_hash"]==app_hash(db,app_id),data["experiment_hash"]==experiment["hash"],
            data["variant"]==variant,data["brief"]["hash"]==brief["hash"],
            data["costs"]==cost_rows(db,app_id,variant["cohort"],request["cost_events"]))
    if not all(checks):raise Invalid("Creative outcome source changed; inspect and relink before learning")
    asset=db.execute("SELECT hash,data FROM records WHERE app_id=? AND id=?",(app_id,variant["asset_id"])).fetchone()
    if not asset or asset["hash"]!=variant["asset_hash"] or not asset_intact(store.path.parent/"files"/app_id,json.loads(asset["data"])):raise Invalid("The linked creative asset is unavailable or changed")
    return row


def joined(db,store,app_id,experiment):
    """Require both source-current arms for outcome use."""
    return {arm:validate_link(db,store,app_id,experiment,current_link(db,app_id,experiment["id"],arm)) for arm in ("control","treatment")}


def append_link(db,app_id,experiment_id,arm,data,version):
    """Version exact content under optimistic concurrency and bounded history."""
    old=db.execute("SELECT version,hash FROM creative_outcome_links WHERE app_id=? AND experiment_id=? AND arm=? ORDER BY version DESC LIMIT 1",(app_id,experiment_id,arm)).fetchone()
    expected=old["version"] if old else None
    if version!=expected or (version is not None and type(version) is not int):raise Invalid("Outcome link changed; reload before saving")
    link_capacity(db,app_id,old)
    if old and old["hash"]==digest(data):return current_link(db,app_id,experiment_id,arm)
    next_version=(expected or 0)+1
    db.execute("INSERT INTO creative_outcome_links VALUES(?,?,?,?,?,?,?)",(app_id,experiment_id,arm,next_version,canonical(data),digest(data),now()))
    return current_link(db,app_id,experiment_id,arm)


def link_capacity(db,app_id,old):
    """Enforce both revision and identity storage bounds."""
    count=db.execute("SELECT count(*) FROM creative_outcome_links WHERE app_id=?",(app_id,)).fetchone()[0]
    if count>=5000:raise Invalid("Archive outcome links before 5000 revisions")
    identities=db.execute("SELECT count(*) FROM (SELECT DISTINCT experiment_id,arm FROM creative_outcome_links WHERE app_id=?)",(app_id,)).fetchone()[0]
    if old is None and identities>=1000:raise Invalid("Archive outcome links before 1000 identities")


class Links:
    def __init__(self,store):self.store=store

    def list(self,app_id):
        """Show current joins and unavailable reasons without fake empty success."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            groups=db.execute("SELECT DISTINCT experiment_id,arm FROM creative_outcome_links WHERE app_id=? ORDER BY experiment_id,arm LIMIT 1000",(app_id,)).fetchall()
            result=[]
            for group in groups:
                row=current_link(db,app_id,*group); row["findings"]=[]
                try:validate_link(db,self.store,app_id,lookup(db,app_id,row["experiment_id"]),row)
                except (Invalid,OSError,KeyError) as exc:row["findings"]=[str(exc) if isinstance(exc,Invalid) else "Required creative evidence is unavailable"]
                row["availability"]="UNAVAILABLE" if row["findings"] else "CURRENT";result.append(row)
            return result

    def options(self,app_id):
        """Offer only scoped cost rows; never expose cohort person identifiers."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            result=[]
            for row in db.execute("SELECT cohort_id,data FROM growth_events WHERE app_id=? ORDER BY provider,external_id",(app_id,)):
                event=json.loads(row["data"])
                if event["type"]=="COST_DELIVERY":result.append({"cohort_id":row["cohort_id"],**{k:event[k] for k in ("provider","event_id","amount_minor","currency","source")}})
                if len(result)>=1000:break
            return result

    def save(self,app_id,body):
        """Persist an explicit source allocation; never fabricate publication."""
        self.store.app(app_id)
        if set(body)!={"data","version"}:raise Invalid("Use the current outcome link revision")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            data=bind_link(db,self.store,app_id,body["data"]); experiment_id=body["data"]["experiment_id"];arm=body["data"]["arm"]
            other="treatment" if arm=="control" else "control"
            row=db.execute("SELECT data FROM creative_outcome_links WHERE app_id=? AND experiment_id=? AND arm=? ORDER BY version DESC LIMIT 1",(app_id,experiment_id,other)).fetchone()
            if row:
                identities={(c["provider"],c["event_id"]) for c in json.loads(row[0])["costs"]}
                if any((c["provider"],c["event_id"]) in identities for c in data["costs"]):raise Invalid("A cost row is already allocated to the other creative arm")
            return append_link(db,app_id,experiment_id,arm,data,body["version"])
