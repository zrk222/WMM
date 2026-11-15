"""Pure creative handoffs; a receipt never authorizes an external action."""

import re
from collections.abc import Mapping
from typing import Any

from .common import Invalid, digest, identifier

ENGINES = ("hypit", "rea-video", "genjutsu")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_BINDING = {"app_id", "manifest_version", "source_sha256"}
_ANALYSIS = {"duration_ms", "observed_beats", "interpretation", "analyzer_revision", "analyzer_sha256"}
_VARIANT = {"artifact_sha256", "request_id", "reviewed", "rights_sha256"}


def sha256(value: object) -> bool:
    """Recognize lowercase SHA-256 text."""
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def checked_binding(binding: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the current source identity supplied by the caller."""
    if set(binding) != _BINDING or not sha256(binding["source_sha256"]):
        raise Invalid("Choose the current source and app")
    identifier(binding["app_id"])
    if type(binding["manifest_version"]) is not int or binding["manifest_version"] < 1:
        raise Invalid("Refresh the current app revision")
    return dict(binding)


def bounded_text(value: object, limit: int) -> bool:
    """Require nonempty text within the input limit."""
    return isinstance(value, str) and 0 < len(value.strip()) <= limit and len(value) <= limit


def checked_beat(row: object, previous: int, duration: int) -> dict[str, Any]:
    """Accept one observed timestamp range and its text."""
    if not isinstance(row, dict) or set(row) != {"start_ms", "end_ms", "text"}:
        raise Invalid("Use a start time, end time and observation for each beat")
    start, end = row["start_ms"], row["end_ms"]
    if type(start) is not int or type(end) is not int or not previous <= start < end <= duration:
        raise Invalid("Observed beats must be ordered and within the clip")
    if not bounded_text(row["text"], 500):
        raise Invalid("Describe each observed beat in up to 500 characters")
    return dict(row)


def observations(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Keep timestamp evidence separate from interpretation."""
    duration, rows = payload["duration_ms"], payload["observed_beats"]
    if (
        type(duration) is not int
        or not 1 <= duration <= 180000
        or not isinstance(rows, list)
        or not 1 <= len(rows) <= 60
    ):
        raise Invalid("Choose up to 60 observed beats within a three-minute clip")
    result: list[dict[str, Any]] = []
    previous = 0
    for row in rows:
        beat = checked_beat(row, previous, duration)
        result.append(beat)
        previous = beat["end_ms"]
    return result


def analysis_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an analysis receipt before creating a draft handoff."""
    if set(payload) != _ANALYSIS or not sha256(payload["analyzer_sha256"]):
        raise Invalid("Include the pinned analyzer revision and observed beats")
    revision = payload["analyzer_revision"]
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise Invalid("Include the pinned analyzer Git revision")
    if not bounded_text(payload["interpretation"], 2000):
        raise Invalid("Include a bounded interpretation with its uncertainty")
    return dict(payload, observed_beats=observations(payload))


def variant_data(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Require evidence identifiers and a recorded review for a draft variant."""
    if set(payload) != _VARIANT or payload["reviewed"] is not True:
        raise Invalid("Review the returned creative before handing it to Hypit")
    if not sha256(payload["artifact_sha256"]) or not sha256(payload["rights_sha256"]):
        raise Invalid("Include the draft artifact and rights fingerprints")
    if not bounded_text(payload["request_id"], 200):
        raise Invalid("Include the existing generation request ID")
    return dict(payload)


def handoff(engine: str, binding: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and bind analysis or variant metadata for draft use."""
    normalize = {"rea-video": analysis_data, "genjutsu": variant_data}.get(engine)
    if normalize is None:
        raise Invalid("Choose an analysis or draft-variant handoff")
    body = {"engine": engine, "binding": checked_binding(binding), "data": normalize(payload)}
    return {**body, "sha256": digest(body)}


def current_handoff(engine: str, binding: Mapping[str, Any], receipt: Mapping[str, Any]) -> bool:
    """Reject receipts with foreign bindings or changed data."""
    if set(receipt) != {"engine", "binding", "data", "sha256"} or not isinstance(receipt["data"], dict):
        return False
    try:
        return receipt == handoff(engine, binding, receipt["data"])
    except Invalid:
        return False


def decision_for(state: str) -> str:
    """Expose one actionable step without authorizing any effect."""
    return {
        "OFF": "No action; the other selected tools can continue.",
        "READY_FOR_EXISTING_WORKFLOW": "Use the current Hypit brief and render controls.",
        "LOCAL_ANALYSIS_NEEDED": "Analyze the rights-cleared local clip with the pinned analyzer.",
        "PROVIDER_APPROVAL_NEEDED": "Prepare an exact quote and ask the owner to approve the upload and spend.",
        "DRAFT_METADATA_MATCHES": "Verify the saved source, job, artifact and approval before using this draft.",
    }[state]


def plan(selection: Mapping[str, bool], binding: Mapping[str, Any], receipts: Mapping[str, Any]) -> dict[str, Any]:
    """Plan independent tools without implicitly dispatching or publishing."""
    binding = checked_binding(binding)
    if set(selection) != set(ENGINES) or any(type(value) is not bool for value in selection.values()):
        raise Invalid("Set each creative tool on or off")
    steps: dict[str, str] = {}
    for engine in ENGINES:
        if not selection[engine]:
            steps[engine] = "OFF"
        elif engine == "hypit":
            steps[engine] = "READY_FOR_EXISTING_WORKFLOW"
        else:
            receipt = receipts.get(engine)
            if isinstance(receipt, dict) and current_handoff(engine, binding, receipt):
                steps[engine] = "DRAFT_METADATA_MATCHES"
            else:
                steps[engine] = "LOCAL_ANALYSIS_NEEDED" if engine == "rea-video" else "PROVIDER_APPROVAL_NEEDED"
    return {
        "tools": steps,
        "next_actions": {engine: decision_for(state) for engine, state in steps.items()},
        "external_execution": False,
        "publication": False,
    }
