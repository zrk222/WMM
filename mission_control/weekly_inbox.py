"""Bounded portfolio exceptions over saved workspaces; no external execution."""

import json
from datetime import timedelta

from .common import Invalid, digest, iso_time, now
from .weekly_controls import decision_controls

EXPIRY_HORIZON = timedelta(days=7)

ROUTES = {
    "readiness": "readiness",
    "measurement": "measurement",
    "economics": "results",
    "retention": "retention",
}


def project(workspace):
    """Project only the selected app's evidence, not its credentials or conversations."""
    app = workspace["app"]
    controls = decision_controls(app, workspace["records"], workspace["stages"])
    receipt = dict(
        app_id=app["id"],
        manifest_version=app["version"],
        source_hash=controls["source_hash"],
        observed_at=now(),
    )
    cards = []
    for record in workspace["records"]:
        if (
            record["kind"] == "review"
            and record["data"].get("confirmed") is True
            and record["data"].get("severity") == "P0"
        ):
            cards.append(
                dict(
                    id=digest([app["id"], record["id"], record["hash"]]),
                    category="critical",
                    priority=0,
                    state="NEEDS_REPAIR",
                    title="Resolve confirmed critical finding",
                    reason=record["title"],
                    next_action="Investigate, repair and retest before acquisition.",
                    resolution_route="findings",
                )
            )
    for gate in controls["gates"]:
        if gate["state"] != "LOCAL_INPUTS_READY":
            stage = next(
                (s for s in workspace["stages"] if s["id"] == gate["stage"]), {}
            )
            cards.append(
                dict(
                    id=digest([app["id"], gate["id"], controls["source_hash"]]),
                    category=gate["id"],
                    priority=gate["stage"],
                    state=gate["state"],
                    title=gate["id"].title() + " needs evidence",
                    reason=(
                        stage.get("missing")
                        or ["Current source evidence is unavailable."]
                    )[0],
                    next_action=gate["next_action"],
                    resolution_route=ROUTES[gate["id"]],
                )
            )
    for card in cards:
        card.update(
            app_id=app["id"],
            app_name=app["data"]["name"],
            source_receipt=receipt,
            change="NOT_COMPARED_WITH_PRIOR_REVIEW",
            cost_minor=None,
            owner="App operator",
        )
    workflow = workspace.get("workflow") or {}
    current = workflow.get("next_step")
    stage = next((s for s in workspace.get("stages", []) if s["id"] == current), None)
    sequences = (workspace.get("sequences") or {}).get("history") or []
    return dict(
        app_id=app["id"],
        app_name=app["data"]["name"],
        source_receipt=receipt,
        exceptions=cards,
        local_ready=[
            g["id"] for g in controls["gates"] if g["state"] == "LOCAL_INPUTS_READY"
        ],
        current_stage=dict(
            id=current,
            title=stage["title"] if stage else None,
            next_action=(workflow.get("next_action") or {}).get("title"),
        ),
        high_priority_gaps=sum(len(s.get("critical_findings", [])) for s in workflow.get("steps", [])),
        active_sequences=sum(1 for r in sequences if r.get("state") in ("QUEUED", "WAITING")),
    )


