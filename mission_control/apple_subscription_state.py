"""Classify Apple Subscription State Standard rows without retaining private dimensions."""

import re

from .common import Invalid

REQUIRED_FIELDS = frozenset({"date", "app apple identifier", "state metric", "state metric grouping", "counts"})
# Apple documents these as disjoint states in the daily subscription snapshot.
STATES = {
    "Full price": ("paid plans", "active_paid"),
    "Preserved price": ("paid plans", "active_paid"),
    "Contingent price": ("paid plans", "active_paid"),
    "Paid offers": ("subscription offers", "active_paid"),
    "Free trials": ("subscription offers", "other_subscription_state"),
    "Grace period": ("billing issue", "other_subscription_state"),
    "Billing retry": ("billing issue", "other_subscription_state"),
    "Suspended": ("billing issue", "other_subscription_state"),
    "Voluntarily churned": ("churned", "other_subscription_state"),
    "Involuntarily churned": ("churned", "other_subscription_state"),
}
CLASSIFIED = {(name.casefold(), group): (name, kind) for name, (group, kind) in STATES.items()}
UNKNOWN = "Unknown state"


def observation(row: dict[str, str], day: str) -> dict:
    metric = " ".join(row["state metric"].split()).casefold()
    group = " ".join(row["state metric grouping"].split()).casefold()
    count = row["counts"]
    if not metric or not group or re.fullmatch(r"[0-9]{1,15}", count) is None:
        raise Invalid("Invalid Apple subscription state or count")
    name, kind = CLASSIFIED.get((metric, group), (UNKNOWN, "unknown"))
    return dict(date=day, source_type=name, type=kind, count=int(count), dimensions={})


def validate_observation(row: dict) -> None:
    source = row.get("source_type")
    known = STATES.get(source) if isinstance(source, str) else None
    kind = "unknown" if source == UNKNOWN else known[1] if known else None
    if (
        kind is None
        or row.get("type") != kind
        or type(row.get("count")) is not int
        or not 0 <= row["count"] < 10**15
        or row.get("dimensions") != {}
    ):
        raise Invalid("Invalid retained Apple subscription state")
