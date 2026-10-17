"""Shared input contracts. No credentials or personal conversations in records."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import uuid


class Invalid(ValueError):
    """Readable input error for the API."""


def canonical(value: dict) -> str:
    """Encode finite JSON values deterministically for evidence hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    """Hash canonical JSON bytes so review and source evidence remain bound."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def now():
    """Return an unambiguous UTC timestamp for durable records."""
    return datetime.now(timezone.utc).isoformat()


def uid():
    """Create a unique opaque record or job identity."""
    return str(uuid.uuid4())


def required(value, name, limit=4000):
    """Validate a bounded nonempty text field and normalize surrounding space."""
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise Invalid(f"{name}: enter text between 1 and {limit} characters")
    return value.strip()


def amount(value, name):
    """Reject negative, boolean or fractional minor-unit amounts and counts."""
    if type(value) is not int or value < 0:
        raise Invalid(f"{name}: enter a nonnegative whole number in minor currency units")
    return value


def fraction(value, name):
    """Validate a finite fraction in the closed interval from zero to one."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise Invalid(f"{name}: enter a fraction from 0 to 1")
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise Invalid(f"{name}: enter a fraction from 0 to 1")
    return value


def identifier(value):
    """Validate a portable app namespace without traversal or separator ambiguity."""
    value = required(value, "App ID", 60)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise Invalid("App ID: use lowercase letters, numbers and single hyphens")
    return value


def safe_data(value):
    """Validate finite record JSON and reject secrets or private conversation fields."""
    if not isinstance(value, dict):
        raise Invalid("Record data must be a JSON object")
    try:
        encoded = canonical(value)
    except (TypeError, ValueError) as exc:
        raise Invalid("Record data must contain finite JSON values") from exc
    if len(encoded.encode()) > 1048576:
        raise Invalid("Record exceeds 1 MB")
    forbidden = r'"(?:password|secret|token|api_key|access_token|private_key|client_secret|key_pem|chat_history|conversation|email|phone)"\s*:'
    if re.search(forbidden, encoded, re.I):
        raise Invalid("Do not store secrets, contacts or personal conversations here")
    if re.search(r"https?://[^\s/\"]+:[^\s/\"]+@",encoded,re.I):
        raise Invalid("Remove embedded credentials from source URLs")
    return value


def iso_time(value):
    """Parse an explicit timezone-bearing timestamp or reject ambiguous input."""
    try:
        parsed = datetime.fromisoformat(required(value, "Timestamp").replace("Z", "+00:00"))
    except ValueError as exc:
        raise Invalid("Use an ISO timestamp with timezone") from exc
    if parsed.tzinfo is None:
        raise Invalid("Timestamp requires timezone")
    return parsed