def review(service, offset=0, user=None):
    """Read at most five workspaces; retain every failed source and explicit coverage."""
    if type(offset) is not int or offset < 0:
        raise Invalid("Use a nonnegative portfolio offset")
    apps = service.store.apps()
    if offset > len(apps):
        raise Invalid("Portfolio changed; restart the weekly review")
    rows = []
    for app in apps[offset : offset + 5]:
        try:
            row = project(service.workspace(app["id"]))
            row["active_work"] = active_work(service.store, app, user)
            row["exceptions"].extend(operation_exceptions(service.store, app, user))
        except Exception:
            row = dict(
                app_id=app["id"],
                app_name=app["data"]["name"],
                local_ready=[],
                active_work=[],
                current_stage=dict(id=None, title=None, next_action=None),
                high_priority_gaps=None,
                active_sequences=None,
                exceptions=[
                    dict(
                        id=digest([app["id"], "unavailable"]),
                        app_id=app["id"],
                        app_name=app["data"]["name"],
                        priority=1,
                        category="source",
                        state="UNAVAILABLE",
                        title="Workspace evidence unavailable",
                        reason="Saved evidence could not be evaluated. No success or zero result is inferred.",
                        next_action="Open this workspace and retry loading its saved evidence.",
                        resolution_route="workspace",
                        source_receipt=dict(
                            app_id=app["id"],
                            manifest_version=app["version"],
                            source_hash=None,
                            observed_at=now(),
                        ),
                        change="NOT_COMPARED_WITH_PRIOR_REVIEW",
                        cost_minor=None,
                        owner="App operator",
                    )
                ],
            )
        rows.append(row)
    return dict(
        schema="growth.weekly-exception-inbox.v1",
        observed_at=now(),
        apps=rows,
        owner_operations_principal=trusted_principal(user),
        exceptions=sorted(
            [c for r in rows for c in r["exceptions"]],
            key=lambda c: (c["priority"], c["app_id"]),
        ),
        active_work=sorted(
            [w for r in rows for w in r.get("active_work", [])],
            key=lambda w: (w["priority"], w["app_id"], w["kind"], w["id"]),
        ),
        coverage=dict(
            offset=offset,
            evaluated=len(rows),
            total_apps=len(apps),
            next_offset=offset + 5 if offset + 5 < len(apps) else None,
        ),
        authority="NO_EXECUTION_AUTHORITY",
        spend_allowed=False,
        scale_allowed=False,
        learning_pilot_allowed=False,
        limits="Saved local evidence only. No prior-review comparison, independent outcome verification or campaign execution.",
    )


def _soon(value, current):
    """Return a future expiry inside the review horizon; anything else stays absent."""
    try:
        at = iso_time(value)
    except Exception:
        return None
    return at if current < at <= current + EXPIRY_HORIZON else None


def _work(app, kind, identity, state, title, reason, next_action, route, updated, priority, expires_at=None):
    """Describe one current local work item without any stored payload."""
    source = dict(status=state, updated=updated)
    if expires_at is not None:
        source["expires"] = expires_at
    return dict(
        id=digest([app["id"], kind, identity]),
        app_id=app["id"],
        app_name=app["data"]["name"],
        kind=kind,
        state=state,
        title=title,
        reason=reason,
        next_action=next_action,
        resolution_route=route,
        updated_at=updated,
        expires_at=expires_at,
        priority=priority,
        source_receipt=dict(
            app_id=app["id"],
            manifest_version=app["version"],
            source_hash=digest(source),
            observed_at=now(),
            source_updated_at=updated,
        ),
    )


def _active_work_items(db, app, principal, tables):
    """Project active jobs, saved sequences and approvals expiring within seven days."""
    current = iso_time(now())
    items = []
    for row in db.execute(
        "SELECT id,action,status,attempts,created,updated FROM jobs "
        "WHERE app_id=? AND status IN ('QUEUED','RUNNING') ORDER BY updated DESC,id DESC LIMIT 50",
        (app["id"],),
    ):
        items.append(
            _work(
                app, "JOB", row["id"], row["status"],
                "Run in progress" if row["status"] == "RUNNING" else "Run queued",
                "{} · attempt {} · queued {}".format(row["action"], row["attempts"], row["created"]),
                "Inspect the saved run; a queued or running job is not a completed result.",
                "activity", row["updated"], 3,
            )
        )
    if "campaign_sequences" in tables:
        for row in db.execute(
            "SELECT id,state,updated FROM campaign_sequences "
            "WHERE app_id=? AND state IN ('QUEUED','WAITING') ORDER BY updated DESC,id DESC LIMIT 50",
            (app["id"],),
        ):
            items.append(
                _work(
                    app, "SEQUENCE", row["id"], row["state"], "Saved sequence still active",
                    "Sequence state {} · updated {}".format(row["state"], row["updated"]),
                    "Inspect the saved sequence checkpoints; a waiting sequence is not completed.",
                    "activity", row["updated"], 3,
                )
            )
    if "agent_grants" in tables:
        for row in db.execute(
            "SELECT id,expires,updated FROM agent_grants "
            "WHERE app_id=? AND status='ACTIVE' ORDER BY expires,id LIMIT 50",
            (app["id"],),
        ):
            at = _soon(row["expires"], current)
            if at is not None:
                items.append(
                    _work(
                        app, "AGENT_GRANT", row["id"], "EXPIRING", "Agent grant expires soon",
                        "Grant {} expires {}".format(row["id"], at.isoformat()),
                        "Renew or revoke the current owner grant before it expires.",
                        "agents", row["updated"], 2, at.isoformat(),
                    )
                )
    if "automation_policies" in tables:
        for row in db.execute(
            "SELECT id,summary,updated FROM automation_policies "
            "WHERE app_id=? AND status='ACTIVE' ORDER BY updated DESC,id LIMIT 50",
            (app["id"],),
        ):
            try:
                summary = json.loads(row["summary"])
            except (TypeError, ValueError):
                continue
            at = _soon(summary.get("stops_at") if isinstance(summary, dict) else None, current)
            if at is not None:
                items.append(
                    _work(
                        app, "AUTOMATION", row["id"], "EXPIRING", "Standing approval expires soon",
                        "Policy {} stops at {}".format(row["id"], at.isoformat()),
                        "Review the standing scope and renew only if the owner still approves it.",
                        "workspace", row["updated"], 2, at.isoformat(),
                    )
                )
    return sorted({item["id"]: item for item in items}.values(),
                  key=lambda item: (item["priority"], item["kind"], item["id"]))


