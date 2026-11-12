"""Owner-only combined review; existing independent scopes retain execution authority."""

from datetime import datetime, timezone
import json

from .automation_requirements import social_account, workflow_catalog
from .campaign_contract import (
    SCOPE_FIELDS,
    post_data,
    hashes,
    target_countries,
    whole,
    numeric,
)
from .campaign_schedule import item_status, check_paid_review
from .campaign_execution import scope_view
from .common import Invalid, digest, iso_time
from .complete_automation import policy_view
from .db import connection
from .marketing_agent_manifest import operating_manifest
from .operation_catalog import exact_keys, path_segment
from .review_access import member
from .social_contract import reference

FIELDS = (
    "manifest_version",
    "workflow_policy_id",
    "campaign_scope_id",
    "schedule_batch_id",
)
UNCERTAIN = (
    "UNKNOWN",
    "DISPATCHED",
    "DISPATCHING",
    "RUNNING",
    "CANCEL_REQUESTED",
    "VERIFYING",
    "ACKNOWLEDGED",
    "NEEDS_RECONCILIATION",
)


def selection(body):
    """Accept exact existing resource references, never new authority choices."""
    exact_keys(body, FIELDS, ("draft_posts",))
    if type(body["manifest_version"]) is not int or body["manifest_version"] < 1:
        raise Invalid("Use the current app manifest version")
    selected = [body[name] for name in FIELDS[1:] if body[name] is not None]
    if not selected:
        raise Invalid("Select at least one existing automation resource")
    for identity in selected:
        reference(identity)
    if "draft_posts" in body:
        posts = body["draft_posts"]
        if (
            body["campaign_scope_id"] is None
            or body["schedule_batch_id"] is not None
            or not isinstance(posts, list)
            or not 1 <= len(posts) <= 20
        ):
            raise Invalid("Select one draft campaign and one to twenty exact posts")
        return dict(body, draft_posts=[post_data(post) for post in posts])
    return dict(body)


def saved_object(raw):
    """Malformed saved state needs repair without reflecting its contents."""
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        raise Invalid("Saved agreement resource needs repair") from None
    if not isinstance(value, dict):
        raise Invalid("Saved agreement resource needs repair")
    return value


def owned(db, table, app_id, identity, principal):
    """Only fixed internal table names reach this owner-filtered read."""
    if table not in (
        "automation_policies",
        "campaign_scopes",
        "campaign_schedule_batches",
    ):
        raise Invalid("Unsupported agreement resource")
    row = db.execute(
        "SELECT * FROM " + table + " WHERE app_id=? AND id=? AND owner=?",
        (app_id, identity, principal),
    ).fetchone()
    if row is None:
        raise Invalid("Selected automation resource is unavailable for this owner")
    return row


def local_scope(db, app_id, principal, identity, observed):
    """Reuse the existing policy view and preserve blocked saved authority."""
    if identity is None:
        return None
    row = owned(db, "automation_policies", app_id, identity, principal)
    view = policy_view(db, row, observed)
    summary = view["summary"]
    if summary is not None:
        inventory = summary["inventory"]
        if inventory["app"]["id"] != app_id or inventory["owner"]["principal"] != principal:
            raise Invalid("Local policy summary ownership changed")
    return dict(
        id=view["id"],
        version=view["version"],
        status=view["status"],
        effective_status=view["effective_status"],
        summary_hash=row["summary_hash"],
        summary=view["summary"],
        usage=view["usage"],
        repair=view["repair"],
        executions=view["executions"],
        spend_limit_minor=0,
        price="UNKNOWN",
        protected_access="REVALIDATE_AT_DISPATCH",
    )


def campaign_blockers(scope, row, app, owner, account, observed):
    """Saved approval is separate from current credentials and provider readback."""
    checks = [
        (scope["status"] != "ACTIVE", "CAMPAIGN_SCOPE_" + scope["status"]),
        (iso_time(scope["permission_expires_at"]) <= observed, "CAMPAIGN_SCOPE_EXPIRED"),
        (
            (scope["app_version"], scope["app_hash"]) != (app["version"], digest(app["data"])),
            "CAMPAIGN_APP_CHANGED",
        ),
        (
            (scope["owner_version"], row["owner_version"]) != (owner["version"], owner["version"]),
            "CAMPAIGN_OWNER_CHANGED",
        ),
        (
            (account["version"], account["destination_id"], account["provider"])
            != (scope["connection_version"], scope["page_id"], "facebook"),
            "CAMPAIGN_CONNECTION_CHANGED",
        ),
        (account["status"] != "TESTED_FRESH", "CAMPAIGN_ACCOUNT_" + account["status"]),
        (row["calls"] >= scope["max_calls"], "CAMPAIGN_CALL_ALLOWANCE_EXHAUSTED"),
    ]
    return [reason for failed, reason in checks if failed]


