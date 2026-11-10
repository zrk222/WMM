"""Deterministic user-authored rules over supplied facts; proposals only, no effects."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import Invalid, canonical, digest, iso_time, now

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
    parser.add_argument("--facts", required=True)
    args = parser.parse_args(argv)
    document = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))
    print(json.dumps(evaluate(document, facts), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
