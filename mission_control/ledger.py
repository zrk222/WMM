"""Immutable export ingestion and deterministic app/cohort/as-of reconciliation."""
import csv
from datetime import datetime, timezone
import io
import json
import re
from .common import Invalid, amount, canonical, digest, iso_time, now, required, safe_data
from .db import connection

TYPES={"INSTALL","ACTIVATION","VALUE","PURCHASE","REFUND","REFUND_REVERSED","COST_ACQUISITION","COST_DELIVERY"}
FIELDS={"provider","event_id","type","subject_id","occurred_at","amount_minor","currency","related_event_id","source"}
SUBJECT_TYPES={"INSTALL","ACTIVATION","VALUE","PURCHASE"}


def opaque(value,field):
    """Accept opaque export identifiers, never email addresses or contact strings."""
    value=required(value,field,120)
    if not re.fullmatch(r"[A-Za-z0-9_-]+",value):
        raise Invalid(f"{field}: use an opaque alphanumeric ID, not a contact identifier")
    return value


def currency(value):
    """Keep currencies explicit rather than silently convert or combine them."""
    if not isinstance(value,str) or not re.fullmatch(r"[A-Z]{3}",value):
        raise Invalid("Currency must be an explicit three-letter uppercase code")
    return value


def cohort_data(data):
    """Validate the immutable acquisition window and its observation contract."""
    safe_data(data)
    names=("cohort_id","release","platform","locale","currency","starts_at","ends_at","matures_at","attribution_method","observability","source")
    if set(data)!=set(names):
        raise Invalid("Cohort needs exactly: "+", ".join(names))
    result={key:required(data.get(key),key,2000) for key in names}
    result["cohort_id"]=opaque(result["cohort_id"],"cohort_id")
    result["currency"]=currency(result["currency"])
    times=[iso_time(result[key]) for key in ("starts_at","ends_at","matures_at")]
    if not times[0]<times[1]<=times[2]:
        raise Invalid("Acquisition start must precede end; maturity cannot precede end")
    if result["observability"] not in ("OBSERVED","PARTIAL","UNKNOWN"):
        raise Invalid("Choose OBSERVED, PARTIAL or UNKNOWN observability")
    return result


def event_data(row,csv_mode=False):
    """Normalize a permitted export row without accepting arbitrary personal fields."""
    if not isinstance(row,dict) or set(row)-FIELDS:
        raise Invalid("Event contains unsupported columns; use the provided template")
    safe_data(row)
    result={key:opaque(row.get(key),key) for key in ("provider","event_id")}
    result["type"]=required(row.get("type"),"type",120)
    if result["type"] not in TYPES:
        raise Invalid("Unsupported event type")
    result["subject_id"]=opaque(row.get("subject_id"),"subject_id") if result["type"] in SUBJECT_TYPES else ""
    result["occurred_at"]=iso_time(row.get("occurred_at")).astimezone(timezone.utc).isoformat()
    if iso_time(result["occurred_at"])>datetime.now(timezone.utc):
        raise Invalid("Observed export events cannot have future timestamps")
    value=row.get("amount_minor",0)
    if csv_mode:
        if not isinstance(value,str) or not value.isdigit():
            raise Invalid("CSV amount_minor must be a nonnegative integer")
        value=int(value)
    result["amount_minor"]=amount(value,"amount_minor")
    result["currency"]=currency(row.get("currency"))
    result["related_event_id"]=opaque(row.get("related_event_id"),"related_event_id") if result["type"] in ("REFUND","REFUND_REVERSED") else ""
    result["source"]=required(row.get("source"),"source",2000)
    return result


def write_cohort(db,app_id,data):
    """Idempotently create a definition; changes require a new cohort identity."""
    data=cohort_data(data)
    old=db.execute("SELECT hash FROM growth_cohorts WHERE app_id=? AND id=?",(app_id,data["cohort_id"])).fetchone()
    if old and old["hash"]!=digest(data):
        raise Invalid("Cohort definition changed; use a new cohort ID")
    db.execute("INSERT OR IGNORE INTO growth_cohorts VALUES(?,?,?,?,?)",(app_id,data["cohort_id"],canonical(data),digest(data),now()))
    return data


def write_events(db,app_id,cohort_id,events):
    """Reject ID collisions in the same transaction that admits immutable rows."""
    inserted=0
    for event in events:
        content={"cohort_id":cohort_id,"event":event}
        old=db.execute("SELECT hash FROM growth_events WHERE app_id=? AND provider=? AND external_id=?",(app_id,event["provider"],event["event_id"])).fetchone()
        if old and old["hash"]!=digest(content):
            raise Invalid("Event ID already exists with different content or cohort")
        inserted+=db.execute("INSERT OR IGNORE INTO growth_events VALUES(?,?,?,?,?,?,?)",(app_id,event["provider"],event["event_id"],cohort_id,canonical(event),digest(content),now())).rowcount
    return {"inserted":inserted,"duplicates":len(events)-inserted}


