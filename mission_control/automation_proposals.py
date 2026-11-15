"""App-scoped rule recommendations; neither persistence nor review executes them."""

import json
import re
from collections.abc import Callable
from datetime import timedelta
from sqlite3 import Connection
from typing import TypedDict

from .automation_rules import _project_snapshot, _study_facts, evaluate
from .automation_store import version_in_snapshot
from .common import Invalid, canonical, digest, iso_time, now
from .db import connection
from .review_access import member
from .store import Store

MAX_RUNS_PER_OWNER = 2_000
MAX_PROPOSALS_PER_OWNER = 5_000
COOLDOWN = re.compile(r"(?:P([1-7])D|PT([1-9][0-9]{0,2})([HM]))")
FINGERPRINT = re.compile(r"[a-f0-9]{64}")
REQUEST_ID = re.compile(r"[a-zA-Z0-9-]{16,64}")


class RuleRef(TypedDict):
    version: int
    hash: str


class ProposalDisposition(TypedDict):
    id: str
    status: str


class RunReceipt(TypedDict):
    id: str
    app_id: str
    app_version: int
    rule: RuleRef
    observed_at: str
    facts_sha256: str
    request_sha256: str | None
    results: list[dict]
    proposals: list[ProposalDisposition]
    mode: str


class SavedProposal(TypedDict):
    proposal: dict
    dismissed_at: str | None
    app_version: int
    rule_version: int
    receipt_id: str


class ProposalInbox(TypedDict):
    app_id: str
    mode: str
    proposals: list[SavedProposal]
    latest_run: RunReceipt | None
    has_more: bool


def duration(value: str) -> timedelta:
    """Parse historical rule labels only when they enter durable execution."""
    if value == "":
        return timedelta()
    match = COOLDOWN.fullmatch(value)
    if not match:
        raise Invalid("Use a rule cooldown such as PT15M, PT6H or P1D")
    days, amount, unit = match.groups()
    if days:
        return timedelta(days=int(days))
    result = timedelta(hours=int(amount)) if unit == "H" else timedelta(minutes=int(amount))
    if result > timedelta(days=7):
        raise Invalid("Rule cooldown cannot exceed seven days")
    return result


def version_matches(db: Connection, app_id: str, version: int) -> None:
    """Reject stale app form submissions independently from rule versions."""
    current = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
    if type(version) is not int or current is None or current["version"] != version:
        raise Invalid("App setup changed. Refresh and choose the saved rules again.")


def stored_proposal(
    db: Connection, app_id: str, owner: str, proposal_id: str, action_key: str, stamp: str, cooldown: timedelta
) -> str | None:
    """Suppress identical facts forever and changed facts for the actual elapsed cooldown."""
    if db.execute(
        "SELECT 1 FROM automation_rule_proposals WHERE app_id=? AND owner=? AND id=?",
        (app_id, owner, proposal_id),
    ).fetchone():
        return "UNCHANGED"
    if not cooldown:
        return None
    last = db.execute(
        """SELECT observed_at FROM automation_rule_proposals
           WHERE app_id=? AND owner=? AND action_key=? ORDER BY observed_at DESC LIMIT 1""",
        (app_id, owner, action_key),
    ).fetchone()
    if last is not None and iso_time(last["observed_at"]) + cooldown > iso_time(stamp):
        return "COOLDOWN"
    return None


def evaluate_in_snapshot(
    db: Connection,
    app_id: str,
    owner: str,
    app_version: int,
    reference: RuleRef,
    stamp: str,
    *,
    study: dict[str, object] | None = None,
    slot: str | None = None,
    request_id: str | None = None,
) -> RunReceipt:
    """Retain the evidence using one authorized, serialized workspace transaction."""
    version_matches(db, app_id, app_version)
    fingerprint, request_hash, previous = request_binding(db, app_id, owner, app_version, reference, study, request_id)
    if previous is not None:
        return previous
    saved = version_in_snapshot(db, app_id, reference)
    if saved is None:
        raise Invalid("The saved rule version is unavailable")
    rules = saved["document"]
    binding = {key: saved[key] for key in ("app_id", "version", "hash")}
    facts = _project_snapshot(db, app_id)
    if study is not None:
        facts["study"] = _study_facts(db, app_id, study, stamp)
    evaluated = evaluate(rules, facts, observed_at=stamp, binding=binding)
    if fingerprint is None:
        fingerprints = [reference, study, evaluated["facts_sha256"], evaluated["results"]]
        fingerprint = digest([app_id, owner, app_version, fingerprints, slot or stamp])
        previous = saved_run(db, app_id, owner, fingerprint)
        if previous is not None:
            return previous
    return retain_evaluation(
        db, app_id, owner, app_version, reference, fingerprint, evaluated, stamp, request_hash, study
    )


def request_binding(
    db: Connection,
    app_id: str,
    owner: str,
    app_version: int,
    reference: RuleRef,
    study: dict[str, object] | None,
    request_id: str | None,
) -> tuple[str | None, str | None, RunReceipt | None]:
    if request_id is None:
        return None, None, None
    if not isinstance(request_id, str) or not REQUEST_ID.fullmatch(request_id):
        raise Invalid("A valid rule request ID is required")
    fingerprint = digest(["manual_rule_run", app_id, owner, request_id])
    request_hash = digest([app_version, reference, study])
    previous = saved_run(db, app_id, owner, fingerprint)
    if previous is not None and previous["request_sha256"] != request_hash:
        raise Invalid("This request ID was used with different rules or evidence")
    return fingerprint, request_hash, previous


def saved_run(db: Connection, app_id: str, owner: str, fingerprint: str) -> RunReceipt | None:
    previous = db.execute(
        "SELECT receipt FROM automation_rule_runs WHERE app_id=? AND owner=? AND id=?",
        (app_id, owner, fingerprint),
    ).fetchone()
    return json.loads(previous["receipt"]) if previous is not None else None


