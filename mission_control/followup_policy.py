"""Typed local follow-up contracts, with no contact data or delivery permission."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .common import Invalid, identifier, iso_time, required, safe_data


def zone(value):
    """Resolve the declared IANA zone without silently replacing missing data."""
    name = required(value, "IANA timezone", 100)
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise Invalid("Timezone data unavailable. Choose a supported IANA timezone; no fallback was applied.") from exc


def clock(value):
    """Accept a real 24-hour local wall clock, including midnight."""
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
        raise Invalid("Quiet hours require HH:MM in 24-hour local time")
    return value


def boolean(value, name):
    """Do not interpret strings or missing consent as authorization."""
    if type(value) is not bool:
        raise Invalid(name + ": choose Yes or No")
    return value


def validate(kind, data, observed):
    """Return normalized closed-schema input with explicit date bounds."""
    safe_data(data)
    validators = {"policy": policy, "subject": subject, "task": task}
    if kind not in validators:
        raise Invalid("Choose policy, subject or task")
    result = validators[kind](data, observed)
    if set(data) != set(result):
        raise Invalid("Follow-up contains missing or unsupported fields")
    return result


def policy(data, observed):
    """One-time enabled preparation never authorizes external delivery."""
    return {"enabled": boolean(data.get("enabled"), "Automatic preparation"),
            "cadence": required(data.get("cadence"), "Useful-value cadence", 2000),
            "prompt": required(data.get("prompt"), "Checkpoint prompt", 500)}


def subject(data, observed):
    """Validate supplied consent, zone and nonempty quiet-hour interval."""
    granted = iso_time(data.get("granted_at")); expires = iso_time(data.get("expires_at"))
    if granted > observed or expires <= granted:
        raise Invalid("Consent must have a nonfuture grant and a later expiration")
    start = clock(data.get("quiet_start")); end = clock(data.get("quiet_end"))
    if start == end:
        raise Invalid("Quiet-hour start and end must differ")
    return {"confirmed": boolean(data.get("confirmed"), "Supplied consent confirmed"),
            "source": required(data.get("source"), "Consent source", 2000),
            "granted_at": granted.isoformat(), "expires_at": expires.isoformat(),
            "timezone": zone(data.get("timezone")).key, "quiet_start": start, "quiet_end": end}


def task(data, observed):
    """Explicit UTC-offset times avoid ambiguous/nonexistent DST input."""
    due = iso_time(data.get("due_at")); expires = iso_time(data.get("expires_at"))
    if expires <= due or data.get("state") not in ("OPEN", "COMPLETED", "CANCELLED"):
        raise Invalid("Checkpoint needs a later expiration and OPEN, COMPLETED or CANCELLED state")
    return {"subject_id": identifier(data.get("subject_id")),
            "action": required(data.get("action"), "Useful checkpoint action", 500),
            "due_at": due.isoformat(), "expires_at": expires.isoformat(), "state": data["state"]}
