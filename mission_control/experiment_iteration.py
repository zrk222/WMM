"""Deterministic next-test drafts derived from a saved experiment assessment."""

import re

from .common import digest
from .experiment_analysis import ASSIGNMENT_MISMATCH, GUARDRAIL_BREACH


CREATIVE_TWEAKS = {
    "activation_rate": (
        "opening_hook",
        "Open with authentic app footage showing one useful first action, then keep the existing call to action.",
    ),
    "paid_conversion": (
        "call_to_action",
        "Replace the closing call to action with one that names a verified paid feature and points to the same offer.",
    ),
    "retention_rate": (
        "example_use_case",
        "Replace the example with a verified recurring use case, keeping the hook and call to action.",
    ),
}


def iteration_plan(definition, assessment, assessment_hash):
    """Project a local recommendation without changing the source assessment."""
    metric = definition.get("primary_metric")
    metric = metric if isinstance(metric, str) and metric in CREATIVE_TWEAKS else None
    minimum = definition.get("minimum_detectable_effect")
    threshold = minimum if type(minimum) in (int, float) and 0 < minimum < 1 else None
    try:
        bound = digest(definition) == assessment.get("definition_hash") and digest(assessment) == assessment_hash
    except (TypeError, ValueError):
        bound = False
    if not bound:
        action, reason = "REPAIR", "The experiment and assessment fingerprints do not match. Evaluate current evidence."
    elif metric is None or not isinstance(definition.get("control"), dict):
        action, reason = "REPAIR", "The saved experiment is missing its primary metric or control definition."
    else:
        action, reason = classify(assessment, threshold)
    draft = creative_draft(definition) if action == "REVISE" else None
    if action == "REVISE" and draft is None:
        reason += " Review which single variable can be tested before drafting a new variant."
    value = dict(
        schema="wmm.experiment-iteration.v1",
        assessment_hash=assessment_hash,
        definition_hash=assessment.get("definition_hash"),
        primary_metric=metric,
        practical_effect_threshold=threshold,
        decision=action,
        reason=reason,
        draft=draft,
        reported_guardrail_breach=has_guardrail_breach(assessment) if bound else None,
        external_execution="NOT_RUN",
        authority_issued=False,
    )
    return dict(value, iteration_hash=digest(value))


def has_guardrail_breach(assessment):
    findings = assessment.get("guardrail_findings", [])
    return isinstance(findings, list) and any(
        f"{arm} {GUARDRAIL_BREACH}" in findings for arm in ("control", "treatment")
    )


def classify(assessment, threshold):
    state = assessment.get("status")
    issues = assessment.get("issues", [])
    if (
        state not in ("BLOCKED", "INCONCLUSIVE", "EVALUATED")
        or not isinstance(issues, list)
        or not isinstance(assessment.get("guardrail_findings", []), list)
    ):
        return "REPAIR", "The saved comparison diagnostics are invalid. Evaluate current evidence."
    needs_repair = state == "BLOCKED" or ASSIGNMENT_MISMATCH in issues
    if has_guardrail_breach(assessment):
        reason = "A predeclared guardrail was breached. Review the affected arm and its saved stop rule."
        if needs_repair:
            reason += " Resolve the evidence or assignment issue before interpreting the result."
        return "STOP", reason
    if needs_repair:
        return "REPAIR", "Resolve the evidence or assignment issue before changing the experiment."
    if state != "EVALUATED":
        return (
            "COLLECT",
            "Recover missing evidence from the declared window, or preregister a new test if it cannot be recovered.",
        )
    effect = assessment.get("effect")
    if not isinstance(effect, dict) or threshold is None:
        return "REPAIR", "The saved comparison or its practical effect threshold is unavailable."
    bounds = effect.get("interval")
    if (
        not isinstance(bounds, (list, tuple))
        or len(bounds) != 2
        or any(type(value) not in (int, float) or not -1 <= value <= 1 for value in bounds)
        or bounds[0] > bounds[1]
    ):
        return "REPAIR", "The saved comparison interval is invalid. Evaluate current evidence."
    lower, upper = bounds
    if lower >= threshold:
        return (
            "CONTINUE",
            "The observed interval clears the practical threshold. Preregister an untouched holdout to check the pattern.",
        )
    if upper <= -threshold:
        return "REVISE", "Keep the control. The treatment interval is below the practical loss threshold."
    if lower > -threshold and upper < threshold:
        return (
            "REVISE",
            "Keep the control and change one variable. The observed interval stays inside the practical difference band.",
        )
    return (
        "COLLECT",
        "The interval spans a practical threshold. Keep the frozen window and preregister a new sample plan if needed.",
    )


def creative_draft(definition):
    control = definition.get("control", {})
    asset_hash = control.get("creative_sha256")
    tweak = CREATIVE_TWEAKS.get(definition.get("primary_metric"))
    if (
        not tweak
        or control.get("variant_type") == "SUBSCRIPTION"
        or not isinstance(asset_hash, str)
        or not re.fullmatch(r"[0-9a-f]{64}", asset_hash)
    ):
        return None
    variable, change = tweak
    return dict(
        state="DRAFT_FOR_REVIEW",
        control_asset_sha256=asset_hash,
        variable=variable,
        proposed_change=change,
        keep_fixed=["audience", "placement", "offer", "primary_metric"],
        next_step="Check the authentic proof, then register fresh control and treatment cohorts before exposure.",
    )
