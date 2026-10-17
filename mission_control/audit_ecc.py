"""Deterministic ECC skill rules over bound native observations, never approval."""
import re
from urllib.parse import urlsplit
from .common import Invalid, digest


def contains(actual, expected):
    """REA adds defaults; every declared input must still match exactly."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and contains(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(contains(a, b) for a, b in zip(actual, expected))
    return actual == expected


def native(value, scenario):
    """Validate provenance, normalized request and ordered outcomes independently of exit code."""
    if not isinstance(value, dict) or value.get("ok") is not True:
        raise Invalid("REA did not return a successful evidence envelope")
    d = value.get("data", {})
    structure(d)
    if d.get("operation") != "capture_browser_scenario" or d.get("provider", {}).get("id") != "rea-playwright-browser-scenario":
        raise Invalid("Unexpected native evidence provider or operation")
    if not re.fullmatch(r"ev_[a-f0-9]{64}", str(d.get("evidence_id"))):
        raise Invalid("Missing native evidence identity")
    parameters = dict(d.get("parameters", {}))
    sha = parameters.pop("scenario_sha256", None)
    if sha != digest(parameters) or not contains(parameters, scenario):
        raise Invalid("Native scenario does not match the frozen request")
    result = d.get("normalized_result", {})
    steps = result.get("steps", [])
    expected = [("scenario_start", "goto_start")] + [(s["step_id"], s["action"]) for s in scenario["actions"]]
    if [(s.get("step_id"), s.get("action")) for s in steps] != expected:
        raise Invalid("Native step sequence does not match the frozen request")
    check_urls(steps,scenario["start_url"]["url"])
    return d, result


def structure(data):
    """Malformed native payloads block one job instead of killing the shared worker."""
    if not isinstance(data,dict):raise Invalid("Malformed native evidence")
    for key in ("provider","parameters","normalized_result"):
        if not isinstance(data.get(key),dict):raise Invalid("Malformed native evidence section")
    result=data["normalized_result"]
    if not isinstance(result.get("completeness"),dict):raise Invalid("Malformed native completeness")
    steps=result.get("steps")
    if not isinstance(steps,list) or any(not isinstance(s,dict) for s in steps):
        raise Invalid("Malformed native step outcomes")


def check_urls(steps,start):
    """A redirect or fixture interaction cannot silently escape the declared origin."""
    source=urlsplit(start)
    for step in steps:
        after=step.get("after_url")
        if not after:continue
        value=after.get("url") if isinstance(after,dict) else after
        url=urlsplit(value)
        if (url.scheme,url.netloc)!=(source.scheme,source.netloc):
            raise Invalid("Observed navigation escaped the declared origin; result is not accepted")


def review(value, frozen, tools):
    """Apply installed click-path and loop rules, explicitly without an independent model."""
    d, result = native(value, frozen["scenario"])
    steps = [{k: s.get(k) for k in ("step_id", "action", "status", "error")} for s in result["steps"]]
    complete = result.get("completeness", {}).get("status") == "complete"
    succeeded = complete and all(s["status"] == "completed" for s in steps)
    events = result.get("events", {}).get("items", [])
    errors = [e for e in events if e.get("kind") == "page-error" or (isinstance(e.get("status"), int) and e["status"] >= 500)]
    return {"mode": "DETERMINISTIC_SKILL_RULE_REVIEW", "status": "SUCCEEDED" if succeeded else "INCOMPLETE",
            "rea_evidence_id": d["evidence_id"], "native_sha256": digest(value), "skills": tools["skills"],
            "app_id": frozen["app_id"], "manifest_version": frozen["manifest_version"],
            "task_source": frozen["task_source"], "scope_hash": frozen["scope_hash"], "scope_mode": frozen["mode"],
            "confirmed": {"steps": steps, "completeness": result.get("completeness"), "observed_error_events": errors},
            "hypotheses": ["Uncompleted declared actions may prevent reaching the intended value moment"] if not succeeded else [],
            "counterargument": "A bounded replay cannot establish user value, representative behavior or PMF even when every step completes.",
            "next_test": "Declare one observable first-value state; verify that all steps complete and that state appears in a new isolated replay.",
            "gaps": ["No independent model critique", "No authenticated production journey", "No consented cohort or causal outcome evidence"],
            "native_limits": d.get("limitations", []) + result.get("limitations", []),
            "readiness_authority": False, "publication_authority": False, "pmf": "UNPROVEN"}
