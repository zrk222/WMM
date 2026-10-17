"""Deterministic app-specific PMF investigation, never a PMF certification."""
from datetime import datetime,timezone
from .common import digest
from .automatic_preparation import check_scope
from .workflow_automation import baseline
from .automation_policy import preferences
from .pipeline import critical_findings,current

SOURCES=[
    {"title":"Superhuman PMF engine (2018 case study)","url":"https://review.firstround.com/how-superhuman-built-an-engine-to-find-product-market-fit/"},
    {"title":"Critical event and natural usage interval","url":"https://amplitude.com/docs/get-started/optimize-amplitude-workflow"},
    {"title":"Multiple PMF signals and caveats","url":"https://posthog.com/founders/measure-product-market-fit"},
    {"title":"PostHog event-triggered surveys","url":"https://posthog.com/docs/surveys/creating-surveys"},
    {"title":"RevenueCat renewal cohort semantics","url":"https://www.revenuecat.com/docs/dashboard-and-metrics/charts/subscription-retention-chart"},
    {"title":"Clarity friction signals","url":"https://clarity.microsoft.com/insights?clang=en"},
]


def latest_record(records,kind):
    """Never hide a newer failure behind an older success."""
    rows=[r for r in records if r["kind"]==kind]
    return max(rows,key=lambda r:(r["updated"],r["id"])) if rows else None


def core_state(app,records):
    """Critical findings and current build failures precede marketing experiments."""
    failures=critical_findings(records)
    ready=latest_record([r for r in records if r["data"].get("release")==app["data"].get("release")],"readiness")
    if ready and ready["data"].get("result")=="FAIL":failures.append(ready["title"])
    return {"failures":failures,"current_pass":bool(ready and current(ready,app))}


def next_step(facts,cadence,core,measurement,retained):
    """Return a research priority, not a statistically diagnosed causal bottleneck."""
    if core["failures"]:
        return {"state":"REPAIR_CORE","title":"Repair the core journey before optimizing acquisition","tool":"readiness"}
    if not all(facts.get(k) for k in ("job","audience","activation")) or not cadence:
        return {"state":"DEFINE_VALUE","title":"Define one user problem, target segment and return opportunity","tool":"app"}
    if not core["current_pass"]:
        return {"state":"VERIFY_VALUE","title":"Verify the promised outcome on the current build","tool":"readiness"}
    if not measurement:
        return {"state":"CONNECT_MEASUREMENT","title":"Validate outcome events, consent and payment reconciliation","tool":"measurement"}
    if retained["value"] is None:
        return {"state":"COLLECT_REPEAT_VALUE","title":"Collect a mature cohort over this app’s natural return cycle","tool":"results"}
    return {"state":"INVESTIGATE_SEGMENT","title":"Test why this segment returns, pays or switches away","tool":"experiments"}


def task_packets(app,cadence,source_hash):
    """REA observations feed ECC review; no hidden server-to-MCP execution."""
    facts=app["data"]
    return [
        {"id":"rea-journey","engine":"REA","execution":"NOT_RUN","depends_on":[],"app_id":app["id"],"release":facts.get("release"),"source_hash":source_hash,
         "output_required":["evidence_ids","artifact_hashes","observed_at","coverage","unknowns","observations"],
         "task":"Trace the current authorized first-value, return, save/reload and payment journeys; retain DOM/action/network evidence and unknowns.",
         "tools":["inspect_web_page","analyze_web_bundle","capture_browser_scenario"],"expected_value":facts.get("activation"),"cadence":cadence,
         "constraint":"Use the exact app/build and authorized public/review fixture; redact personal data; no purchases, publication or competitor login bypass."},
        {"id":"ecc-diagnosis","engine":"ECC","execution":"NOT_RUN","depends_on":["rea-journey"],"app_id":app["id"],"release":facts.get("release"),"source_hash":source_hash,
         "input_required":"Current source-bound REA evidence envelope, including coverage and unknowns; missing runtime evidence stays NOT_RUN.",
         "output_required":["confirmed_findings","hypotheses","counterargument","next_test","guardrails","execution_receipts"],
         "skills":["market-research","click-path-audit","ai-regression-testing","loop-design-check"],
         "task":"Critique source-linked problem, switching evidence, REA journey findings and mature behavior/economics. Separate observations from hypotheses. Produce one falsifiable test and counterargument.",
         "constraint":"Never infer PMF from static UI, growth promises, a survey threshold or missing/immature data; no autonomous goal or metric rewrites."},
    ]


