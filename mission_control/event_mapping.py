"""Finite event roles and current aggregate coverage, never cohort or payment proof."""
from datetime import datetime, timezone
import re
from .common import Invalid, digest, iso_time

ROLES = {
    "pageview": "Page viewed", "signup": "Registration completed",
    "activation": "First useful result", "value": "Repeat useful result",
    "purchase": "Purchase event", "exposure": "Experiment exposure",
}
DEFAULTS = dict(pageview="$pageview", signup="signup_completed",
                activation="activation_completed", value="",
                purchase="purchase_completed", exposure="")


def mapping(value):
    """Allow event labels only; never SQL, identifiers about people or freeform content."""
    if not isinstance(value, dict) or set(value) != set(ROLES):
        raise Invalid("Map exactly the six measurement roles; leave unknown event names empty")
    for name in value.values():
        if not isinstance(name, str) or (name and not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$.-]{0,79}", name)):
            raise Invalid("Event names allow 1–80 ASCII letters, digits, _, $, . or -; no spaces or quotes")
    names = [name for name in value.values() if name]
    if not names or len(names) != len(set(names)):
        raise Invalid("Map at least one event and use a distinct event name for each role")
    return dict(value)


def query(events):
    """Only validated finite labels enter the fixed project-wide count query."""
    names = sorted(name for name in mapping(events).values() if name)
    literals = ",".join("'" + name + "'" for name in names)
    return ("SELECT event, count() FROM events WHERE timestamp >= now() - INTERVAL 7 DAY "
            "AND event IN (" + literals + ") GROUP BY event LIMIT 100")


def role_rows(events, counts):
    """Distinguish no mapping, absent provider rows, explicit zero and positive counts."""
    rows = []
    for role, label in ROLES.items():
        name = events[role]
        value = counts.get(name) if name else None
        state = "NOT_MAPPED" if not name else "NOT_OBSERVED" if value is None else "NO_ACTIVITY" if value == 0 else "OBSERVED"
        rows.append(dict(role=role, label=label, event=name, count=value, state=state))
    return rows


def matching_report(source, reports):
    """Newest report only; an old connection or older success cannot stand in for it."""
    candidates = [r for r in reports if r.get("source_id") == source["id"]]
    if not candidates:
        return None
    report = candidates[0]
    data = report["data"]
    expected = {"source_version": source["version"], "configuration_hash": digest(source["data"]),
                "provider": "posthog", "project_id": source["data"]["project_id"],
                "event_map": mapping(source["data"].get("event_map", DEFAULTS))}
    if report.get("hash") != digest(data) or any(data.get(k) != v for k, v in expected.items()):
        return None
    return report


def recent(data):
    """Fail closed on stale, malformed or future observations."""
    try:
        age = (datetime.now(timezone.utc) - iso_time(data["observed_at"])).total_seconds()
    except (Invalid, KeyError, ValueError, TypeError):
        return False
    return 0 <= age <= 86400


def coverage(source, reports):
    """Project activity is descriptive; every stronger measurement claim stays separate."""
    events = mapping(source["data"].get("event_map", DEFAULTS))
    result = dict(state="READ_NEEDED", reason="Read the current event mapping to check coverage.",
                  roles=role_rows(events, {}), observation=None, scope="DEDICATED_PROJECT_LAST_7_DAYS",
                  release_verified=False, consent_verified=False, transaction_verified=False)
    if source["status"] != "CONNECTED":
        result.update(state="READ_BLOCKED", reason=source.get("last_error") or "Connect or retry this source before checking coverage.")
        return result
    report = matching_report(source, reports)
    if report is None:
        return result
    if not recent(report["data"]):
        result.update(state="STALE", reason="This observation is older than 24 hours or has an invalid time; refresh it.")
        return result
    counts = {r["id"]: r["value"] for r in report["data"]["rows"]}
    rows = role_rows(events, counts)
    complete = all(r["state"] == "OBSERVED" for r in rows)
    result.update(state="EVENT_COUNTS_OBSERVED" if complete else "COVERAGE_GAPS",
                  reason="All mapped roles have project activity; verify consent, build scope and transactions separately." if complete else "Map missing roles and check app instrumentation for events with no observed activity.",
                  roles=rows, observation=dict(id=report["id"], sha256=report["hash"], observed_at=report["data"]["observed_at"]))
    return result
