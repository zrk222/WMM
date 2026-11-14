"""Compose saved discovery, briefs, renders, publication and learning into one loop."""

from typing import Any

from .common import digest


def _items(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return value.get("items") or value.get("report") or value.get("programs") or []
    return value if isinstance(value, list) else []


def _status(item: Any) -> str:
    return (item.get("status") or item.get("state") or "UNKNOWN") if isinstance(item, dict) else "UNKNOWN"


def summary(workspace: Any) -> dict[str, Any]:
    """Read the existing loop state without creating, rendering or publishing anything."""
    briefs = _items(workspace.get("briefs"))
    rankings = _items(workspace.get("rankings"))
    renders = _items(workspace.get("renders"))
    hypit = _items(workspace.get("hypit_renders"))
    actions = _items(workspace.get("provider_actions"))
    experiments = _items(workspace.get("experiments"))
    learning = workspace.get("learning") or {}
    programs = _items(learning.get("programs"))
    active = next((item for item in programs if item.get("active")), None)
    published = [item for item in actions if _status(item) in ("PUBLISHED", "VERIFIED", "SUCCEEDED", "DELIVERED")]
    render_items = renders + hypit
    measured = [
        item for item in experiments if item.get("assessments") or item.get("state") in ("DECIDED", "OBSERVING")
    ]
    if not briefs and not rankings and not render_items:
        status = "NO_INPUT"
    elif briefs and not render_items:
        status = "BRIEF_READY"
    elif render_items and not published:
        status = "RENDER_READY"
    elif published and not measured:
        status = "PUBLICATION_OBSERVED"
    elif measured and not active:
        status = "OUTCOME_RECORDED"
    else:
        status = "LEARNING_ACTIVE"
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
        scope="Read-only composition of saved local evidence; no new authority, provider read, render or publication.",
    )