def campaign_receipts(db, app_id, scope_id):
    """Return only durable public receipt identities and states, never raw results."""
    posts = [
        dict(row, kind="POST")
        for row in db.execute(
            "SELECT id,request_id,request_hash,content_hash,rights_hash,status,remote_id,updated FROM campaign_intents WHERE app_id=? AND scope_id=? ORDER BY id",
            (app_id, scope_id),
        )
    ]
    ads = [
        dict(row, kind="AD")
        for row in db.execute(
            "SELECT id,request_id,request_hash,currency,commitment,status,ids,updated FROM campaign_paid_intents WHERE app_id=? AND scope_id=? ORDER BY id",
            (app_id, scope_id),
        )
    ]
    for receipt in ads:
        ids = saved_object(receipt["ids"])
        if set(ids) - {"campaign", "adset", "creative", "ad"}:
            raise Invalid("Saved paid receipt identities need repair")
        receipt["ids"] = {kind: numeric(identity) for kind, identity in ids.items()}
    return posts + ads


def campaign_scope(db, app, owner, identity, observed):
    """Project exact existing approval and current selected account in this snapshot."""
    if identity is None:
        return None
    row = owned(db, "campaign_scopes", app["id"], identity, owner["principal"])
    raw = saved_object(row["summary"])
    if digest(raw) != row["summary_hash"]:
        raise Invalid("Campaign summary integrity changed")
    exact_keys(
        raw,
        (
            *SCOPE_FIELDS,
            "app_id",
            "app_hash",
            "app_version",
            "owner_principal",
            "owner_version",
            "connection_version",
            "billing_notice",
            "rights_notice",
        ),
        ("extended_expiry_consent",),
    )
    if "extended_expiry_consent" in raw and type(raw["extended_expiry_consent"]) is not bool:
        raise Invalid("Campaign expiry consent needs repair")
    if raw["app_id"] != app["id"] or raw["owner_principal"] != owner["principal"]:
        raise Invalid("Campaign summary ownership changed")
    scope = scope_view(db, row)
    account = social_account(db, app["id"], raw["connection_id"], observed)
    blockers = campaign_blockers(scope, row, app, owner, account, observed)
    receipts = campaign_receipts(db, app["id"], identity)
    return dict(
        id=identity,
        status=row["status"],
        approval_hash=row["summary_hash"],
        permission_expires_at=scope["permission_expires_at"],
        consent_revision=scope["consent_revision"],
        approval={
            key: raw[key]
            for key in (
                *SCOPE_FIELDS,
                "app_version",
                "app_hash",
                "owner_version",
                "connection_version",
            )
        }
        | ({"extended_expiry_consent": raw["extended_expiry_consent"]} if "extended_expiry_consent" in raw else {}),
        account=account,
        blockers=blockers,
        receipts=receipts,
        effective_status="BLOCKED" if blockers else "ACTIVE",
        commitment_held_minor=sum(r["commitment"] for r in receipts if r["kind"] == "AD"),
        provider_readback="NOT_PERFORMED",
        billing_notice=raw["billing_notice"],
        rights_notice=raw["rights_notice"],
    )


def batch_row(db, app_id, principal, identity):
    """Bind selected batch to its stored immutable summary before resolving dependencies."""
    if identity is None:
        return None, None
    row = owned(db, "campaign_schedule_batches", app_id, identity, principal)
    summary = saved_object(row["summary"])
    exact_keys(
        summary,
        ("batch_id", "app_id", "owner", "scope_id", "scope_hash", "items"),
        ("permission_expires_at",),
    )
    if digest(summary) != row["summary_hash"]:
        raise Invalid("Scheduled batch summary integrity changed")
    if (
        summary["batch_id"],
        summary["app_id"],
        summary["owner"],
        summary["scope_id"],
    ) != (row["id"], app_id, principal, row["scope_id"]):
        raise Invalid("Scheduled batch ownership changed")
    return row, summary


