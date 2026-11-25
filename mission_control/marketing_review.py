"""Closed owner-only local marketing review operations shared by HTTP and gateway."""

import json
from typing import Any, cast

from . import mini_demo
from .campaign_access import identity, scope_owner
from .campaign_owner_reports import owned_resource
from .campaign_stale_claims import review, source_snapshot, verify_public
from .common import Invalid, digest, iso_time, now, required, safe_data
from .db import connection
from .marketing_effort import validate
from .marketing_review_store import save
from .pmf_contract import exact
from .social_contract import reference

FIELDS = {
    "index-artifact": {"scope_id", "id", "url", "approved_claim_text", "claim_ids", "published_at"},
    "claims": {"scope_id"},
    "check-artifact": {"scope_id", "id", "hash"},
    "effort": {
        "scope_id",
        "id",
        "occurred_at",
        "checks_run",
        "reviews_completed",
        "minutes",
        "evidence_sha256",
        "note",
    },
    "change": {"scope_id", "id", "title", "shipped_at", "shipment_sha256", "claim_ids"},
    "topics": {"scope_id"},
    "prepare-demo": {
        "scope_id",
        "id",
        "change_id",
        "change_hash",
        "brief_id",
        "brief_hash",
        "hook_review",
        "study_id",
        "study_hash",
        "channel",
    },
    "demo-status": {"scope_id", "id", "hash", "publication_id"},
    "retention": {
        "scope_id",
        "id",
        "demo_id",
        "demo_hash",
        "source_id",
        "days",
        "observed_at",
        "coverage_from",
        "coverage_through",
        "complete",
        "source_event_count",
        "source_receipt_sha256",
        "events",
    },
}


def dispatch(store: Any, app: str, action: str, body: dict) -> dict:
    """Current owner admission, exact source scope, immutable local evidence only."""
    if action not in FIELDS:
        raise Invalid("Unknown marketing review operation")
    exact(body, FIELDS[action])
    safe_data(body)
    context, principal = identity(store, app)
    if "principal" not in context and not (context.get("grant_id") and context.get("review")):
        raise PermissionError("Marketing review requires a current owner or independently reviewed exact request")
    if json.loads(cast(str, context["envelope"])) != dict(
        app_id=app, operation="marketing-review." + action, input=body
    ):
        raise PermissionError("Marketing review differs from the exact admitted operation")
    owner = scope_owner(store, context, principal)
    reference(body["scope_id"])
    if "id" in body:
        reference(body["id"])
    # Public fetching is explicit, bounded, credential-free, and outside SQLite writes.
    if action == "check-artifact":
        with connection(store.path) as db:
            owned_resource(db, "campaign_scopes", app, owner, body["scope_id"])
            artifact = mini_demo._saved(db, app, owner, body["scope_id"], "ARTIFACT", body["id"], body["hash"])
        result = verify_public(artifact["data"]["url"], artifact["data"]["approved_claim_text"])
        identity(store, app)
        return dict(
            artifact_id=artifact["id"], artifact_hash=artifact["hash"], observation=result, automatic_changes=False
        )
    with connection(store.path, write=True) as db:
        owned_resource(db, "campaign_scopes", app, owner, body["scope_id"])
        scope = body["scope_id"]
        if action == "index-artifact":
            from .aeo_transport import public_url

            url = public_url(body["url"], allow_tracking=True)
            stamp = iso_time(body["published_at"])
            if stamp > iso_time(now()):
                raise Invalid("A future artifact is not published")
            source = source_snapshot(db, app, body["claim_ids"])
            return save(
                db,
                app,
                owner,
                "ARTIFACT",
                body["id"],
                scope,
                dict(
                    url=url,
                    approved_claim_text=required(body["approved_claim_text"], "Exact approved wording", 20000),
                    source=source,
                    source_sha256=digest(source),
                    published_at=stamp.isoformat(),
                    provenance="OWNER_RECORDED_NOT_PROVIDER_VERIFIED",
                ),
            )
        if action == "claims":
            return review(db, app, owner, scope)
        if action == "effort":
            data = validate(body)
            if iso_time(data["occurred_at"]) > iso_time(now()):
                raise Invalid("Future effort is not completed work")
            return save(db, app, owner, "EFFORT", body["id"], scope, data)
        if action == "change":
            return mini_demo.change(db, app, owner, scope, body)
        if action == "topics":
            return mini_demo.topics(db, app, owner, scope)
        if action == "prepare-demo":
            return mini_demo.prepare(db, store, app, owner, scope, body)
        if action == "demo-status":
            return mini_demo.status(db, store, app, owner, scope, body)
        from .mini_demo_retention import assess

        demo = mini_demo._saved(db, app, owner, scope, "DEMO", body["demo_id"], body["demo_hash"])
        result = assess(db, app, demo, body)
        return save(db, app, owner, "RETENTION", body["id"], scope, dict(inputs=body, report=result))


def _dispatch_envelope(service, envelope, caller):
    """Preserve the exact owner or reviewed-agent admission before dispatch."""
    from .operation_authority import REQUEST, protected

    context = REQUEST.get()
    reviewed_agent = caller == "SCOPED_AGENT" and context and context.get("grant_id") and context.get("review")
    if caller != "LOCAL_SESSION" and not reviewed_agent:
        raise PermissionError("Marketing review requires a current owner or independently reviewed exact request")
    with protected(service.store, envelope):
        return dispatch(service.store, envelope["app_id"], envelope["operation"].split(".")[1], envelope["input"])
