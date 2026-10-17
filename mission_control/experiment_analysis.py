"""Fixed-window descriptive comparison and transparent normal-approximation planning."""
import math
from .common import Invalid, amount, fraction

METRICS={"activation_rate":"activated","paid_conversion":"paid","retention_rate":"retained"}


def sample_plan(baseline,effect,allocation):
    """Calculate approximate required binary sample; no universal conversion threshold."""
    for value in (baseline,effect,allocation):
        fraction(value,"Planning fraction")
        if not 0<value<1:raise Invalid("Planning fractions must be strictly between 0 and 1")
    if baseline+effect>=1:raise Invalid("Baseline plus detectable effect must be below one")
    pbar=baseline+effect/2
    total=pbar*(1-pbar)*(1/allocation+1/(1-allocation))*(1.96+0.841621)**2/effect**2
    return {"control":math.ceil(total*(1-allocation)),"treatment":math.ceil(total*allocation),
            "method":"Approximate two-proportion normal sample plan, 95% interval and 80% power; not proof of lift"}


def guardrail_data(data):
    """Validate predeclared financial and retained-usefulness constraints."""
    fields={"min_retention_rate","max_refund_fraction","min_contribution_minor","max_acquisition_minor"}
    if not isinstance(data,dict) or set(data)!=fields:raise Invalid("Complete all four guardrails")
    for key in ("min_retention_rate","max_refund_fraction"):fraction(data[key],key)
    amount(data["max_acquisition_minor"],"Acquisition cap")
    if type(data["min_contribution_minor"]) is not int:raise Invalid("Minimum contribution must be a whole number in minor units")
    return data


def wilson(count,total):
    """Wilson 95% interval retains binary boundaries for small observed counts."""
    p=count/total;z=1.96;den=1+z*z/total
    center=(p+z*z/(2*total))/den
    margin=z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/den
    return max(0,center-margin),min(1,center+margin)


def comparison(control,treatment,metric):
    """Return descriptive difference with a Newcombe Wilson interval, never causal lift."""
    if not control["installs"] or not treatment["installs"]:return None
    key=METRICS[metric]
    c=control[key]/control["installs"];t=treatment[key]/treatment["installs"]
    clo,chi=wilson(control[key],control["installs"]);tlo,thi=wilson(treatment[key],treatment["installs"])
    difference=t-c
    return {"control_rate":c,"treatment_rate":t,"difference":difference,
            "interval":[difference-math.sqrt((t-tlo)**2+(chi-c)**2),difference+math.sqrt((thi-t)**2+(c-clo)**2)],
            "method":"Descriptive difference; Newcombe Wilson 95% interval; supplied assignment is not verified causal evidence"}


def sample_diagnostics(reports,plan,allocation):
    """Expose sample shortfalls and a fixed 1% allocation mismatch diagnostic."""
    c,t=[reports[arm]["installs"] for arm in ("control","treatment")]
    issues=[]
    for arm in ("control","treatment"):
        if reports[arm]["installs"]<plan[arm]:issues.append(arm+" sample below predeclared requirement")
    total=c+t
    chi=(c-total*(1-allocation))**2/(total*(1-allocation))+(t-total*allocation)**2/(total*allocation) if total else None
    if chi is not None and chi>6.634897:issues.append("Sample ratio mismatch; investigate assignment and logging")
    return {"issues":issues,"sample_ratio_chi_square":chi,"required":plan}


def guardrail_findings(reports,guardrails):
    """Keep missing financial denominators unknown instead of marking a pass."""
    failures=[]
    for arm,r in reports.items():
        values={"retention":r["retention_rate"],"contribution":r["contribution_after_acquisition_minor"],"cost":r["acquisition_cost_minor"]}
        gross=r["net_proceeds_minor"]+r["refunds_minor"] if r["net_proceeds_minor"] is not None and r["refunds_minor"] is not None else None
        refund_fraction=r["refunds_minor"]/gross if gross else None
        if any(value is None for value in values.values()) or refund_fraction is None:
            failures.append(arm+" guardrail denominator or costs unavailable");continue
        checks=(values["retention"]>=guardrails["min_retention_rate"],values["contribution"]>=guardrails["min_contribution_minor"],
                values["cost"]<=guardrails["max_acquisition_minor"],refund_fraction<=guardrails["max_refund_fraction"])
        if not all(checks):failures.append(arm+" breached a predeclared retention/refund/contribution/cost guardrail")
    return failures


def analyze(definition,reports,overlap,quality):
    """Evaluate mature imported evidence only after diagnostics and declared guardrails."""
    diagnostic=sample_diagnostics(reports,definition["sample_plan"],definition["treatment_allocation"])
    issues=diagnostic["issues"][:]
    if overlap:issues.append("Cross-arm subject contamination: "+str(overlap))
    for arm,r in reports.items():
        if r["status"]!="SUPPLIED_RECONCILED":issues.append(arm+" cohort is immature, unresolved or incomplete")
    guardrails=guardrail_findings(reports,definition["guardrails"])
    issues+=guardrails+quality
    effect=comparison(reports["control"],reports["treatment"],definition["primary_metric"]) if not issues else None
    return {"status":"BLOCKED" if quality or overlap else "INCONCLUSIVE" if issues else "EVALUATED",
            "issues":issues,"diagnostics":diagnostic,"effect":effect,"reports":reports,"guardrail_findings":guardrails,
            "recommendation":"Repair identified cause or collect mature evidence" if issues else "Review this descriptive result before proposing another bounded test",
            "scope":"Imported cohort comparison; no verified randomization, incremental revenue, automatic winner, campaign launch or budget authority"}
