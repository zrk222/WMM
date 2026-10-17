"""Actionable packets, not fabricated marketing outcomes."""
from .common import digest, now
from .metrics import summarize


def by_kind(records, kind):
    """Select structured evidence for one packet input category."""
    return [r["data"] for r in records if r["kind"]==kind]


def creative(app, records):
    """Generate six draft creative briefs from an app job and supplied claim proof."""
    claims=[r["data"] for r in records if r["kind"]=="claim" and r["data"].get("result")=="PASS" and r["data"].get("release")==app["data"].get("release") and r["data"].get("locale")==app["data"].get("locale") and bool(app["data"].get("locale"))]
    promise=claims[0].get("claim") if claims else app["data"].get("job")
    angles=["Show the current workaround","Demonstrate the useful outcome","Explain one honest limitation"]
    hooks=["Problem first","Real screen first"]
    return [{"id":f"brief-{i+1}","angle":angle,"hook":hook,"promise":promise,
             "audience":app["data"].get("audience"),"demo":"Capture the advertised job on the exact reviewed build",
             "cta":"Try the demonstrated task","rights":"REVIEW_REQUIRED","status":"DRAFT"}
            for i,(angle,hook) in enumerate((a,h) for a in angles for h in hooks)]


def weekly(app, records, checklist,ledger_reports=()):
    """Report supplied outcomes, unresolved bottlenecks and one bounded next action."""
    metrics=summarize(records,app["id"],ledger_reports)
    missing=[s["title"] for s in checklist if s["status"]!="READY"]
    return {"app":app["data"]["name"],"metrics":metrics,"decision":"REPAIR_OR_COLLECT_EVIDENCE" if missing else "REVIEW_EXPERIMENT",
            "bottlenecks":missing,"next_action":missing[0] if missing else "Review mature cohorts and authorize the next bounded experiment",
            "incremental_lift":"UNPROVEN","approved_spend_minor":0}


def reflection(app, records, checklist,ledger_reports=()):
    """Propose a versioned experiment change without altering permissions or prices."""
    report=weekly(app,records,checklist,ledger_reports)
    return {"version":digest(report),"change_hypothesis":report["next_action"],"evidence":report,
            "heldout_test":"Define untouched examples and an analysis date before adoption",
            "rollback":"Retain prior packet and app manifest version",
            "status":"PROPOSED","permission_changes":False,"price_changes":False}


def stage_packet(stage, app, records, checklist,ledger_reports=()):
    """Create a complete inspectable packet with source hashes and external-state limits."""
    builders={6:lambda: {"briefs":creative(app,records)},11:lambda:weekly(app,records,checklist,ledger_reports),
              12:lambda:reflection(app,records,checklist,ledger_reports),4:lambda:summarize(records,app["id"],ledger_reports)}
    if stage["id"] in builders:
        output=builders[stage["id"]]()
    else:
        output={"app_facts":app["data"],"inputs":{kind:by_kind(records,kind) for kind in stage["inputs"] if kind!="manifest"},
                "operator_steps":stage["operations"]["tasks"],
                "skill_command":f"Use $app-store-growth for {app['data']['name']}: {stage['title']}. Inspect this packet and current evidence before acting."}
    return {"schema":"growth.stage-packet.v1","app_id":app["id"],"stage":stage["id"],"title":stage["title"],
            "created_at":now(),"manifest_version":app["version"],"source_hashes":[r["hash"] for r in records]+[r["source_hash"] for r in ledger_reports],
            "local_status":"PREPARED","external_execution":"NOT_RUN","operations":stage["operations"],"content":output}