class Ledger:
    def __init__(self,path):
        self.path=path

    def define(self,app_id,data):
        """Persist a reviewed local cohort definition without modifying a product."""
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            result=write_cohort(db,app_id,data)
            db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,"ledger.cohort_defined",canonical({"cohort_id":result["cohort_id"],"hash":digest(result)}),now()))
        return result

    def ingest(self,app_id,body):
        """Atomically import a bounded CSV/JSON export with app-level deduplication."""
        cohort_id=opaque(body.get("cohort_id"),"cohort_id")
        if set(body) not in ({"cohort_id","csv"},{"cohort_id","events"}):
            raise Invalid("Provide one CSV export or one JSON event array")
        raw=csv_rows(body["csv"]) if "csv" in body else body.get("events")
        if not isinstance(raw,list) or not 0<len(raw)<=500:
            raise Invalid("Import between one and 500 event rows")
        events=[event_data(row,"csv" in body) for row in raw]
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT id FROM growth_cohorts WHERE app_id=? AND id=?",(app_id,cohort_id)).fetchone():
                raise Invalid("Define this cohort in the selected app before importing events")
            result=write_events(db,app_id,cohort_id,events)
            db.execute("INSERT INTO audit(app_id,action,detail,created) VALUES(?,?,?,?)",(app_id,"ledger.imported",canonical(dict(result,cohort_id=cohort_id)),now()))
        return dict(result,cohort_id=cohort_id,provenance="OPERATOR_IMPORT; provider signatures not verified")

    def export(self,app_id):
        """Return source-bound cohort definitions and immutable event records."""
        with connection(self.path) as db:
            cohorts=[json.loads(r["data"]) for r in db.execute("SELECT data FROM growth_cohorts WHERE app_id=? ORDER BY id",(app_id,))]
            events=[dict(cohort_id=r["cohort_id"],data=json.loads(r["data"]),hash=r["hash"]) for r in db.execute("SELECT cohort_id,data,hash FROM growth_events WHERE app_id=? ORDER BY provider,external_id",(app_id,))]
        return {"cohorts":cohorts,"events":events}

    def reports(self,app_id,as_of=None):
        """Calculate one reproducible as-of view per declared cohort."""
        as_of=iso_time(as_of or now())
        if as_of>datetime.now(timezone.utc):
            raise Invalid("An observed report cannot use a future as-of time")
        snapshot=self.export(app_id)
        return [report(cohort,[r["data"] for r in snapshot["events"] if r["cohort_id"]==cohort["cohort_id"]],as_of) for cohort in snapshot["cohorts"]]


def csv_rows(text):
    """Reject ambiguous column names before parsing source export rows."""
    reader=csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    fields=reader.fieldnames or []
    if len(fields)!=len(set(fields)) or set(fields)!=FIELDS:
        raise Invalid("CSV columns must exactly match the template, without duplicates")
    return list(reader)


def restore_ledger(db,app_id,payload):
    """Restore validated measurement data inside the caller's workspace transaction."""
    if payload is None:
        return
    validate_snapshot(payload)
    definitions=[cohort_data(c) for c in payload["cohorts"]]
    cohort_ids={c["cohort_id"] for c in definitions}
    for data in definitions:
        write_cohort(db,app_id,data)
    for item in payload["events"]:
        if not isinstance(item,dict) or set(item)!={"cohort_id","data","hash"}:
            raise Invalid("Snapshot event schema is invalid")
        if item["cohort_id"] not in cohort_ids:
            raise Invalid("Snapshot event references an absent cohort")
        event=event_data(item["data"])
        content={"cohort_id":item["cohort_id"],"event":event}
        if digest(content)!=item["hash"]:
            raise Invalid("Snapshot event hash mismatch")
        write_events(db,app_id,item["cohort_id"],[event])


def validate_snapshot(payload):
    """Validate export collection shape and bounds before any restore writes."""
    if not isinstance(payload,dict) or set(payload)!={"cohorts","events"}:
        raise Invalid("Snapshot ledger schema is invalid")
    if not isinstance(payload["cohorts"],list) or not isinstance(payload["events"],list) or len(payload["cohorts"])>1000 or len(payload["events"])>10000:
        raise Invalid("Snapshot ledger exceeds its validated bounds")