def research_tasks(tasks,research):
    """Expose supplied results without granting execution or readiness authority."""
    for task in tasks:
        entries=[r for r in research["history"] if r["kind"]=="receipt" and r["data"]["engine"]==task["engine"] and r["data"]["source_hash"]==task["source_hash"]]
        task["supplied_results"]=[{"id":r["id"],"hash":r["hash"],"provenance":"IMPORTED_ASSERTION" if r["imported"] else "SUPPLIED_RESULT_NOT_AUTHENTICATED"} for r in entries]
    return tasks


def research_next(research,tasks,app):
    """Recommend the next unmet research prerequisite without a fit claim."""
    studies=[s for s in research["studies"] if all(s["study"]["data"][k]==app["data"].get(k) for k in ("release","locale","currency"))]
    if not studies:return {"state":"CREATE_STUDY","title":"Declare a current problem and segment study"}
    if any(s["snapshot"] is None for s in studies):return {"state":"IMPORT_OBSERVATIONS","title":"Import consented cohort observations"}
    if any(s["readout"]["pending"] for s in studies):return {"state":"COMPLETE_EVIDENCE","title":"Resolve the declared coverage, response or maturity gaps"}
    if not tasks[0]["supplied_results"]:return {"state":"REA_REVIEW","title":"Trace the value journey and record the REA evidence"}
    if not tasks[1]["supplied_results"]:return {"state":"ECC_REVIEW","title":"Critique the current REA evidence with ECC"}
    return {"state":"TEST_HYPOTHESIS","title":"Review supplied findings and preregister one falsifiable test"}


def prepare(app,records,reports,observed_at=None,research=None):
    """Refresh scoped recommendations without writing data or invoking providers."""
    check_scope(app,records,reports);at=observed_at or datetime.now(timezone.utc)
    cadence=preferences(app["data"])["cadence"] or None
    measured={metric:baseline(app,reports,metric,at) for metric in ("activation_rate","paid_conversion","retention_rate")}
    core=core_state(app,records);record=latest_record(records,"measurement")
    measurement=bool(record and current(record,app))
    research=research or {"history":[],"studies":[],"inputs_hash":digest([])}
    if any(r["app_id"]!=app["id"] for r in research["history"]):
        from .common import Invalid
        raise Invalid("Foreign PMF research")
    inputs={"app":app,"records":sorted((r["id"],r["version"],r["hash"]) for r in records),"reports":sorted(r["source_hash"] for r in reports),"research":research["inputs_hash"]}
    result={"schema":"growth.pmf-workflow.v1","app_id":app["id"],"manifest_version":app["version"],
            "classification":"RESEARCH_AND_PLANNING_ONLY","pmf_status":"UNPROVEN","automatic_external_writes":False,"authorized_spend_minor":0,
            "problem":app["data"].get("job"),"segment_hypothesis":app["data"].get("audience"),"value_event":app["data"].get("activation"),"value_cadence":cadence,
            "core":core,"measurement_current":measurement,"observations":measured,
            "next":next_step(app["data"],cadence,core,measurement,measured["retention_rate"]),
            "missing_research":["Interview evidence of the existing workaround, pain severity and switching cost","Segment-specific mature repeat-value and return-opportunity denominators","Survey invitation/response/nonresponse counts and source-linked reasons","First renewal, refunds, delivery cost and contribution for the same cohort","Predeclared success threshold, sample plan, holdout and rollback"],
            "tasks":research_tasks(task_packets(app,cadence,digest(inputs)),research),"research":research,"sources":SOURCES,
            "limits":["No PMF score or causal winner is computed.","40% very-disappointed is a historical survey heuristic, not a certification.","Saved research and supplied REA/ECC results do not establish authenticated plugin execution. Autonomous invocation remains unimplemented.","Supplied cohort reports are descriptive; missing evidence is not zero or proof of failure."]}
    result["research_next"]=research_next(research,result["tasks"],app)
    result["source_hash"]=digest({**inputs,"recommendations":result})
    return result