def batch_item(db, app_id, row, expected, scope, permission_expires_at):
    """Validate exact post bytes and due binding while permitting historical due times."""
    body = saved_object(row["body"])
    fields = ("item_id", "due_at", "request", "operation") if "operation" in body else ("item_id", "due_at", "request")
    exact_keys(body, fields)
    if digest(body) != row["body_hash"] or body != expected or body["item_id"] != row["id"]:
        raise Invalid("Scheduled post integrity changed")
    if row["due"] != iso_time(body["due_at"]).timestamp():
        raise Invalid("Scheduled post due time changed")
    post = scheduled_request(db, app_id, body, scope, permission_expires_at)
    approval = scope["approval"]
    if (
        post["content_hash"] not in approval["approved_content_hashes"]
        or post["rights_hash"] not in approval["approved_rights_hashes"]
    ):
        raise Invalid("Scheduled post is outside campaign approval")
    if iso_time(body["due_at"]) >= iso_time(permission_expires_at):
        raise Invalid("Scheduled post exceeds campaign expiry")
    job = (
        db.execute("SELECT app_id,action,status,data FROM jobs WHERE id=?", (row["job_id"],)).fetchone()
        if row["job_id"]
        else None
    )
    return item_view(db, app_id, row, body, job, scope["id"])


def scheduled_request(db, app_id, body, scope, permission_expires_at):
    """Validate saved historical requests without requiring a future ad end time."""
    operation = body.get("operation", "campaign.publish")
    if operation == "campaign.publish":
        return post_data(body["request"])
    if operation != "campaign.ad-launch":
        raise Invalid("Unsupported scheduled campaign operation")
    request = body["request"]
    exact_keys(
        request,
        (
            "request_id",
            "post_id",
            "content_hash",
            "rights_hash",
            "targeting_hash",
            "lifetime_budget_minor",
            "end_time",
            "targeting",
            "name",
        ),
    )
    reference(request["request_id"])
    hashes(
        [request[key] for key in ("content_hash", "rights_hash", "targeting_hash")],
        True,
    )
    target_countries(request)
    whole(request["lifetime_budget_minor"], 1, 100000000)
    check_paid_review(
        db,
        app_id,
        dict(scope["approval"], permission_expires_at=permission_expires_at),
        request,
        iso_time(body["due_at"]),
    )
    return request


def item_view(db, app_id, row, body, job, scope_id):
    """Preserve exact job/request linkage without exporting private job results."""
    if row["job_id"]:
        expected = dict(
            batch_id=row["batch_id"],
            item_id=row["id"],
            scope_id=scope_id,
            request=body["request"],
        )
        operation = body.get("operation", "campaign.publish")
        if "operation" in body:
            expected["operation"] = operation
        action = "campaign_ad" if operation == "campaign.ad-launch" else "campaign_post"
        if job is None or job["app_id"] != app_id or job["action"] != action or saved_object(job["data"]) != expected:
            raise Invalid("Scheduled job binding changed")
    status = item_status(db, app_id, scope_id, row)
    return dict(body, input_hash=row["body_hash"], **status)


def captured_permission_expiry(summary, scope):
    """Resolve the batch's admission-time deadline within current campaign authority."""
    permission_expires_at = summary.get("permission_expires_at", scope["approval"]["expires_at"])
    if iso_time(permission_expires_at) > iso_time(scope["permission_expires_at"]):
        raise Invalid("Scheduled permission exceeds campaign authority")
    return permission_expires_at


def batch_scope(db, app_id, row, summary, scope, observed):
    """Review every saved item; a changed dependency blocks the combined review."""
    if row is None:
        return None
    if summary["scope_hash"] != scope["approval_hash"]:
        raise Invalid("Scheduled campaign approval changed")
    permission_expires_at = captured_permission_expiry(summary, scope)
    rows = db.execute(
        "SELECT * FROM campaign_schedule_items WHERE batch_id=? ORDER BY due,id",
        (row["id"],),
    ).fetchall()
    expected = {item["item_id"]: item for item in summary["items"]}
    if not 1 <= len(rows) <= 20 or len(rows) != len(expected) or len(expected) != len(summary["items"]):
        raise Invalid("Scheduled item set changed")
    items = [batch_item(db, app_id, item, expected.get(item["id"]), scope, permission_expires_at) for item in rows]
    blockers = list(scope["blockers"])
    if iso_time(permission_expires_at) <= observed:
        blockers.append("SCHEDULE_PERMISSION_EXPIRED")
    if row["status"] != "ACTIVE":
        blockers.append("SCHEDULE_BATCH_" + row["status"])
    if any(item["effective_status"] in ("BLOCKED", "NEEDS_RECONCILIATION") for item in items):
        blockers.append("SCHEDULE_ITEM_NEEDS_REVIEW")
    return dict(
        id=row["id"],
        version=row["version"],
        status=row["status"],
        summary_hash=row["summary_hash"],
        scope_id=row["scope_id"],
        scope_hash=summary["scope_hash"],
        permission_expires_at=permission_expires_at,
        items=items,
        blockers=blockers,
        effective_status="BLOCKED" if blockers else "ACTIVE",
    )


