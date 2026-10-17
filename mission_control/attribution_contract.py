"""Bounded attribution wire types and separate signed/unsigned result semantics."""
import base64
import re
import uuid
from .common import Invalid, digest
from .payment_signature import strict_json


def require(condition, message):
    """Reject untrusted values with a bounded repair message."""
    if not condition:
        raise Invalid(message)


def body(raw):
    """Reuse the exact-byte duplicate/nonfinite/depth JSON boundary."""
    return strict_json(raw)


def fields(data, required, optional=()):
    """Reject unsupported fields instead of silently losing attribution meaning."""
    require(isinstance(data, dict) and set(required) <= set(data), "Attribution fields are missing")
    require(not set(data) - set(required) - set(optional), "Attribution fields are unsupported")


def integer(value, lower, upper):
    """Booleans, strings, floats and excessive provider IDs are not accepted integers."""
    require(type(value) is int and lower <= value <= upper, "Attribution integer is invalid")
    return value


def boolean(value):
    """No truthiness coercion is permitted for signed win or redownload claims."""
    require(type(value) is bool, "Attribution Boolean is invalid")
    return value


def identifier(value):
    """Bound an ASCII provider identifier without URLs or injected delimiters."""
    require(isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,254}", value),
            "Attribution identifier is invalid")
    return value


def postback_id(value):
    """Retain original signed case, but require UUID syntax for deduplication."""
    require(isinstance(value, str) and re.fullmatch(r"[A-Fa-f0-9]{8}(?:-[A-Fa-f0-9]{4}){3}-[A-Fa-f0-9]{12}", value),
            "Attribution postback identity is invalid")
    uuid.UUID(value)
    return value


def source_id(value):
    """Preserve privacy-truncated two-, three- or four-digit source identifiers."""
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{2,4}", value),
            "Attribution source identifier must retain two through four digits")
    return value


def environment_name(value):
    """Require a declared environment without inferring it from untrusted data."""
    require(value in ("Production", "Development"), "Attribution source environment is invalid")
    return value


def app_scope(value, expected):
    """Advertised app scope must be positive and exact before any claim is returned."""
    integer(expected, 1, 9223372036854775807)
    integer(value, 1, 9223372036854775807)
    require(value == expected, "Attribution belongs to another app")


def base64_bytes(value, cap, url=False):
    """Require canonical finite base64 with exactly the declared alphabet."""
    require(isinstance(value, str) and 0 < len(value) <= cap * 2, "Attribution encoding size is invalid")
    pattern = r"[A-Za-z0-9_-]+" if url else r"[A-Za-z0-9+/]+={0,2}"
    require(re.fullmatch(pattern, value), "Attribution encoding is invalid")
    padded = value + "=" * (-len(value) % 4) if url else value
    try:
        raw = base64.b64decode(padded, altchars=b"-_" if url else None, validate=True)
    except ValueError as exc:
        raise Invalid("Attribution encoding is invalid") from exc
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=") if url else base64.b64encode(raw).decode()
    require(0 < len(raw) <= cap and encoded == value, "Attribution encoding is noncanonical or oversized")
    return raw


def conversions(data, sequence):
    """Unsigned conversion values cannot prove activation, money or user outcomes."""
    require(not ("conversion-value" in data and "coarse-conversion-value" in data),
            "Choose only fine or coarse conversion value")
    fine, coarse = data.get("conversion-value"), data.get("coarse-conversion-value")
    if fine is not None:
        integer(fine, 0, 63)
        require(sequence == 0, "Fine conversion is unavailable after the first postback")
    if coarse is not None:
        require(coarse in ("low", "medium", "high"), "Coarse conversion value is invalid")
    return {"status": "UNSIGNED_OBSERVATION", "conversion_value": fine,
            "coarse_conversion_value": coarse,
            "availability": "AVAILABLE" if fine is not None or coarse is not None else "UNAVAILABLE"}


def result(channel, version, signed, unsigned, app_id, environment, postback, conversion, sequence, won):
    """Keep channels separate; follow-ups and redownloads are not new installs."""
    identity = digest({"channel": channel, "app_id": app_id, "environment": environment,
                       "postback_id": postback.lower()})
    return {"channel": channel, "version": version, "environment": environment,
            "app_id": app_id, "postback_id": postback.lower(), "identity": identity,
            "signed": signed, "signed_sha256": digest(signed), "unsigned": unsigned,
            "signature_status": "NATIVE_VERIFIED", "conversion_type": conversion,
            "sequence": sequence, "did_win": won,
            "new_install_candidate": won and sequence == 0 and conversion == "download",
            "overlap_status": "UNRESOLVED", "current_ingestion_authority": False}