def active_work(store, app, user):
    """Read only bounded owner-scoped work; anonymous, maker and checker callers see none."""
    principal = trusted_principal(user)
    if principal is None or not hasattr(store, "path"):
        return []
    from .db import connection
    from .review_access import member

    with connection(store.path) as db:
        db.execute("BEGIN")
        try:
            role = member(db, app["id"], principal)["role"]
        except PermissionError:
            return []
        if role != "OWNER":
            return []
        tables = {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return _active_work_items(db, app, principal, tables)


def trusted_principal(user):
    """Only the server-supplied authenticated session principal enables private reads."""
    if not isinstance(user, dict):
        return None
    value = user.get("principal")
    return value if isinstance(value, str) and 1 <= len(value) <= 200 else None


def operation_exceptions(store, app, user):
    """Read only bounded owner-owned local rows; anonymous legacy callers see none."""
    principal = trusted_principal(user)
    if principal is None or not hasattr(store, "path"):
        return []
    from .db import connection
    from .review_access import member

    with connection(store.path) as db:
        db.execute("BEGIN")
        try:
            role = member(db, app["id"], principal)["role"]
        except PermissionError:
            return []
        if role not in ("OWNER", "CHECKER", "MAKER"):
            return []
        tables = {
            row["name"]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        cards = _agent_review_cards(db, app, principal, role, tables)
        if role != "OWNER" or "campaign_scopes" not in tables:
            return cards
        try:
            return cards + _operation_rows(db, app, principal, tables)
        except Exception:
            return cards + [
                _card(
                    app,
                    principal,
                    "operation_source",
                    "operation-source",
                    "UNAVAILABLE",
                    "Saved operational evidence unavailable",
                    "Owner-scoped saved operational rows could not be evaluated.",
                    "Open the campaign controls and inspect local saved state before retrying this review.",
                    "campaign",
                    {},
                    {"status": "UNAVAILABLE"},
                    2,
                )
            ]


def _authoritative_review_grant(db, app_id, item, cache):
    """Load complete expiry-binding metadata without widening the card projection."""
    grant_id = item["grant_id"]
    grant = cache.get(grant_id)
    if grant is None:
        source = db.execute(
            "SELECT * FROM agent_grants WHERE app_id=? AND id=?",
            (app_id, grant_id),
        ).fetchone()
        if source is None:
            raise Invalid("Grant source unavailable")
        grant = dict(source)
        cache[grant_id] = grant
    if (grant["id"] != item["g_id"] or grant["id"] != grant_id
            or grant["app_id"] != app_id
            or any(grant[key] != item[key] for key in (
                "agent_id", "owner", "owner_version", "app_version", "app_hash",
                "operations", "expires", "max_calls", "used", "status", "version",
                "created", "updated",
            ))):
        raise Invalid("Grant projection changed")
    return grant


def _agent_review_cards(db, app, principal, role, tables):
    """Read bounded metadata only; inspection and decisions remain in Agent Control."""
    from datetime import datetime, timezone
    from .agent_checkpoints import OPERATIONS, current as checkpoint_current, hashed
    from .agent_grants import current as grant_current
    from .authority_expiry import effective_expiry
    from .common import iso_time
    from .operation_catalog import path_segment

    if not {"agent_review_requests", "agent_checkpoints", "agent_grants"} <= tables:
        # A partially present review source is damaged; older databases may have none.
        if {"agent_review_requests", "agent_checkpoints"} & tables:
            return [_review_source_card(app, principal, role, "review-source")]
        return []
    try:
        rows = db.execute(
            "SELECT r.id,r.grant_id,r.input_hash,CASE WHEN length(CAST(c.data AS BLOB))<=65536 "
            "THEN c.data ELSE NULL END AS checkpoint,c.revision AS checkpoint_revision, "
            "g.id AS g_id,g.app_id,g.agent_id,g.owner,g.owner_version,g.app_version,g.app_hash,"
            "g.operations,g.expires,g.max_calls,g.used,g.status,g.version,g.created,g.updated "
            "FROM agent_review_requests r LEFT JOIN agent_checkpoints c ON c.app_id=r.app_id AND c.id=r.id "
            "LEFT JOIN agent_grants g ON g.id=r.grant_id WHERE r.app_id=? ORDER BY r.id LIMIT 100",
            (app["id"],),
        ).fetchall()
    except Exception:
        return [_review_source_card(app, principal, role, "review-source")]
    observed = datetime.now(timezone.utc)
    cards = []
    maker_source_unavailable = False
    authoritative_grants = {}
    for item in rows:
        identity = item["id"]
        row = _saved(item["checkpoint"])
        packet = row.get("packet") if isinstance(row.get("packet"), dict) else {}
        # Never disclose another maker's request, including corrupt sources.
        # ReviewedDispatch creates the checkpoint as the grant owner; do not
        # trust a damaged packet to identify the maker for a private read.
        if role == "MAKER" and item["owner"] != principal:
            if not isinstance(item["owner"], str) or not item["owner"]:
                maker_source_unavailable = True
            continue
        try:
            # Expiry consent binds complete grant metadata; keep it off the card join.
            grant = _authoritative_review_grant(db, app["id"], item, authoritative_grants)
            path_segment(identity)
            path_segment(item["grant_id"])
            hashed(item["input_hash"])
            hashed(row["hash"])
            hashed(packet["app_hash"])
            hashed(item["app_hash"])
            if type(item["version"]) is not int or item["status"] not in ("ACTIVE", "REVOKED"):
                raise Invalid("Invalid grant metadata")
            if (set(packet) != {"id", "agent_id", "operation", "input_hash", "manifest_version", "expires", "app_id", "app_hash", "maker", "maker_role_version"}
                    or packet["operation"] not in OPERATIONS or type(packet["manifest_version"]) is not int
                    or type(packet["maker_role_version"]) is not int
                    or not isinstance(packet["maker"], str) or not 1 <= len(packet["maker"]) <= 200):
                raise Invalid("Invalid packet")
            if (packet["id"] != identity or packet["app_id"] != app["id"]
                    or packet["input_hash"] != item["input_hash"]
                    or digest(packet) != row["hash"] or item["g_id"] != item["grant_id"]
                    or packet["agent_id"] != item["agent_id"] or packet["maker"] != item["owner"] or item["app_id"] != app["id"]
                    or type(row["revision"]) is not int or row["revision"] != item["checkpoint_revision"]):
                raise Invalid("Invalid source binding")
            history = row["history"]
            if not isinstance(history, list) or len(history) != row["revision"] or not history:
                raise Invalid("Invalid history")
            previous = None
            for event in history:
                data = {key: value for key, value in event.items() if key != "hash"}
                if data.get("previous_hash") != previous or digest(data) != event.get("hash"):
                    raise Invalid("Invalid transition")
                previous = event["hash"]
            state = row["state"]
            if history[-1].get("state") != state or state not in (
                "WAITING_REVIEW", "APPROVED", "RUNNING", "UNKNOWN", "CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED"
            ):
                raise Invalid("Invalid state")
            # Validate timestamps even for terminal records, without returning their contents.
            expiry = iso_time(packet["expires"])
            iso_time(item["expires"])
            if state in ("SUCCEEDED", "FAILED", "CANCELLED"):
                continue
            effective_grant_expiry = iso_time(
                effective_expiry(db, "AGENT_GRANT", grant, grant["expires"])["expires"]
            )
            issue = None
            if expiry <= observed or effective_grant_expiry <= observed:
                issue = "EXPIRED"
            else:
                try:
                    checkpoint_current(db, row, observed)
                except (Invalid, PermissionError):
                    issue = "CHECKPOINT_CONTEXT_CHANGED"
                try:
                    # Only metadata already bound to the packet is supplied; no actual input is invented.
                    grant_current(db, grant, {"app_id": packet["app_id"], "operation": packet["operation"]}, observed, check_quota=False)
                except (Invalid, PermissionError):
                    issue = issue or "GRANT_CONTEXT_CHANGED"
            if state in ("APPROVED", "RUNNING") and issue is None:
                continue
            if state in ("UNKNOWN", "CANCEL_REQUESTED"):
                reason = "The saved effect needs reconciliation; its outcome is not confirmed."
                action = "Open this exact request in Agent Control and reconcile its saved receipts with an independent checker; do not retry uncertain work."
                title = "Reconcile agent request"
            elif issue:
                reason = {"EXPIRED": "The checkpoint or grant expired.", "CHECKPOINT_CONTEXT_CHANGED": "The app or a recorded review role changed.", "GRANT_CONTEXT_CHANGED": "The grant or its owner authority changed."}[issue]
                action = "Open this exact request in Agent Control and inspect current authority and saved receipts before preparing replacement work."
                if state == "RUNNING":
                    action += " Expiry or changed authority does not establish that an in-flight effect stopped."
                title = "Recover stale agent request"
            else:
                reason = "This proposal awaits an independent checker."
                action = "Open this exact request in Agent Control; a current checker distinct from the maker must inspect it."
                title = "Review agent proposal"
            evidence = dict(request_id=identity, grant_id=item["grant_id"], input_hash=item["input_hash"],
                            checkpoint_hash=row["hash"], revision=row["revision"], state=state, authority_issue=issue,
                            grant_version=item["version"], app_version=app["version"])
            card = _card(app, principal, "agent_review", identity, issue or state, title, reason, action,
                         "agent_review", {}, evidence, 1)
            card.update(owner_only=False, private_principal=principal, owner={"OWNER": "App owner", "CHECKER": "App checker", "MAKER": "App maker"}[role])
            card.pop("owner_principal", None)
            cards.append(card)
        except (Invalid, PermissionError, KeyError, TypeError, ValueError, AttributeError):
            # Do not reflect malformed IDs, metadata or exception messages into the response.
            try:
                safe_identity = path_segment(identity)
            except Invalid:
                safe_identity = "review-source"
            cards.append(_review_source_card(app, principal, role, safe_identity))
    if maker_source_unavailable:
        cards.append(_review_source_card(app, principal, role, "review-source"))
    return list({card["id"]: card for card in cards}.values())


def _review_source_card(app, principal, role, identity):
    card = _card(app, principal, "agent_review", identity, "SOURCE_UNAVAILABLE",
                 "Review source unavailable", "Saved review metadata could not be verified.",
                 "Open Agent Control and inspect the saved request before taking action.",
                 "agent_review", {}, {"status": "SOURCE_UNAVAILABLE", "request_id": identity}, 1)
    card.update(owner_only=False, private_principal=principal, owner={"OWNER": "App owner", "CHECKER": "App checker", "MAKER": "App maker"}[role])
    card.pop("owner_principal", None)
    return card


def _operation_rows(db, app, principal, tables):
    scopes = {
        r["id"]: r
        for r in db.execute(
            "SELECT * FROM campaign_scopes WHERE app_id=? AND owner=? ORDER BY updated DESC,id LIMIT 50",
            (app["id"], principal),
        )
    }
    cards = []
    if "agent_handoffs" in tables:
        cards.extend(_handoff_cards(db, app, principal))
    unresolved = set()
    for table, paid in (("campaign_paid_intents", True), ("campaign_intents", False)):
        if table not in tables:
            continue
        sql = (
            "SELECT i.* FROM "
            + table
            + " i JOIN campaign_scopes s ON s.app_id=i.app_id AND s.id=i.scope_id "
            "WHERE i.app_id=? AND s.owner=? ORDER BY i.updated DESC,i.id LIMIT 100"
        )
        for row in db.execute(sql, (app["id"], principal)):
            if row["scope_id"] not in scopes:
                continue
            card = _intent_card(app, principal, scopes[row["scope_id"]], row, paid)
            if card:
                cards.append(card)
                unresolved.add(row["id"])
    if "campaign_monitors" in tables:
        for row in db.execute(
            "SELECT * FROM campaign_monitors WHERE app_id=? AND owner=? ORDER BY updated DESC,id LIMIT 50",
            (app["id"], principal),
        ):
            card = _plan_card(db, app, principal, row, "monitor", unresolved)
            if card:
                cards.append(card)
    if "campaign_report_plans" in tables:
        for row in db.execute(
            "SELECT * FROM campaign_report_plans WHERE app_id=? AND owner=? ORDER BY updated DESC,id LIMIT 50",
            (app["id"], principal),
        ):
            card = _plan_card(db, app, principal, row, "owner_reports", unresolved)
            if card:
                cards.append(card)
    if {"campaign_schedule_batches", "campaign_schedule_items"} <= tables:
        cards.extend(
            _schedule_cards(
                db,
                app,
                principal,
                scopes,
                {
                    c["action"].get("scope_id")
                    for c in cards
                    if c["category"] == "delivery"
                },
            )
        )
    return list({card["id"]: card for card in cards}.values())


def _handoff_cards(db, app, principal):
    """Reuse current handoff admission state without resuming or issuing authority."""
    from .agent_handoffs import _read, _job, _view, _utc

    cards = []
    observed = _utc()
    for row in db.execute(
        "SELECT * FROM agent_handoffs WHERE app_id=? ORDER BY created DESC,id LIMIT 100",
        (app["id"],),
    ):
        payload = _read(row)
        source = payload["source"]
        owner = source.get("principal") if source["kind"] == "OWNER" else None
        if source["kind"] == "AGENT":
            grant = db.execute("SELECT owner FROM agent_grants WHERE app_id=? AND id=?",
                               (app["id"], source["grant_id"])).fetchone()
            owner = grant["owner"] if grant else None
        if owner != principal:
            continue
        job = _job(db, app["id"], payload["job_id"])
        view = _view(db, row, job, observed)
        state = view["effective_status"]
        failed = job["status"] in ("FAILED", "BLOCKED", "UNKNOWN", "INTERRUPTED")
        invalid = state in ("EXPIRED", "CONTEXT_CHANGED", "SOURCE_INVALID", "RECIPIENT_INVALID")
        if not failed and (not invalid or job["status"] in ("SUCCEEDED", "CANCELLED")):
            continue
        repair = ("Open Your agents, then Handoffs; inspect the original job and reconcile its saved receipts; do not replay uncertain effects. "
                  "Revoked handoff authority remains revoked." if state == "REVOKED" else
                  "Open Your agents, then Handoffs; " + view["next_action"])
        evidence = dict(handoff_id=row["id"], version=row["version"], effective_status=state,
                        payload_hash=row["payload_hash"], expires=row["expires"],
                        job_id=job["id"], job_status=job["status"], updated=job["updated"],
                        authority_issued=False)
        cards.append(_card(app, principal, "handoff", row["id"],
                           "JOB_" + job["status"] if failed else state,
                           "Agent handoff needs recovery", "Saved task continuity needs current owner review.",
                           repair, "workspace", {"job_id":job["id"]}, evidence, 2))
    return cards


def _schedule_cards(db, app, principal, scopes, unresolved_scopes):
    from .common import iso_time

    cards = []
    rows = db.execute(
        "SELECT b.id,b.scope_id,b.status,b.summary_hash,b.updated, count(i.id) AS pending FROM campaign_schedule_batches b JOIN campaign_schedule_items i ON i.batch_id=b.id WHERE b.app_id=? AND b.owner=? AND b.status='ACTIVE' AND i.status IN ('READY','QUEUED','BLOCKED') GROUP BY b.id ORDER BY b.updated DESC LIMIT 50",
        (app["id"], principal),
    )
    for row in rows:
        scope = scopes.get(row["scope_id"])
        if scope is None:
            continue
        if scope["id"] in unresolved_scopes:
            continue
        data = _saved(scope["summary"])
        try:
            expired = iso_time(data["expires_at"]) <= iso_time(now())
        except (KeyError, TypeError, Invalid):
            expired = True
        if not expired:
            failed = db.execute(
                "SELECT 1 FROM campaign_schedule_items i LEFT JOIN jobs j ON j.id=i.job_id AND j.app_id=? WHERE i.batch_id=? AND (i.status='BLOCKED' OR j.status IN ('BLOCKED','FAILED','UNKNOWN')) LIMIT 1",
                (app["id"], row["id"]),
            ).fetchone()
            if not failed:
                continue
        source = dict(
            id=row["id"],
            scope_id=row["scope_id"],
            status="EXPIRED_PENDING_WORK" if expired else "BLOCKED",
            summary_hash=row["summary_hash"],
            pending_items=row["pending"],
            updated=row["updated"],
        )
        cards.append(
            _card(
                app,
                principal,
                "scheduled_campaign",
                row["id"],
                source["status"],
                "Review unfinished scheduled campaign work",
                "The campaign approval expired with pending work."
                if expired
                else "A saved scheduled campaign job needs review.",
                "Inspect the exact batch and delivery receipts; reconcile uncertainty before approving replacement work.",
                "campaign",
                dict(scope_id=row["scope_id"], batch_id=row["id"]),
                source,
                2,
            )
        )
    return cards


def _saved(raw):
    import json

    if not isinstance(raw, str) or len(raw) > 65536:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _intent_card(app, principal, scope, row, paid):
    state = row["status"]
    allowed = {"UNKNOWN", "DISPATCHING", "ACKNOWLEDGED", "VERIFYING"} | {
        "PENDING_" + name
        for name in (
            "CREATE_campaign",
            "CREATE_adset",
            "CREATE_creative",
            "CREATE_ad",
            "ACTIVE_adset",
            "ACTIVE_ad",
            "ACTIVE_campaign",
            "PAUSED_campaign",
        )
    }
    if state not in allowed:
        return None
    uncertain = state in (
        "UNKNOWN",
        "DISPATCHING",
        "ACKNOWLEDGED",
        "VERIFYING",
    ) or state.startswith("PENDING_")
    if not uncertain:
        return None
    # Revoked/OFF scheduling is intentional; unresolved dispatch receipts still
    # need reconciliation because OFF does not undo a dispatched effect.
    identities = {
        key: row[key]
        for key in ("id", "request_id", "request_hash", "status", "updated")
    }
    if paid:
        ids = _saved(row["ids"])
        identities.update(
            provider_ids=_provider_ids(ids),
            retained_commitment_minor=row["commitment"],
            currency=row["currency"],
        )
    else:
        remote = row["remote_id"]
        identities["provider_ids"] = {"post": remote} if _provider_id(remote) else {}
    return _card(
        app,
        principal,
        "delivery",
        row["id"],
        state,
        "Reconcile uncertain campaign delivery",
        "A saved provider effect is unconfirmed. Retained commitments are not released by uncertainty.",
        "Inspect this exact receipt and reconcile its saved provider IDs before any retry.",
        "campaign",
        dict(scope_id=scope["id"], intent_id=row["id"]),
        identities,
        1,
    )


def _provider_id(value):
    import re

    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9]{1,40}(?:_[0-9]{1,40})?", value) is not None
    )