def uncertainty(local, campaign, batch):
    """Unknown dispatch is a reconciliation requirement, never automatic retry authority."""
    states = [r["status"] for r in (local or {}).get("executions", [])]
    states += [r["status"] for r in (campaign or {}).get("receipts", [])]
    states += [r["job_status"] for r in (batch or {}).get("items", [])]
    states += [r["effective_status"] for r in (batch or {}).get("items", [])]
    return any(state in UNCERTAIN or str(state).startswith("PENDING_") for state in states)


class Agreement:
    """Read one consistent app-owner snapshot without service initialization or effects."""

    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self, app_id, user, body):
        """Return an exact combined review without approving any selected scope."""
        path_segment(app_id)
        chosen = selection(body)
        observed = self.clock()
        with connection(self.store.path) as db:
            db.execute("BEGIN")
            owner = member(db, app_id, user["principal"], "OWNER")
            row = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
            if row is None or row["version"] != chosen["manifest_version"]:
                raise Invalid("App manifest changed; reload the agreement")
            app = dict(id=app_id, version=row["version"], data=saved_object(row["data"]))
            summary = build_summary(db, app, owner, chosen, observed)
        blocked = summary["blocked"]
        return dict(
            status="warning" if blocked else "success",
            summary=summary,
            summary_hash=digest(summary),
            observed_at=observed.isoformat(),
            authority_issued=False,
            next_actions=["Inspect each scope and reconcile uncertain work before requesting changes."],
            artifacts=[],
        )


def build_summary(db, app, owner, chosen, observed):
    """Keep every selected family visible and independent in a hash-bound owner review."""
    row, saved = batch_row(db, app["id"], owner["principal"], chosen["schedule_batch_id"])
    campaign_id = chosen["campaign_scope_id"]
    if row is not None:
        if campaign_id is not None and campaign_id != row["scope_id"]:
            raise Invalid("Selected schedule and campaign scope differ")
        campaign_id = row["scope_id"]
    local = local_scope(db, app["id"], owner["principal"], chosen["workflow_policy_id"], observed)
    campaign = campaign_scope(db, app, owner, campaign_id, observed)
    draft_posts = chosen.get("draft_posts")
    if draft_posts is not None:
        approval = campaign["approval"]
        if (
            campaign["status"] != "DRAFT"
            or approval["ad_account_id"] is not None
            or len(draft_posts) > approval["max_posts"]
        ):
            raise Invalid("Use the current draft organic campaign scope")
        if any(
            post["content_hash"] not in approval["approved_content_hashes"]
            or post["rights_hash"] not in approval["approved_rights_hashes"]
            for post in draft_posts
        ):
            raise Invalid("Draft post differs from the saved campaign scope")
        campaign["draft_posts"] = draft_posts
    batch = batch_scope(db, app["id"], row, saved, campaign, observed)
    uncertain = uncertainty(local, campaign, batch)
    blocked = uncertain or any(value and value["effective_status"] != "ACTIVE" for value in (local, campaign, batch))
    return dict(
        schema="wmm.automation-agreement.v1",
        selection={name: chosen[name] for name in FIELDS},
        app=dict(id=app["id"], version=app["version"], hash=digest(app["data"])),
        owner=dict(principal=owner["principal"], role_version=owner["version"]),
        policy_sha256=digest(operating_manifest(app)),
        catalog_sha256=workflow_catalog()["sha256"],
        local_work=local,
        campaign=campaign,
        schedule=batch,
        blocked=bool(blocked),
        dispatch_uncertain=uncertain,
        execution_authority=False,
        classification="COMBINED_REVIEW_ONLY_INDEPENDENT_SCOPES",
        pricing=dict(
            inference="UNKNOWN",
            fees_and_taxes="EXCLUDED_FROM_MEDIA_CEILING",
            provider_reporting="MAY_LAG",
        ),
        credential_validation="SAVED_PUBLIC_FACTS_ONLY_REVALIDATE_PROTECTED_ACCESS_AND_PROVIDER_AT_DISPATCH",
        stop_rules=[
            "OFF, revoked owner or grant",
            "Expiry, changed source or resource revisions",
            "Allowance or approved media ceiling exhausted",
            "Uncertain dispatch: reconcile before retry",
        ],
        revocation="Use each scope OFF control; dispatched effects and incurred charges remain recorded.",
    )
