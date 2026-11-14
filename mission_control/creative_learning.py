"""Compose saved discovery, briefs, renders, publication and learning into one loop."""

from typing import Any

from .common import digest


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        value = value.get("items") or value.get("report") or value.get("programs") or []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _status(item: Any) -> str:
    return (item.get("status") or item.get("state") or "UNKNOWN") if isinstance(item, dict) else "UNKNOWN"


def summary(workspace: Any) -> dict[str, Any]:
    """Read the existing loop state without creating, rendering or publishing anything."""
    briefs = _items(workspace.get("briefs"))
    rankings = []
    for report in _items(workspace.get("rankings")):
        if report.get("input_status") != "CURRENT":
            continue
        data = (report.get("current") or {}).get("data") or {}
        slate = data.get("slate") or []
        if slate:
            rankings.append({"reference_id": slate[0]})
    renders = _items(workspace.get("renders"))
    hypit = _items(workspace.get("hypit_renders"))
    actions = [
        job["result"]
        for job in _items(workspace.get("jobs"))
        if job.get("action") == "social_publication"
        and isinstance(job.get("result"), dict)
        and job["result"].get("status") == "PUBLISHED"
        and job["result"].get("receipt_hash")
    ]
    experiments = _items(workspace.get("experiments"))
    learning = workspace.get("learning") or {}
    programs = _items(learning.get("programs"))
    active = next((item for item in programs if item.get("active")), None)
    published = list({item["id"]: item for item in actions if item.get("id")}.values())
    render_items = [item for item in renders + hypit if _status(item) == "CURRENT"]
    measured = []
    for item in experiments:
        assessments = _items(item.get("assessments"))
        latest = (assessments[-1].get("data") or {}) if assessments else {}
        if item.get("state") in ("EVALUATED", "DECIDED") and latest.get("status") == "EVALUATED":
            measured.append(item)
    if not briefs and not rankings and not render_items:
        status = "NO_INPUT"
    elif not render_items:
        status = "BRIEF_READY" if briefs else "RESEARCH_READY"
    elif not published:
        status = "RENDER_READY"
    elif not measured:
        status = "PUBLICATION_OBSERVED"
    else:
        status = "LEARNING_ACTIVE" if active else "OUTCOME_RECORDED"
    gaps = []
    if not workspace.get("references"):
        gaps.append("Add or discover a creative reference")
    if not briefs:
        gaps.append("Prepare a production brief")
    if not rankings:
        gaps.append("Rank current creative inputs")
    if not render_items:
        gaps.append("Render at least one approved variant")
    if not published:
        gaps.append("Record a publication readback")
    if not measured:
        gaps.append("Collect mature outcome evidence")
    if not active:
        gaps.append("Propose a learning program from observed outcomes")
    top = rankings[0] if rankings else None
    pattern = None
    if active:
        definition = (active.get("data") or {}).get("definition") or {}
        pattern = definition.get("pattern")
    next_brief = dict(
        source_id=(top or {}).get("reference_id") or (top or {}).get("source_id"),
        learning_pattern=pattern,
        missing=gaps,
        seed=(
            "Brief the top-ranked source" + (" using the active creative method: " + pattern if pattern else "")
            if top
            else "Add a ranked source before briefing"
        ),
    )
    return dict(
        schema="wmm.closed-creative-learning.v1",
        status=status,
        counts=dict(
            references=len(workspace.get("references") or []),
            analyses=len(workspace.get("analyses") or []),
            briefs=len(briefs),
            ranked=len(rankings),
            renders=len(render_items),
            publications=len(published),
            measured=len(measured),
            learning_programs=len(programs),
        ),
        learned=dict(
            active_program=(active or {}).get("id"),
            active_state=(active or {}).get("state"),
            active_pattern=pattern,
            evaluation=(active or {}).get("data", {}).get("evaluation"),
            uses=len(learning.get("uses") or []),
            top_ranked=top,
        ),
        next_brief=next_brief,
        gaps=gaps,
        input_sha256=digest(
            dict(
                status=status,
                briefs=[item.get("id") for item in briefs],
                renders=[item.get("id") for item in render_items],
                published=[item.get("id") for item in published],
                programs=[item.get("id") for item in programs],
            )
        ),
        scope="Saved stages are app-level signals. They do not establish a linked creative experiment or any new authority.",
    )