def _provider_ids(ids):
    return {
        key: value
        for key, value in ids.items()
        if key in ("campaign", "adset", "creative", "ad") and _provider_id(value)
    }


def _plan_card(db, app, principal, row, tool, unresolved):
    if row["status"] == "OFF":
        return None
    summary = _saved(row["summary"])
    if not summary or digest(summary) != row["summary_hash"]:
        return _card(
            app,
            principal,
            tool,
            row["id"],
            "INTEGRITY_REVIEW_REQUIRED",
            "Review damaged automation state",
            "Saved approval integrity could not be verified.",
            "Open the exact saved controls and review its approval before enabling work.",
            tool,
            {},
            dict(
                id=row["id"],
                version=row["version"],
                status="INTEGRITY_REVIEW_REQUIRED",
                updated=row["updated"],
            ),
            2,
        )
    proposal = summary.get("proposal", {})
    if tool == "monitor" and any(
        target.get("intent_id") in unresolved
        for target in proposal.get("targets", [])
        if isinstance(target, dict)
    ):
        return None
    job = _owned_job(db, app, row, tool)
    issue = _plan_issue(row, proposal, job, tool)
    if issue is None:
        return None
    state, title, reason, repair = issue
    source = dict(
        id=row["id"],
        version=row["version"],
        status=row["status"],
        summary_hash=row["summary_hash"],
        updated=row["updated"],
        last_job=dict(id=job["id"], status=job["status"], updated=job["updated"])
        if job
        else None,
    )
    return _card(
        app,
        principal,
        tool,
        row["id"],
        state,
        title,
        reason,
        repair,
        tool,
        {},
        source,
        2,
    )


