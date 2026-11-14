"""Join consented acquisition and billing observations for one app and campaign."""

import re
from datetime import datetime
from typing import TypedDict, cast

from .common import Invalid, digest, iso_time

STAGES = ("TOUCH", "INSTALL", "ACTIVATION", "TRIAL_START", "PURCHASE", "RENEWAL")
PRODUCT_STAGES = STAGES[:3]
HASH = re.compile(r"[a-f0-9]{64}")
OPAQUE = re.compile(r"[A-Za-z0-9_-]{1,128}")
MAX_EVENTS = 25_000


class OutcomeEvent(TypedDict):
    event_id: str
    subject_sha256: str
    kind: str
    occurred_at: str
    campaign: str | None
    consented: bool
    internal_test: bool


class OutcomeBatch(TypedDict):
    app_id: str
    environment: str
    provider: str
    source_sha256: str
    identity_namespace_sha256: str
    coverage_from: str
    coverage_through: str
    complete: bool
    events: list[OutcomeEvent]


def normalized_batch(value: object) -> OutcomeBatch:
    """Validate the private normalized interchange format before matching subjects."""
    if not isinstance(value, dict) or set(value) != OutcomeBatch.__required_keys__:
        raise Invalid("Outcome batch has unsupported or missing fields")
    for field in ("app_id", "environment", "provider", "coverage_from", "coverage_through"):
        if not isinstance(value[field], str) or not 1 <= len(value[field]) <= 128:
            raise Invalid("Outcome batch scope and dates must be bounded text")
    for field in ("source_sha256", "identity_namespace_sha256"):
        if not isinstance(value[field], str) or not HASH.fullmatch(value[field]):
            raise Invalid("Outcome batch needs valid provenance and identity fingerprints")
    if (
        type(value["complete"]) is not bool
        or not isinstance(value["events"], list)
        or len(value["events"]) > MAX_EVENTS
    ):
        raise Invalid("Outcome batch needs explicit coverage and a bounded event list")
    for event in value["events"]:
        if not isinstance(event, dict) or set(event) != OutcomeEvent.__required_keys__:
            raise Invalid("Outcome event has unsupported or missing fields")
        if any(
            not isinstance(event[field], str) or not OPAQUE.fullmatch(event[field]) for field in ("event_id", "kind")
        ):
            raise Invalid("Outcome event IDs and types must be opaque tokens")
        if not isinstance(event["subject_sha256"], str) or not HASH.fullmatch(event["subject_sha256"]):
            raise Invalid("Outcome events need app-scoped pseudonymous fingerprints")
        if event["campaign"] is not None and (
            not isinstance(event["campaign"], str) or not OPAQUE.fullmatch(event["campaign"])
        ):
            raise Invalid("Outcome campaign must be an opaque token")
        if (
            not isinstance(event["occurred_at"], str)
            or not 1 <= len(event["occurred_at"]) <= 128
            or type(event["consented"]) is not bool
            or type(event["internal_test"]) is not bool
        ):
            raise Invalid("Outcome events need explicit consent, internal-test status and a bounded timestamp")
    return cast(OutcomeBatch, value)


def join(
    app_id: str,
    environment: str,
    campaign: str,
    starts_at: str,
    ends_at: str,
    matures_at: str,
    as_of: str,
    product: OutcomeBatch,
    billing: OutcomeBatch,
) -> dict[str, object]:
    """Project first observed touches in the declared coverage; never infer identities."""
    product, billing = normalized_batch(product), normalized_batch(billing)
    start, end, maturity, cutoff = map(iso_time, (starts_at, ends_at, matures_at, as_of))
    if not campaign or not start < end <= maturity:
        raise Invalid("Outcome join needs a campaign and ordered acquisition and maturity windows")
    namespace = product["identity_namespace_sha256"]
    if not HASH.fullmatch(namespace):
        raise Invalid("Outcome sources need a shared app-specific identity namespace")
    events: dict[str, list[tuple[datetime, str, str | None]]] = {}
    excluded: dict[str, int] = {"ineligible_events": 0, "unmatched_paid_subjects": 0}
    complete = cutoff >= maturity
    for batch, provider, allowed in (
        (product, "posthog", PRODUCT_STAGES),
        (billing, "revenuecat", STAGES[3:]),
    ):
        through = iso_time(batch["coverage_through"])
        since = iso_time(batch["coverage_from"])
        if (
            (batch["app_id"], batch["environment"], batch["provider"]) != (app_id, environment, provider)
            or batch["identity_namespace_sha256"] != namespace
            or not HASH.fullmatch(batch["source_sha256"])
            or not since <= through <= cutoff
        ):
            raise Invalid("Outcome source scope, lineage, or coverage differs")
        complete = complete and batch["complete"] is True and since <= start and through >= maturity
        seen: dict[str, str] = {}
        for row in batch["events"]:
            stamp = iso_time(row["occurred_at"])
            subject, kind, row_campaign = row["subject_sha256"], row["kind"], row["campaign"]
            if (
                not row["event_id"]
                or not HASH.fullmatch(subject)
                or kind not in allowed
                or (row_campaign is not None and (kind != "TOUCH" or not row_campaign))
                or not since <= stamp <= through
            ):
                raise Invalid("Outcome event does not match the admitted source contract")
            fingerprint = digest(row)
            prior = seen.get(row["event_id"])
            if prior is not None:
                if prior != fingerprint:
                    raise Invalid("Conflicting outcome event identity")
                continue
            seen[row["event_id"]] = fingerprint
            if row["consented"] is not True or row["internal_test"] is not False:
                excluded["ineligible_events"] += 1
                continue
            if stamp <= maturity:
                events.setdefault(subject, []).append((stamp, kind, row_campaign))
    counts = dict.fromkeys(STAGES[1:], 0)
    for rows in events.values():
        observed = {kind: min((stamp for stamp, name, _ in rows if name == kind), default=None) for kind in STAGES}
        touch, install = observed["TOUCH"], observed["INSTALL"]
        if (
            touch is None
            or install is None
            or not start <= touch < install < end
            or {tag for stamp, kind, tag in rows if kind == "TOUCH" and stamp == touch} != {campaign}
        ):
            excluded["unmatched_paid_subjects"] += int(observed["PURCHASE"] is not None)
            continue
        counts["INSTALL"] += 1
        previous = install
        for kind in STAGES[2:]:
            stamp = observed[kind]
            if stamp is None or stamp < previous:
                break
            counts[kind] += 1
            previous = stamp
    return {
        "schema": "wmm.first-party-outcomes.v1",
        "app_id": app_id,
        "environment": environment,
        "campaign": campaign,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "matures_at": matures_at,
        "as_of": as_of,
        "attribution": "FIRST_OBSERVED_TOUCH_WITHIN_SOURCE_COVERAGE",
        "install_definition": "SOURCE_REPORTED_FIRST_OPEN",
        "counts": {kind: value if value or complete else None for kind, value in counts.items()},
        "excluded": excluded,
        "coverage": "DECLARED_COMPLETE" if complete else "PARTIAL",
        "provenance": "NORMALIZED_INPUT_NOT_PROVIDER_VERIFIED",
        "source_sha256": digest(
            [dict(batch, events=sorted({digest(event) for event in batch["events"]})) for batch in (product, billing)]
        ),
        "incrementality_measured": False,
    }
