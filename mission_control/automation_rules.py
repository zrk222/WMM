"""Deterministic user-authored rules over supplied facts; proposals only, no effects."""

from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
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


def _condition(value, depth=0):
    if depth > 16:
        raise Invalid("Use at most 16 nested condition levels")
    if not isinstance(value, dict) or not value:
        raise Invalid("Every condition must be a non-empty object")
    keys = set(value)
    if keys in ({"fact", "op", "value"}, {"fact", "op"}):
        fact = _text(value["fact"], "fact path", 200)
        if any(not part or part.strip() != part for part in fact.split(".")):
            raise Invalid("Conditions need a dotted fact path")
        op = value["op"]
        if not isinstance(op, str) or op not in COMPARISONS:
            raise Invalid("Unsupported condition operator")
        if op not in ("exists", "missing") and "value" not in value:
            raise Invalid("Comparisons need a value")
        expected = value.get("value")
        try:
            digest(expected)
        except (TypeError, ValueError, RecursionError) as error:
            raise Invalid("Comparison values must be finite JSON") from error
        return dict(kind="compare", fact=fact, op=op, value=expected)
    if keys == {"all"}:
        if not isinstance(value["all"], list) or not 1 <= len(value["all"]) <= 50:
            raise Invalid("Use 1-50 all conditions")
        return dict(kind="all", items=[_condition(item, depth + 1) for item in value["all"]])
    if keys == {"any"}:
        if not isinstance(value["any"], list) or not 1 <= len(value["any"]) <= 50:
            raise Invalid("Use 1-50 any conditions")
        return dict(kind="any", items=[_condition(item, depth + 1) for item in value["any"]])
    if keys == {"not"}:
        return dict(kind="not", item=_condition(value["not"], depth + 1))
    raise Invalid("Use one of all, any, not or a fact comparison")


def _rule(value):
    if not isinstance(value, dict):
        raise Invalid("Every rule must be an object")
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
    if (
        not isinstance(requires, list)
        or not requires
        or len(requires) > 10
        or any(not isinstance(item, str) or not item for item in requires)
    ):
        raise Invalid("Proposals need 1-10 named approvals")
    cooldown = value.get("cooldown", "")
    if cooldown and (not isinstance(cooldown, str) or len(cooldown) > 40):
        raise Invalid("Use an ISO 8601-style cooldown label")
    expires = value.get("expires_at")
    if expires is not None:
        iso_time(expires)
    return dict(
        id=value["id"],
        enabled=value["enabled"],
        priority=value["priority"],
        when=when,
        action=action,
        tool=tool,
        reason=reason,
        requires=list(requires),
        cooldown=cooldown,
        expires_at=expires,
    )


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
            "campaign_tokens": (
                sorted(row.get("campaign_token") for row in campaigns if row.get("campaign_token"))
                if campaigns is not None
                else None
            ),
            "last_observed_at": max(
                (row.get("last_observed_at") for row in campaigns or [] if row.get("last_observed_at")), default=None
            ),
        },
        "measurement": {"state": integrity.get("state")},
        "experiments": {
            "count": _count(experiments),
            "planned": _count(experiments, "state", "PLANNED"),
            "awaiting_analysis": _count(experiments, "state", "AWAITING_ANALYSIS"),
        },
    }
    return {
        key: {inner: value for inner, value in values.items() if value is not None}
        for key, values in facts.items()
        if any(value is not None for value in values.values())
    }


@contextmanager
def _database_snapshot(path, app_id, owner_principal):
    """Pin owner, rule and facts to one read-only SQLite snapshot."""
    path = Path(path)
    if not path.is_file():
        raise Invalid("Choose an existing WMM workspace database")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if owner_principal is not None:
                from .review_access import member

                member(db, app_id, owner_principal, "OWNER")
            yield db
    except (Invalid, PermissionError):
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError, AttributeError) as error:
        raise Invalid("Cannot read saved facts from this WMM workspace") from error


FACT_SOURCES = {
    "app": "Saved app manifest",
    "metrics": "Saved evidence record counts; no measured metric inferred",
    "install": "Campaigns with saved install import batches; no install count inferred",
    "experiments": "Saved experiment lifecycle counts",
    "jobs": "Saved local worker state counts; no provider result inferred",
    "study": "Selected study and saved collector receipts; descriptive only",
}