def _owned_job(db, app, row, tool):
    if not row["last_job"]:
        return None
    job = db.execute(
        "SELECT id,app_id,action,status,data,updated FROM jobs WHERE id=? AND app_id=?",
        (row["last_job"], app["id"]),
    ).fetchone()
    if job is None:
        return None
    expected = "campaign_monitor" if tool == "monitor" else "campaign_owner_report"
    data = _saved(job["data"])
    key = "monitor_id" if tool == "monitor" else "plan_id"
    if (
        job["status"]
        not in {
            "QUEUED",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "BLOCKED",
            "UNKNOWN",
            "CANCELLED",
            "INTERRUPTED",
        }
        or job["action"] != expected
        or data.get(key) != row["id"]
        or data.get("summary_hash") != row["summary_hash"]
    ):
        return None
    return job


def _plan_issue(row, proposal, job, tool):
    name = "Campaign monitor" if tool == "monitor" else "Private report plan"
    repair = (
        "Open the exact monitor controls and inspect its last observation before approving replacement work."
        if tool == "monitor"
        else "Open private reports, inspect the failed snapshot job and review current source bindings before another plan."
    )
    limit = proposal.get("max_runs" if tool == "monitor" else "max_reports")
    finished = (
        type(limit) is int
        and row["runs"] >= limit
        and (job is None or job["status"] == "SUCCEEDED")
    )
    if finished:
        return None
    if row["status"] == "BLOCKED" or (
        job and job["status"] in ("FAILED", "BLOCKED", "UNKNOWN")
    ):
        return (
            "BLOCKED",
            name + " needs a decision",
            "Saved local work stopped at a validation, authority or execution boundary.",
            repair,
        )
    if row["status"] != "ACTIVE":
        return None
    from .common import iso_time

    try:
        expired = iso_time(proposal["expires_at"]) <= iso_time(now())
    except (Invalid, KeyError, TypeError):
        return (
            "INTEGRITY_REVIEW_REQUIRED",
            name + " needs review",
            "Saved expiry could not be verified.",
            repair,
        )
    limit = proposal.get("max_runs" if tool == "monitor" else "max_reports")
    if expired and type(limit) is int and row["runs"] < limit:
        return (
            "EXPIRED",
            name + " expired with unfinished planned work",
            "The finite approval ended before all planned runs were dispatched.",
            repair,
        )
    return None


def _card(
    app,
    principal,
    category,
    identity,
    state,
    title,
    reason,
    repair,
    tool,
    refs,
    source,
    priority,
):
    receipt = dict(
        app_id=app["id"],
        manifest_version=app["version"],
        source_hash=digest(source),
        observed_at=now(),
        source_updated_at=source.get("updated"),
    )
    return dict(
        id=digest([app["id"], category, identity]),
        app_id=app["id"],
        app_name=app["data"]["name"],
        category=category,
        priority=priority,
        state=state,
        title=title,
        reason=reason,
        next_action=repair,
        resolution_route=tool,
        action=dict(tool=tool, resource_id=identity, **refs),
        source_receipt=receipt,
        change="CURRENT_EXCEPTION_NO_PRIOR_DELIVERY_COMPARISON",
        cost_minor=None,
        owner="App owner",
        owner_only=True,
        owner_principal=principal,
        evidence=source,
    )
