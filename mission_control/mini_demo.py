"""Shipped-change mini-demo preparation reuses briefs, render jobs and studies."""

from sqlite3 import Connection
from typing import Any

from .campaign_stale_claims import source_snapshot
from .common import Invalid, digest, iso_time, now, required
from .creative_analysis import latest
from .creative_briefs import stale_findings
from .marketing_review_store import decoded, rows, save
from .observational_campaign import _app, _study, report_in_snapshot
from .observational_campaign_contract import tagged_url
from .pmf_contract import exact, hashed


def change(db: Connection, app: str, owner: str, scope: str, body: dict) -> dict:
    """Record owner-supplied shipment evidence with explicit claim lineage."""
    stamp = iso_time(body["shipped_at"])
    if stamp > iso_time(now()):
        raise Invalid("A future change is not shipped")
    ids = body["claim_ids"]
    if not isinstance(ids, list) or not ids:
        raise Invalid("Choose current claim evidence for the shipped change")
    source = source_snapshot(db, app, ids)
    return save(
        db,
        app,
        owner,
        "CHANGE",
        body["id"],
        scope,
        dict(
            title=required(body["title"], "Shipped feature", 500),
            shipped_at=stamp.isoformat(),
            shipment_sha256=hashed(body["shipment_sha256"]),
            source=source,
            provenance="OWNER_SUPPLIED_SHIPMENT_EVIDENCE_NOT_INDEPENDENTLY_VERIFIED",
        ),
    )


def topics(db: Connection, app: str, owner: str, scope: str) -> dict:
    """Suggest only evidence-bound current changes, with stale candidates visible."""
    suggestions = []
    for row in rows(db, app, owner, scope, "CHANGE"):
        data = row["data"]
        try:
            current = source_snapshot(db, app, list(data["source"]["claims"])) == data["source"]
        except Invalid:
            current = False
        recent = 0 <= (iso_time(now()) - iso_time(data["shipped_at"])).total_seconds() <= 30 * 86400
        suggestions.append(
            dict(
                change_id=row["id"],
                change_hash=row["hash"],
                title=data["title"],
                shipped_at=data["shipped_at"],
                status="TOPIC_FOR_REVIEW" if current and recent else "STALE_SOURCE" if not current else "OLDER_CHANGE",
                source_sha256=digest(data["source"]),
            )
        )
    return dict(
        topics=suggestions,
        authority_issued=False,
        limits="Suggestions from recorded shipment evidence; never proof that a feature works or that video will perform.",
    )


def _saved(db: Connection, app: str, owner: str, scope: str, kind: str, identity: str, fingerprint: str) -> dict:
    row = db.execute(
        "SELECT * FROM marketing_review_evidence WHERE app_id=? AND owner=? AND scope_id=? AND kind=? AND id=?",
        (app, owner, scope, kind, identity),
    ).fetchone()
    value = decoded(row)
    if value["hash"] != hashed(fingerprint):
        raise Invalid("Selected marketing source changed")
    return value


def hook_review(value: dict, brief_hash: str) -> dict:
    """An explicit honest first-ten-seconds review, not a predicted attention score."""
    exact(value, {"audience", "problem", "reason_to_watch", "opening_end_seconds", "brief_hash", "reviewed"})
    if value["reviewed"] is not True or value["brief_hash"] != brief_hash:
        raise Invalid("Review the hook for this exact creative before approval")
    seconds = value["opening_end_seconds"]
    if type(seconds) not in (int, float) or not 0 < seconds <= 10:
        raise Invalid("The hook must establish audience, problem and reason to watch within ten seconds")
    return dict(
        **{
            key: required(value[key], key.replace("_", " "), 2000) for key in ("audience", "problem", "reason_to_watch")
        },
        opening_end_seconds=seconds,
        brief_hash=brief_hash,
        reviewed=True,
    )


def prepare(db: Connection, store: Any, app: str, owner: str, scope: str, body: dict) -> dict:
    """Freeze a source-bound pipeline, without rendering, approval or publication."""
    changed = _saved(db, app, owner, scope, "CHANGE", body["change_id"], body["change_hash"])
    data = changed["data"]
    if source_snapshot(db, app, list(data["source"]["claims"])) != data["source"]:
        raise Invalid("Shipped-change claims are stale; review the current product first")
    brief = latest(db, "creative_briefs", app, body["brief_id"])
    if brief["hash"] != hashed(body["brief_hash"]) or stale_findings(db, store, app, brief["data"]):
        raise Invalid("Select an exact current proof-bound video brief")
    definition = brief["data"]["definition"]
    if definition["channel"] != "SHORT_VIDEO" or not set(data["source"]["claims"]).issubset(definition["claim_ids"]):
        raise Invalid("Video brief must demonstrate the selected shipped feature claims")
    hook = hook_review(body["hook_review"], brief["hash"])
    context = _app(db, app)
    study = _study(db, app, body["study_id"], body["study_hash"], context)
    if study["data"]["creative_id"] != brief["id"] or study["data"]["source"] != body["channel"]:
        raise Invalid("Use one registered channel and exact creative for this mini-demo")
    link = tagged_url(context["data"].get("website"), study["data"])
    result = dict(
        change_id=changed["id"],
        change_hash=changed["hash"],
        brief_id=brief["id"],
        brief_hash=brief["hash"],
        hook_review=hook,
        channel=body["channel"],
        study_id=study["id"],
        study_hash=study["hash"],
        tagged_link=link,
        capture_assets=brief["data"]["content"]["screens"],
        captions=brief["data"]["content"]["captions"],
        state="PREPARED_NOT_APPROVED",
        authority_issued=False,
    )
    return save(db, app, owner, "DEMO", body["id"], scope, result)


