"""Canonical bounded compact JWS decoding with an explicit native verifier boundary."""
import base64
import re
from .common import Invalid
from .payment_signature import strict_json
from .storekit_native import verify_apple


def url_decode(value, cap):
    """Reject padded, noncanonical, empty or oversized base64url parts."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise Invalid("StoreKit JWS encoding is invalid")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except ValueError as exc:
        raise Invalid("StoreKit JWS encoding is invalid") from exc
    if len(raw) > cap or base64.urlsafe_b64encode(raw).decode().rstrip("=") != value:
        raise Invalid("StoreKit JWS part is oversized or noncanonical")
    return raw


def certificates(header):
    """Reject all unsupported header behavior and cap every DER before native parsing."""
    if set(header) - {"alg", "x5c", "typ"} or header.get("alg") != "ES256":
        raise Invalid("StoreKit JWS header or algorithm is unsupported")
    if "typ" in header and header["typ"] != "JWT":
        raise Invalid("StoreKit JWS type is unsupported")
    chain = header.get("x5c")
    if not isinstance(chain, list) or len(chain) != 3:
        raise Invalid("StoreKit x5c must contain exactly three certificates")
    return tuple(certificate(item) for item in chain)


def certificate(value):
    """Require standard-base64 roundtrip and a finite native certificate input."""
    if not isinstance(value, str) or not 0 < len(value) <= 10924:
        raise Invalid("StoreKit certificate encoding is invalid")
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError as exc:
        raise Invalid("StoreKit certificate encoding is invalid") from exc
    if not 0 < len(raw) <= 8192 or base64.b64encode(raw).decode() != value:
        raise Invalid("StoreKit certificate is oversized or noncanonical")
    return raw


def verified_object(compact, verifier=verify_apple):
    """Authenticate exact ASCII signing bytes; unverified claims never escape."""
    if not isinstance(compact, str) or not 0 < len(compact) <= 131072:
        raise Invalid("StoreKit JWS size is invalid")
    parts = compact.split(".")
    if len(parts) != 3:
        raise Invalid("StoreKit compact JWS must have three parts")
    header = strict_json(url_decode(parts[0], 65536))
    payload = strict_json(url_decode(parts[1], 65536))
    signature = url_decode(parts[2], 64)
    if len(signature) != 64:
        raise Invalid("StoreKit ES256 signature must contain 64 bytes")
    certs = certificates(header)
    verifier(certs, (parts[0] + "." + parts[1]).encode("ascii"), signature)
    return payload