def retain_evaluation(
    db: Connection,
    app_id: str,
    owner: str,
    app_version: int,
    reference: RuleRef,
    fingerprint: str,
    evaluated: dict,
    stamp: str,
    request_hash: str | None,
    study: dict[str, object] | None,
) -> RunReceipt:
    """Separate rule result from the disposition of each proposed action."""
    run_count = db.execute(
        "SELECT count(*) FROM automation_rule_runs WHERE app_id=? AND owner=?", (app_id, owner)
    ).fetchone()[0]
    if run_count >= MAX_RUNS_PER_OWNER:
        raise Invalid("Saved rule history is full. Export and review this workspace.")
    data = []
    for proposal in evaluated["proposals"]:
        candidate = digest([app_version, proposal["id"]])
        action_key = digest([app_version, study["study_id"] if study else None, proposal["action"], proposal["tool"]])
        disposition = stored_proposal(db, app_id, owner, candidate, action_key, stamp, duration(proposal["cooldown"]))
        data.append((candidate, action_key, disposition, {**proposal, "id": candidate, "mode": "PROPOSE_ONLY"}))
    pending = [item for item in data if item[2] is None]
    if pending:
        count = db.execute(
            "SELECT count(*) FROM automation_rule_proposals WHERE app_id=? AND owner=?", (app_id, owner)
        ).fetchone()[0]
        if count + len(pending) > MAX_PROPOSALS_PER_OWNER:
            raise Invalid("Saved proposal history is full. Export and review this workspace.")
    receipt: RunReceipt = {
        "id": fingerprint,
        "app_id": app_id,
        "app_version": app_version,
        "rule": reference,
        "observed_at": stamp,
        "facts_sha256": evaluated["facts_sha256"],
        "request_sha256": request_hash,
        "results": evaluated["results"],
        "proposals": [{"id": key, "status": status or "SAVED"} for key, _, status, _ in data],
        "mode": "PROPOSE_ONLY",
    }
    db.execute(
        "INSERT INTO automation_rule_runs VALUES(?,?,?,?,?,?,?)",
        (app_id, owner, fingerprint, app_version, reference["version"], stamp, canonical(receipt)),
    )
    db.executemany(
        "INSERT INTO automation_rule_proposals VALUES(?,?,?,?,?,?,?,NULL)",
        [(app_id, owner, key, fingerprint, action, stamp, canonical(item)) for key, action, _, item in pending],
    )
    return receipt


def run(
    store: Store,
    app_id: str,
    owner: str,
    app_version: int,
    reference: RuleRef,
    study: dict[str, object] | None = None,
    *,
    request_id: str | None = None,
    commit_check: Callable[[], object] | None = None,
) -> RunReceipt:
    """Evaluate saved rules only after an explicit current owner request."""
    with connection(store.path, write=True) as db:
        member(db, app_id, owner, "OWNER")
        result = evaluate_in_snapshot(
            db, app_id, owner, app_version, reference, now(), study=study, request_id=request_id
        )
        if commit_check is not None:
            commit_check()
        return result


def inbox(store: Store, app_id: str, owner: str) -> ProposalInbox:
    """Read bounded private proposals and the latest evaluation for the selected app."""
    with connection(store.path) as db:
        db.execute("BEGIN")
        member(db, app_id, owner, "OWNER")
        rows = db.execute(
            """SELECT p.proposal, p.dismissed_at, r.app_version, r.rule_version, r.id AS receipt_id
               FROM automation_rule_proposals AS p JOIN automation_rule_runs AS r
               ON (p.app_id,p.owner,p.run_id)=(r.app_id,r.owner,r.id)
               WHERE p.app_id=? AND p.owner=?
               ORDER BY (p.dismissed_at IS NULL) DESC, p.observed_at DESC, p.id LIMIT 51""",
            (app_id, owner),
        ).fetchall()
        latest = db.execute(
            """SELECT receipt FROM automation_rule_runs
               WHERE app_id=? AND owner=? ORDER BY observed_at DESC, id LIMIT 1""",
            (app_id, owner),
        ).fetchone()
    return {
        "app_id": app_id,
        "mode": "PROPOSE_ONLY",
        "proposals": [
            {
                "proposal": json.loads(row["proposal"]),
                "dismissed_at": row["dismissed_at"],
                "app_version": row["app_version"],
                "rule_version": row["rule_version"],
                "receipt_id": row["receipt_id"],
            }
            for row in rows[:50]
        ],
        "latest_run": json.loads(latest["receipt"]) if latest is not None else None,
        "has_more": len(rows) > 50,
    }


def dismiss(
    store: Store,
    app_id: str,
    owner: str,
    proposal_id: str,
    *,
    commit_check: Callable[[], object] | None = None,
) -> dict[str, object]:
    """Dismiss one app-owned proposal idempotently; no dispatch or new authority."""
    if not isinstance(proposal_id, str) or not FINGERPRINT.fullmatch(proposal_id):
        raise Invalid("Choose an exact saved proposal")
    with connection(store.path, write=True) as db:
        member(db, app_id, owner, "OWNER")
        row = db.execute(
            """UPDATE automation_rule_proposals SET dismissed_at=coalesce(dismissed_at,?)
               WHERE app_id=? AND owner=? AND id=? RETURNING dismissed_at""",
            (now(), app_id, owner, proposal_id),
        ).fetchone()
        if row is None:
            raise Invalid("Proposal is unavailable for this app and owner")
        if commit_check is not None:
            commit_check()
        return {"id": proposal_id, "dismissed_at": row["dismissed_at"], "mode": "PROPOSE_ONLY"}
