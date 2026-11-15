"""One owner-authorized, local action for a newly matched saved rule."""

import json
from sqlite3 import Connection
from typing import cast

from .automation_proposals import FINGERPRINT, ReportIntegrationReceipt, RunReceipt, duration, within_cooldown
from .campaign_owner_reports import binding, owned_resource, report_view, save_report, selection
from .common import Invalid, canonical, digest, iso_time
from .social_contract import reference
from .store import Store


def review_action(proposal: dict[str, object], requires: object) -> bool:
    return proposal["action"] == "review_result" and proposal["tool"] == "reports.read" and requires == ["OWNER_REVIEW"]


def template(db: Connection, store: Store, app_id: str, owner: str, request: object) -> tuple[dict[str, object], str]:
    if not isinstance(request, dict) or set(request) != {"report_id", "report_hash"}:
        raise Invalid("Choose the exact saved private report")
    report_id = reference(request["report_id"])
    fingerprint = request["report_hash"]
    if not isinstance(fingerprint, str) or not FINGERPRINT.fullmatch(fingerprint):
        raise Invalid("Choose a valid saved private report fingerprint")
    row = owned_resource(db, "campaign_owner_reports", app_id, owner, report_id)
    saved = report_view(row)
    if saved["hash"] != fingerprint:
        raise Invalid("The selected private report changed. Review it again.")
    chosen = selection(saved["report"]["selection"])
    current = binding(db, store, app_id, owner, chosen)
    if current != saved["report"]["source"]:
        raise Invalid("The private report sources changed. Save a current report first.")
    return cast(dict[str, object], chosen), digest(current)


def prepare(
    db: Connection, store: Store, app_id: str, owner: str, body: dict, document: dict, study: dict | None
) -> dict[str, str]:
    request = body["report_integration"]
    if document["mode"] != "AUTO_WITHIN_GRANT" or not any(
        rule["enabled"] and review_action(rule["then"]["propose"], rule["then"]["requires"])
        for rule in document["rules"]
    ):
        raise Invalid("Choose saved rules with an enabled private Results review in AUTO_WITHIN_GRANT mode.")
    chosen, source_hash = template(db, store, app_id, owner, request)
    if study is not None and any(
        iso_time(chosen_window(chosen)[date]) != iso_time(study["window"][date]) for date in ("starts_at", "ends_at")
    ):
        raise Invalid("Choose a private report with the same dates as the selected study.")
    key = digest([app_id, owner, (body["version"] or 0) + 1, body["saved"], request, source_hash])
    return {**cast(dict[str, str], request), "source_hash": source_hash, "capture_key": "automation-rule:" + key}


def chosen_window(chosen: dict[str, object]) -> dict[str, str]:
    return cast(dict[str, str], chosen["measurement_window"])


def saved_action(db: Connection, app_id: str, owner: str, key: str) -> dict[str, str] | None:
    row = db.execute(
        "SELECT * FROM campaign_owner_reports WHERE app_id=? AND owner=? AND capture_key=?",
        (app_id, owner, key),
    ).fetchone()
    if row is None:
        return None
    saved = report_view(row)
    return {"report_id": cast(str, saved["id"]), "report_hash": cast(str, saved["hash"])}


def complete_matches(receipt: RunReceipt) -> set[str]:
    return {
        row["rule_id"]
        for row in receipt["results"]
        if row["status"] == "MATCH" and not (row["missing"] or row["incompatible"])
    }


def admitted_proposal(db: Connection, app_id: str, owner: str, receipt: RunReceipt) -> str | None:
    matches = complete_matches(receipt)
    for candidate in receipt["proposals"]:
        if candidate["status"] not in {"SAVED", "UNCHANGED"}:
            continue
        row = db.execute(
            """SELECT action_key,proposal FROM automation_rule_proposals
               WHERE app_id=? AND owner=? AND id=? AND dismissed_at IS NULL""",
            (app_id, owner, candidate["id"]),
        ).fetchone()
        if row is None:
            continue
        item = json.loads(row["proposal"])
        if item["rule_id"] not in matches or not review_action(item, item["requires"]):
            continue
        if candidate["status"] == "UNCHANGED" and within_cooldown(
            db, app_id, owner, row["action_key"], receipt["observed_at"], duration(item["cooldown"])
        ):
            continue
        return candidate["id"]
    return None


def integrate(
    db: Connection,
    store: Store,
    app_id: str,
    owner: str,
    approved: dict[str, str],
    receipt: RunReceipt,
) -> None:
    if "integration" in receipt:
        return
    request = {key: approved[key] for key in ("report_id", "report_hash")}
    chosen, source_hash = template(db, store, app_id, owner, request)
    if source_hash != approved["source_hash"]:
        raise Invalid("The approved private report sources changed.")
    key = approved["capture_key"]
    previous = saved_action(db, app_id, owner, key)
    admitted = admitted_proposal(db, app_id, owner, receipt) if previous is None else None
    result: ReportIntegrationReceipt = {
        "status": "NO_NEW_MATCH",
        "template_id": request["report_id"],
        "template_hash": request["report_hash"],
    }
    if admitted is not None:
        saved = save_report(db, store, app_id, owner, chosen, key)
        result.update(
            status="REPORT_SAVED",
            proposal_id=admitted,
            report_id=cast(str, saved["id"]),
            report_hash=cast(str, saved["hash"]),
        )
    receipt["integration"] = result
    db.execute(
        "UPDATE automation_rule_runs SET receipt=? WHERE app_id=? AND owner=? AND id=?",
        (canonical(receipt), app_id, owner, receipt["id"]),
    )