def status(db: Connection, store: Any, app: str, owner: str, scope: str, body: dict) -> dict:
    """Reconcile actual saved render evidence; never equate a plan with a post."""
    demo = _saved(db, app, owner, scope, "DEMO", body["id"], body["hash"])
    data = demo["data"]
    brief = latest(db, "creative_briefs", app, data["brief_id"])
    changed = _saved(db, app, owner, scope, "CHANGE", data["change_id"], data["change_hash"])
    current = (
        brief["hash"] == data["brief_hash"]
        and not stale_findings(db, store, app, brief["data"])
        and source_snapshot(db, app, list(changed["data"]["source"]["claims"])) == changed["data"]["source"]
    )
    context = _app(db, app)
    study = _study(db, app, data["study_id"], data["study_hash"], context)
    render = None
    for row in db.execute("SELECT * FROM hypit_renders WHERE app_id=? ORDER BY created DESC", (app,)):
        from .hypit_jobs import saved as render_decoded

        candidate = render_decoded(row)
        if digest(candidate["data"]) != candidate["hash"]:
            raise Invalid("Rendered demo evidence integrity changed")
        if candidate["data"]["inputs"]["request"]["brief_hash"] == data["brief_hash"]:
            from .hypit_jobs import artifact_file

            artifact_file(store, app, candidate["id"])
            render = dict(id=candidate["id"], hash=candidate["hash"], artifact=candidate["data"]["artifact"])
            break
    publication = None
    publication_id = body["publication_id"]
    if publication_id is not None:
        from .publication_authority import _row as authority_row
        from .publication_authority import _view as authority_view
        from .publication_contract import channel_descriptor
        from .publication_reports import _intent

        authority, draft, _binding = authority_row(db, app, publication_id)
        if authority["owner"] != owner or draft["provider"] != data["channel"]:
            raise PermissionError("Publication belongs to another owner or channel")
        if not render or draft["artifact"] != dict(id=render["id"], sha256=render["artifact"]["sha256"]):
            raise Invalid("Publication must use this mini-demo's rendered bytes")
        if draft["link"] != data["tagged_link"]:
            raise Invalid("Publication must preserve this exact creative's tagged link")
        publication, _events = _intent(db, app, authority_view(authority), digest(channel_descriptor(draft)), draft)
    verified = bool(publication and publication["phase"] == "PUBLISHED" and publication["remote_id"])
    # Existing publication review retains destination, rights, timing and rendered bytes.
    # It cannot be skipped by the preparation API or by a hook review.
    steps = [
        dict(id="feature", assignee=owner, prerequisites=[], state="RECORDED", evidence=data["change_hash"]),
        dict(
            id="hook", assignee=owner, prerequisites=["feature"], state="REVIEWED", evidence=digest(data["hook_review"])
        ),
        dict(
            id="capture-render",
            assignee=owner,
            prerequisites=["hook"],
            state="RENDERED" if render else "NOT_RUN",
            evidence=render,
        ),
        dict(
            id="approval-publish",
            assignee=owner,
            prerequisites=["capture-render"],
            state="PUBLISHED" if verified else "SEPARATE_EXACT_APPROVAL_REQUIRED",
            evidence=publication_id,
        ),
        dict(
            id="receipt",
            assignee=owner,
            prerequisites=["approval-publish"],
            state="PROVIDER_RECEIPT_RECORDED" if verified else "NOT_VERIFIED",
            evidence=publication,
        ),
    ]
    return dict(
        demo=demo,
        source_status="CURRENT" if current else "STALE",
        steps=steps,
        render_operation=dict(
            operation="hypit.queue",
            input=dict(
                data=dict(brief_id=data["brief_id"], brief_hash=data["brief_hash"], shape="portrait"),
                request_key=data["study_id"],
            ),
        ),
        measurement=report_in_snapshot(db, app, study, context, now()),
        limits="Preparation and rendering do not approve a post. Attach a matching publication receipt through the existing review flow.",
  )
