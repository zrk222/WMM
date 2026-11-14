"""Resolve iOS launch status without treating a version state as public availability."""

from datetime import datetime, timedelta
from typing import Literal, TypedDict

from .common import Invalid, iso_time

LIVE_STATES = frozenset({"READY_FOR_DISTRIBUTION", "READY_FOR_SALE"})
REVIEW_STATES = frozenset({"WAITING_FOR_REVIEW", "IN_REVIEW"})
REMOVED_STATES = frozenset({"DEVELOPER_REMOVED_FROM_SALE", "REMOVED_FROM_SALE"})
FRESHNESS = timedelta(hours=24)
Status = Literal["UNKNOWN", "NOT_SUBMITTED", "IN_REVIEW", "LIVE", "REMOVED"]


class ConnectRead(TypedDict):
    observed_at: str
    complete: bool
    states: list[str]


class StorefrontRead(TypedDict):
    observed_at: str
    storefront: str
    state: Literal["AVAILABLE", "NOT_LISTED", "UNAVAILABLE"]


def fresh(observed_at: str, now: datetime) -> bool:
    return timedelta(0) <= now - iso_time(observed_at) <= FRESHNESS


def resolve(
    connect: ConnectRead | None,
    storefronts: list[StorefrontRead],
    now: datetime,
    *,
    previous_verified_live: bool = False,
) -> dict[str, object]:
    """Project already identity-checked reads for one app. Never grant campaign authority."""
    status: Status = "UNKNOWN"
    reason = "CURRENT_CONNECT_READ_REQUIRED"
    checked: dict[str, set[str]] = {}
    for item in storefronts:
        name = item["storefront"]
        if len(name) != 2 or not name.isascii() or not name.isalpha() or name != name.upper():
            raise Invalid("Use a two-letter uppercase storefront code")
        if fresh(item["observed_at"], now):
            checked.setdefault(name, set()).add(item["state"])
    available = sorted(name for name, states in checked.items() if states == {"AVAILABLE"})
    conflicting = any({"AVAILABLE", "NOT_LISTED"} <= states for states in checked.values())
    if connect and fresh(connect["observed_at"], now):
        states = set(connect["states"])
        if conflicting or (available and connect["complete"] and not states & LIVE_STATES):
            reason = "SOURCE_CONFLICT"
        elif states & LIVE_STATES:
            if available:
                status, reason = "LIVE", "CONNECT_AND_STOREFRONT_AGREE"
            else:
                reason = "CURRENT_STOREFRONT_PRESENCE_REQUIRED"
        elif not connect["complete"]:
            reason = "INCOMPLETE_VERSION_INVENTORY"
        elif states & REVIEW_STATES:
            status, reason = "IN_REVIEW", "CONNECT_REVIEW_PENDING"
        elif previous_verified_live and states & REMOVED_STATES and states <= REMOVED_STATES:
            status, reason = "REMOVED", "CONNECT_REMOVAL_AFTER_VERIFIED_LIVE"
        elif not previous_verified_live and states and states <= {"PREPARE_FOR_SUBMISSION"}:
            status, reason = "NOT_SUBMITTED", "CONNECT_PREPARING_FIRST_RELEASE"
        else:
            reason = "CONNECT_STATUS_INCONCLUSIVE"
    return {
        "status": status,
        "reason": reason,
        "verified_storefronts": available if status == "LIVE" else [],
        "observed_at": now.isoformat(),
        "authority_issued": False,
    }