def _project_snapshot(db, app_id):
    app = db.execute("SELECT id,version,data FROM apps WHERE id=?", (app_id,)).fetchone()
    if app is None:
        raise Invalid("The selected app is not in this WMM workspace")
    facts = project({"app": dict(app, data=json.loads(app["data"]))})
    counts = db.execute(
        """SELECT count(CASE WHEN kind='cohort' THEN 1 END) AS cohort_count,
        count(CASE WHEN kind='retention' THEN 1 END) AS retention_window_count
        FROM records WHERE app_id=? AND kind IN ('cohort','retention')""",
        (app_id,),
    ).fetchone()
    facts["metrics"] = dict(counts)
    campaign_count = db.execute(
        "SELECT count(DISTINCT campaign_token) FROM install_attribution_batches WHERE app_id=?", (app_id,)
    ).fetchone()[0]
    facts["install"] = {"campaign_count": campaign_count}
    experiments = db.execute(
        """SELECT count(*) AS count,
        count(CASE WHEN state='PLANNED' THEN 1 END) AS planned,
        count(CASE WHEN state='AWAITING_ANALYSIS' THEN 1 END) AS awaiting_analysis
        FROM experiments WHERE app_id=?""",
        (app_id,),
    ).fetchone()
    facts["experiments"] = dict(experiments)
    jobs = db.execute(
        """SELECT count(CASE WHEN status='QUEUED' THEN 1 END) AS queued,
        count(CASE WHEN status='RUNNING' THEN 1 END) AS running,
        count(CASE WHEN status='UNKNOWN' THEN 1 END) AS unknown
        FROM jobs WHERE app_id=? AND action!='drive_import' AND status IN ('QUEUED','RUNNING','UNKNOWN')""",
        (app_id,),
    ).fetchone()
    facts["jobs"] = dict(jobs)
    return facts


def project_database(path, app_id, *, owner_principal=None):
    """Read durable app facts without opening the runtime or vault."""
    with _database_snapshot(path, app_id, owner_principal) as db:
        return _project_snapshot(db, app_id)


def _study_facts(db, app_id, reference, observed_at):
    from .observational_campaign import _app, _manifest, _study, report_in_snapshot

    _exact(reference, {"study_id", "study_hash", "manifest_version"}, "Study reference")
    app = _app(db, app_id)
    _manifest(reference, app)
    study = _study(db, app_id, reference["study_id"], reference["study_hash"], app)
    report = report_in_snapshot(db, app_id, study, app, observed_at)
    checkpoint = report["checkpoint"]
    counts = checkpoint["ratio_counts"]
    ready = checkpoint["state"] in ("DESCRIPTIVE_READY", "NO_ELIGIBLE_LANDINGS")
    facts = dict(
        id=study["id"],
        definition_sha256=study["hash"],
        manifest_version=app["version"],
        source_sha256=report["source_hash"],
        provenance=report["provenance"],
        coverage="COMPLETE" if ready else "INCOMPLETE",
        checkpoint=checkpoint["state"],
        window=dict(
            starts_at=report["starts_at"],
            ends_at=report["ends_at"],
            state="COLLECTING" if iso_time(observed_at) < iso_time(report["ends_at"]) else "ENDED",
        ),
    )
    if counts:
        facts.update(counts, linked_registration_rate=counts["linked_registrations"] / counts["eligible_landings"])
    elif ready:
        facts.update(
            eligible_landings=report["landing_subjects"], linked_registrations=report["linked_registration_subjects"]
        )
    return facts


def simulate_database(path, app_id, owner_principal, *, rules=None, reference=None, study=None):
    if not owner_principal:
        raise PermissionError("A verified owner is required")
    observed_at = now()
    with _database_snapshot(path, app_id, owner_principal) as db:
        binding = None
        if reference is not None:
            from .automation_store import version_in_snapshot

            saved = version_in_snapshot(db, app_id, reference)
            binding = {key: saved[key] for key in ("app_id", "version", "hash")}
            rules = saved["document"]
        facts = _project_snapshot(db, app_id)
        if study is not None:
            facts["study"] = _study_facts(db, app_id, study, observed_at)
    result = evaluate(rules, facts, observed_at=observed_at, binding=binding)
    return {**result, "fact_snapshot": {"sources": FACT_SOURCES, "values": facts}}


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
    return (UNKNOWN, None) if value is None else (TRUE, value)


def _equality(value, expected):
    if value is None or expected is None:
        return UNKNOWN
    if type(value) in (int, float) and type(expected) in (int, float):
        return TRUE if value == expected else FALSE
    if type(value) is not type(expected):
        return UNKNOWN
    if isinstance(value, list):
        if len(value) != len(expected):
            return FALSE
        return _all_values(_equality(a, b) for a, b in zip(value, expected))
    if isinstance(value, dict):
        if value.keys() != expected.keys():
            return FALSE
        return _all_values(_equality(value[key], expected[key]) for key in value)
    return TRUE if value == expected else FALSE


def _all_values(values):
    values = list(values)
    return FALSE if FALSE in values else UNKNOWN if UNKNOWN in values else TRUE


