"""Deterministic user-authored rules over supplied facts; proposals only, no effects."""
from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .common import Invalid, digest, iso_time, now

SCHEMA = "wmm.automation-rules.v1"
TRUE, FALSE, UNKNOWN = "TRUE", "FALSE", "UNKNOWN"
COMPARISONS = {"eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "exists", "missing"}
RULE_KEYS = {"id", "enabled", "priority", "when", "then", "cooldown", "expires_at"}


def _exact(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise Invalid("Use the exact " + label + " fields")


def _text(value, label, maximum=2000, optional=False):
    if value is None and optional:
        return ""
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Invalid("Use a " + label + " of 1-" + str(maximum) + " characters")
    return value


def _condition(value):
    if not isinstance(value, dict) or not value:
        raise Invalid("Every condition must be a non-empty object")
    keys = set(value)
    if keys == {"fact", "op", "value"}:
        if not isinstance(value["fact"], str) or not value["fact"]:
            raise Invalid("Conditions need a fact path")
        if value["op"] not in COMPARISONS:
            raise Invalid("Unsupported condition operator")
        return dict(kind="compare", fact=value["fact"], op=value["op"], value=value["value"])
    if keys == {"fact", "op"} and value["op"] in ("exists", "missing"):
        return dict(kind="compare", fact=value["fact"], op=value["op"], value=None)
    if keys == {"all"}:
        if not isinstance(value["all"], list) or not 1 <= len(value["all"]) <= 50:
            raise Invalid("Use 1-50 all conditions")
        return dict(kind="all", items=[_condition(item) for item in value["all"]])
    if keys == {"any"}:
        if not isinstance(value["any"], list) or not 1 <= len(value["any"]) <= 50:
            raise Invalid("Use 1-50 any conditions")
        return dict(kind="any", items=[_condition(item) for item in value["any"]])
    if keys == {"not"}:
        return dict(kind="not", item=_condition(value["not"]))
    raise Invalid("Use one of all, any, not or a fact comparison")


def _rule(value):
    _exact(value, RULE_KEYS - ({"cooldown", "expires_at"} - set(value)), "rule")
    if not isinstance(value.get("id"), str) or not value["id"].strip() or len(value["id"]) > 100:
        raise Invalid("Rules need a stable id")
    if type(value.get("enabled")) is not bool:
        raise Invalid("Rule enabled must be an explicit boolean")
    if type(value.get("priority")) is not int or not 0 <= value["priority"] <= 1000:
        raise Invalid("Rule priority must be an integer from 0 to 1000")
    when = _condition(value.get("when"))
    then = value.get("then")
    _exact(then, {"propose", "requires"}, "rule then")
    propose = then["propose"]
    _exact(propose, {"action", "tool", "reason"}, "proposal")
    action = _text(propose["action"], "proposal action", 120)
    tool = _text(propose["tool"], "proposal tool", 200)
    reason = _text(propose["reason"], "proposal reason")
    requires = then["requires"]
    if not isinstance(requires, list) or not requires or len(requires) > 10 or any(
            not isinstance(item, str) or not item for item in requires):
        raise Invalid("Proposals need 1-10 named approvals")
    cooldown = value.get("cooldown", "")
    if cooldown and (not isinstance(cooldown, str) or len(cooldown) > 40):
        raise Invalid("Use an ISO 8601-style cooldown label")
    expires = value.get("expires_at")
    if expires is not None:
        iso_time(expires)
    return dict(id=value["id"], enabled=value["enabled"], priority=value["priority"], when=when,
                action=action, tool=tool, reason=reason, requires=list(requires),
                cooldown=cooldown, expires_at=expires)


def _saved_rows(value):
    return value if isinstance(value, list) and all(isinstance(row, dict) for row in value) else None


def _count(rows, field=None, value=None):
    if rows is None:
        return None
    return len(rows) if field is None else sum(row.get(field) == value for row in rows)


def project(workspace):
    """Project a read-only Service workspace into typed facts; absent facts stay absent."""
    if not isinstance(workspace, dict):
        raise Invalid("Workspace must be an object")
    app = workspace.get("app") or {}
    data = app.get("data") or {}
    workflow = workspace.get("workflow") or {}
    metrics = workspace.get("metrics") or {}
    attribution = workspace.get("install_attribution") or {}
    integrity = workspace.get("measurement_integrity") or {}
    experiments = _saved_rows(workspace.get("experiments"))
    automation = workspace.get("automation") or {}
    cohorts = _saved_rows(metrics.get("cohorts"))
    retention = _saved_rows(metrics.get("retention"))
    ledger = _saved_rows(metrics.get("event_ledger"))
    campaigns = _saved_rows(attribution.get("campaigns"))
    facts = {
        "app": {
            "id": app.get("id"),
            "version": app.get("version"),
            "name": data.get("name"),
            "release": data.get("release"),
            "locale": data.get("locale"),
            "currency": data.get("currency"),
        },
        "workflow": {
            "local_ready_count": workflow.get("local_ready_count"),
            "next_action": (workflow.get("next_action") or {}).get("id"),
            "exception_count": _count(_saved_rows(workflow.get("exceptions"))),
        },
        "automation": {
            "mode": automation.get("mode"),
            "metric": (automation.get("metric") or {}).get("value"),
            "channel": (automation.get("channel") or {}).get("value"),
        },
        "metrics": {
            "cohort_count": _count(cohorts),
            "measured_cohort_count": _count(cohorts, "status", "MEASURED"),
            "retention_window_count": _count(retention),
            "ledger_report_count": _count(ledger),
        },
        "install": {
            "campaign_count": _count(campaigns),
            "campaign_tokens": (sorted(row.get("campaign_token") for row in campaigns if row.get("campaign_token"))
                                if campaigns is not None else None),
            "last_observed_at": max((row.get("last_observed_at") for row in campaigns or []
                                     if row.get("last_observed_at")), default=None),
        },
        "measurement": {"state": integrity.get("state")},
        "experiments": {
            "count": _count(experiments),
            "planned": _count(experiments, "state", "PLANNED"),
            "awaiting_analysis": _count(experiments, "state", "AWAITING_ANALYSIS"),
        },
    }
    return {key: {inner: value for inner, value in values.items() if value is not None}
            for key, values in facts.items()
            if any(value is not None for value in values.values())}


def project_database(path, app_id):
    """Read durable app facts from one SQLite snapshot without opening the runtime or vault."""
    path = Path(path)
    if not path.is_file():
        raise Invalid("Choose an existing WMM workspace database")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            row = db.execute("SELECT id,version,data FROM apps WHERE id=?", (app_id,)).fetchone()
            if row is None:
                raise Invalid("The selected app is not in this WMM workspace")
            facts = project({"app": dict(row, data=json.loads(row["data"]))})
            facts["metrics"] = {
                "cohort_count": db.execute(
                    "SELECT count(*) FROM records WHERE app_id=? AND kind='cohort'", (app_id,)).fetchone()[0],
                "retention_window_count": db.execute(
                    "SELECT count(*) FROM records WHERE app_id=? AND kind='retention'", (app_id,)).fetchone()[0],
            }
            campaign_count = db.execute(
                "SELECT count(DISTINCT campaign_token) FROM install_attribution_batches WHERE app_id=?",
                (app_id,)).fetchone()[0]
            facts["install"] = {"campaign_count": campaign_count}
            row = db.execute("""SELECT count(*) AS count,
                count(CASE WHEN state='PLANNED' THEN 1 END) AS planned,
                count(CASE WHEN state='AWAITING_ANALYSIS' THEN 1 END) AS awaiting_analysis
                FROM experiments WHERE app_id=?""", (app_id,)).fetchone()
            facts["experiments"] = dict(row)
            return facts
    except Invalid:
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError) as error:
        raise Invalid("Cannot read saved facts from this WMM workspace") from error


def validate(document):
    if not isinstance(document, dict):
        raise Invalid("Rules document must be an object")
    _exact(document, {"schema", "mode", "timezone", "rules"}, "rules document")
    if document["schema"] != SCHEMA:
        raise Invalid("Unsupported automation rules schema")
    if document["mode"] not in ("PROPOSE_ONLY", "AUTO_WITHIN_GRANT"):
        raise Invalid("Use PROPOSE_ONLY or AUTO_WITHIN_GRANT")
    _text(document["timezone"], "timezone", 100)
    if not isinstance(document["rules"], list) or not 1 <= len(document["rules"]) <= 100:
        raise Invalid("Use 1-100 rules")
    ids = set()
    rules = []
    for value in document["rules"]:
        rule = _rule(value)
        if rule["id"] in ids:
            raise Invalid("Rule ids must be unique")
        ids.add(rule["id"])
        rules.append(rule)
    return dict(schema=SCHEMA, mode=document["mode"], timezone=document["timezone"], rules=rules)


def _lookup(facts, path):
    value = facts
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return UNKNOWN, None
        value = value[part]
    return TRUE, value


def _compare(facts, item):
    status, value = _lookup(facts, item["fact"])
    if item["op"] == "exists":
        return TRUE if status == TRUE else FALSE
    if item["op"] == "missing":
        return FALSE if status == TRUE else TRUE
    if status != TRUE:
        return UNKNOWN
    op, expected = item["op"], item["value"]
    try:
        if op == "eq":
            return TRUE if value == expected else FALSE
        if op == "ne":
            return TRUE if value != expected else FALSE
        if op in ("gt", "gte", "lt", "lte"):
            if type(value) not in (int, float) or type(expected) not in (int, float):
                return UNKNOWN
            return TRUE if {"gt": value > expected, "gte": value >= expected,
                            "lt": value < expected, "lte": value <= expected}[op] else FALSE
        if op == "in":
            if not isinstance(expected, list):
                return UNKNOWN
            return TRUE if value in expected else FALSE
        if op == "contains":
            if isinstance(value, (list, str)) and isinstance(expected, (list, str, int, float)):
                return TRUE if expected in value else FALSE
            return UNKNOWN
    except (TypeError, ValueError):
        return UNKNOWN
    return UNKNOWN


def _evaluate(facts, condition):
    kind = condition["kind"]
    if kind == "compare":
        return _compare(facts, condition)
    if kind == "not":
        value = _evaluate(facts, condition["item"])
        return {"TRUE": FALSE, "FALSE": TRUE, "UNKNOWN": UNKNOWN}[value]
    values = [_evaluate(facts, item) for item in condition["items"]]
    if kind == "all":
        if FALSE in values:
            return FALSE
        return TRUE if all(value == TRUE for value in values) else UNKNOWN
    if TRUE in values:
        return TRUE
    return FALSE if all(value == FALSE for value in values) else UNKNOWN
    raise Invalid("Unknown condition kind")


def _missing(facts, condition):
    if condition["kind"] == "compare":
        return [condition["fact"]] if condition["op"] not in ("exists", "missing") and _lookup(facts, condition["fact"])[0] == UNKNOWN else []
    if condition["kind"] == "not":
        return _missing(facts, condition["item"])
    return sorted({path for item in condition["items"] for path in _missing(facts, item)})


def evaluate(document, facts, observed_at=None):
    rules = validate(document)
    if not isinstance(facts, dict):
        raise Invalid("Facts must be an object")
    stamp = observed_at or now()
    snapshot = digest(facts)
    results, proposals, seen = [], [], set()
    for rule in sorted(rules["rules"], key=lambda value: (-value["priority"], value["id"])):
        status = "DISABLED" if not rule["enabled"] else "ACTIVE"
        if rule["enabled"] and rule["expires_at"] and iso_time(rule["expires_at"]) <= iso_time(stamp):
            status = "EXPIRED"
        value = UNKNOWN
        if status == "ACTIVE":
            value = _evaluate(facts, rule["when"])
            status = "MATCH" if value == TRUE else "UNKNOWN" if value == UNKNOWN else "NO_MATCH"
        record = dict(rule_id=rule["id"], priority=rule["priority"], status=status,
                      condition=value, missing=_missing(facts, rule["when"]))
        results.append(record)
        if status != "MATCH":
            continue
        key = (rule["action"], rule["tool"])
        if key in seen:
            continue
        seen.add(key)
        proposal = dict(id=digest([rule["id"], snapshot, rule["action"], rule["tool"]]),
                        rule_id=rule["id"], priority=rule["priority"], status="PROPOSED",
                        action=rule["action"], tool=rule["tool"], reason=rule["reason"],
                        requires=rule["requires"], cooldown=rule["cooldown"],
                        fact_snapshot_sha256=snapshot, rule_sha256=digest(rule),
                        observed_at=stamp, mode=rules["mode"])
        proposals.append(proposal)
    return dict(schema="wmm.automation-evaluation.v1", mode=rules["mode"], timezone=rules["timezone"],
                facts_sha256=snapshot, observed_at=stamp, results=results, proposals=proposals,
                boundaries=["Proposals only; no publication, spend, provider or filesystem effect.",
                            "Missing facts never match; UNKNOWN is not success.",
                            "Exact approval or an existing grant is still required before any action."])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--facts")
    parser.add_argument("--database")
    parser.add_argument("--app")
    args = parser.parse_args(argv)
    document = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    if args.facts and (args.database or args.app):
        raise SystemExit("Use --facts or --database/--app, not both")
    if args.facts:
        facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    elif args.database and args.app:
        try:
            facts = project_database(args.database, args.app)
        except Invalid as error:
            parser.error(str(error))
    else:
        raise SystemExit("Provide --facts or both --database and --app")
    print(json.dumps(evaluate(document, facts), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