def finance(events,unit):
    """Reconcile same-provider purchase/refund/reversal references as of the report."""
    purchases={(e["provider"],e["event_id"]):e for e in events if e["type"]=="PURCHASE"}
    refunds={(e["provider"],e["event_id"]):e for e in events if e["type"]=="REFUND"}
    issues=[]
    totals={key:0 for key in purchases}
    reversed_totals={key:0 for key in refunds}
    for event in events:
        apply_adjustment(event,purchases,refunds,totals,reversed_totals,issues)
    for key,total in totals.items():
        if not 0<=total<=purchases[key]["amount_minor"]:
            issues.append("Refund balance exceeds purchase proceeds: "+key[1])
    if any(e["currency"]!=unit for e in events):
        issues.append("Mixed currencies require reconciled provider remittances; no FX inferred")
    proceeds=sum(e["amount_minor"] for e in purchases.values())
    return {"net_proceeds_minor":None if issues else proceeds-sum(totals.values()),"refunds_minor":None if issues else sum(totals.values()),"issues":issues}


def apply_adjustment(event,purchases,refunds,totals,reversed_totals,issues):
    """Apply a late adjustment once or expose its unresolved transaction chain."""
    if event["type"] not in ("REFUND","REFUND_REVERSED"):
        return
    reference=(event["provider"],event["related_event_id"])
    original=purchases.get(reference) if event["type"]=="REFUND" else refunds.get(reference)
    if not original or iso_time(original["occurred_at"])>iso_time(event["occurred_at"]):
        issues.append("Unresolved adjustment: "+event["event_id"])
        return
    if event["type"]=="REFUND":
        totals[reference]+=event["amount_minor"]
        return
    reversed_totals[reference]+=event["amount_minor"]
    purchase=(original["provider"],original["related_event_id"])
    if purchase not in totals or reversed_totals[reference]>original["amount_minor"]:
        issues.append("Unresolved or excessive reversal: "+event["event_id"])
        return
    totals[purchase]-=event["amount_minor"]


def report(cohort,events,as_of):
    """Separate unique observed funnel counts from maturity and finance uncertainty."""
    events=sorted([e for e in events if iso_time(e["occurred_at"])<=as_of],key=lambda e:iso_time(e["occurred_at"]))
    starts,ends,maturity=[iso_time(cohort[k]) for k in ("starts_at","ends_at","matures_at")]
    counts=funnel_counts(events,starts,ends,maturity)
    money=finance(events,cohort["currency"])
    acquisition=sum(e["amount_minor"] for e in events if e["type"]=="COST_ACQUISITION")
    delivery=sum(e["amount_minor"] for e in events if e["type"]=="COST_DELIVERY")
    observable=cohort["observability"]=="OBSERVED"
    costs_complete={"COST_ACQUISITION","COST_DELIVERY"}<=set(e["type"] for e in events)
    complete=observable and as_of>=maturity and not money["issues"] and costs_complete
    count=counts["installs"]
    return {"cohort":cohort,"as_of":as_of.isoformat(),"status":"SUPPLIED_RECONCILED" if complete else "INCONCLUSIVE","events":len(events),
            **counts,
            "activation_rate":observed_rate(counts["activated"],count,observable),
            "paid_conversion":observed_rate(counts["paid"],count,complete),
            "retention_rate":observed_rate(counts["retained"],count,complete),
            "net_proceeds_minor":money["net_proceeds_minor"],"refunds_minor":money["refunds_minor"],
            "acquisition_cost_minor":acquisition,"delivery_cost_minor":delivery,
            "paid_cac_minor":observed_rate(acquisition,counts["paid"],complete),
            "contribution_after_acquisition_minor":money["net_proceeds_minor"]-delivery-acquisition if complete else None,
            "issues":money["issues"],"source_hash":digest({"cohort":cohort,"events":events}),
            "mature":as_of>=maturity,"costs_complete":costs_complete,"observability":cohort["observability"],
            "scope":"Imported observations; signatures and data completeness are not independently verified. Retention is a VALUE after acquisition ends and by maturity. No causal lift."}


def eligible_events(events,starts,ends):
    """Identify each observed install once and its subsequent eligible events."""
    installers={}
    for event in events:
        if event["type"]=="INSTALL" and starts<=iso_time(event["occurred_at"])<ends:
            installers.setdefault(event["subject_id"],iso_time(event["occurred_at"]))
    eligible=[e for e in events if e["subject_id"] in installers and iso_time(e["occurred_at"])>=installers[e["subject_id"]]]
    return installers,eligible


def funnel_counts(events,starts,ends,maturity):
    """Count unique acquired subjects using the declared useful-value window."""
    installers,eligible=eligible_events(events,starts,ends)
    activated={e["subject_id"] for e in eligible if e["type"]=="ACTIVATION"}
    paid={e["subject_id"] for e in eligible if e["type"]=="PURCHASE" and e["amount_minor"]>0}
    retained={e["subject_id"] for e in eligible if e["type"]=="VALUE" and ends<=iso_time(e["occurred_at"])<=maturity}
    return {"installs":len(installers),"activated":len(activated),"paid":len(paid),"retained":len(retained)}


def observed_rate(total,eligible,available):
    """Preserve unavailable denominators and immature observation windows."""
    return total/eligible if available and eligible else None