def _any_values(values):
    values = list(values)
    return TRUE if TRUE in values else UNKNOWN if UNKNOWN in values else FALSE


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
        if op in ("eq", "ne"):
            result = _equality(value, expected)
            return result if op == "eq" or result == UNKNOWN else FALSE if result == TRUE else TRUE
        if op in ("gt", "gte", "lt", "lte"):
            if type(value) not in (int, float) or type(expected) not in (int, float):
                return UNKNOWN
            return (
                TRUE
                if {"gt": value > expected, "gte": value >= expected, "lt": value < expected, "lte": value <= expected}[
                    op
                ]
                else FALSE
            )
        if op == "in":
            if not isinstance(expected, list):
                return UNKNOWN
            return _any_values(_equality(value, option) for option in expected)
        if op == "contains":
            if isinstance(value, list):
                return _any_values(_equality(option, expected) for option in value)
            if isinstance(value, str) and isinstance(expected, str):
                return TRUE if expected in value else FALSE
            return UNKNOWN
    except (TypeError, ValueError):
        return UNKNOWN
    return UNKNOWN


def _evaluate(facts, condition, gaps):
    kind = condition["kind"]
    if kind == "compare":
        result = _compare(facts, condition)
        if result == UNKNOWN:
            path = condition["fact"]
            key = "missing" if _lookup(facts, path)[0] == UNKNOWN else "incompatible"
            gaps[key].add(path)
        return result
    if kind == "not":
        value = _evaluate(facts, condition["item"], gaps)
        return {"TRUE": FALSE, "FALSE": TRUE, "UNKNOWN": UNKNOWN}[value]
    values = (_evaluate(facts, item, gaps) for item in condition["items"])
    if kind == "all":
        return _all_values(values)
    if kind == "any":
        return _any_values(values)
    raise Invalid("Unknown condition kind")


def evaluate(document, facts, observed_at=None, *, binding=None):
    rules = validate(document)
    if not isinstance(facts, dict):
        raise Invalid("Facts must be an object")
    stamp = observed_at or now()
    iso_time(stamp)
    try:
        snapshot = digest(facts)
    except (ValueError, TypeError, RecursionError) as error:
        raise Invalid("Facts must be finite JSON") from error
    rule_set = digest(rules)
    if binding is not None and binding["hash"] != rule_set:
        raise Invalid("Saved rule fingerprint does not match its contents")
    version = binding["version"] if binding else None
    results, proposals, seen = [], [], set()
    for rule in sorted(rules["rules"], key=lambda value: (-value["priority"], value["id"])):
        status = "DISABLED" if not rule["enabled"] else "ACTIVE"
        if rule["enabled"] and rule["expires_at"] and iso_time(rule["expires_at"]) <= iso_time(stamp):
            status = "EXPIRED"
        value = UNKNOWN
        gaps = {"missing": set(), "incompatible": set()}
        if status == "ACTIVE":
            value = _evaluate(facts, rule["when"], gaps)
            status = "MATCH" if value == TRUE else "UNKNOWN" if value == UNKNOWN else "NO_MATCH"
        record = dict(
            rule_id=rule["id"],
            priority=rule["priority"],
            status=status,
            condition=value,
            **{key: sorted(paths) for key, paths in gaps.items()},
        )
        results.append(record)
        if status != "MATCH":
            continue
        key = (rule["action"], rule["tool"])
        if key in seen:
            record["proposal_status"] = "SUPPRESSED_BY_HIGHER_PRIORITY"
            continue
        seen.add(key)
        record["proposal_status"] = "PROPOSED"
        proposal = dict(
            id=digest([rule_set, version, rule["id"], snapshot, rule["action"], rule["tool"]]),
            rule_id=rule["id"],
            priority=rule["priority"],
            status="PROPOSED",
            action=rule["action"],
            tool=rule["tool"],
            reason=rule["reason"],
            requires=rule["requires"],
            cooldown=rule["cooldown"],
            fact_snapshot_sha256=snapshot,
            rule_sha256=digest(rule),
            rule_set_sha256=rule_set,
            rule_version=version,
            observed_at=stamp,
            mode=rules["mode"],
        )
        proposals.append(proposal)
    report = dict(
        schema="wmm.automation-evaluation.v1",
        evaluator_version=2,
        mode=rules["mode"],
        timezone=rules["timezone"],
        rules_sha256=rule_set,
        rule_binding=binding,
        facts_sha256=snapshot,
        observed_at=stamp,
        results=results,
        proposals=proposals,
        boundaries=[
            "Proposals only; no publication, spend, provider or filesystem effect.",
            "Unavailable facts cannot satisfy comparisons; explicit missing checks can match.",
            "Exact approval or an existing grant is still required before any action.",
        ],
    )
    return {**report, "evaluation_sha256": digest(report)}


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
