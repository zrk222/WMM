"""Fixed-provider OIDC verification with bounded, pinned HTTPS egress."""

import base64
import json
import math
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit

from . import aeo_transport as net

MAX_RESPONSE = 262144
DEADLINE_SECONDS = 20


class OIDCError(ValueError):
    """Generic failure; never include provider data or credentials."""


def fail():
    raise OIDCError("Authentication unavailable or invalid") from None


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            fail()
        result[key] = value
    return result


def strict_json(raw):
    try:
        result = json.loads(raw, object_pairs_hook=unique_pairs, parse_constant=lambda _: fail())
        if not isinstance(result, dict):
            fail()
        return result
    except (ValueError, UnicodeError, RecursionError):
        fail()


def text_field(value, limit=1024):
    return isinstance(value, str) and 0 < len(value) <= limit and not re.search(r"[\x00-\x1f\x7f]", value)


@dataclass(frozen=True)
class ProviderConfig:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    client_id: str
    client_secret: str = field(default=None, repr=False)
    display_label: str = "Sign in"

    def __post_init__(self):
        try:
            for value in (self.issuer, self.authorization_endpoint, self.token_endpoint, self.jwks_uri):
                if net.public_url(value) != value:
                    fail()
            if not text_field(self.client_id, 512) or not text_field(self.display_label, 128):
                fail()
            if self.client_secret is not None and not text_field(self.client_secret, 1024):
                fail()
        except (ValueError, TypeError):
            fail()


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str
    expires: float
    issued_at: float
    not_before: float = None


def dependencies_available():
    try:
        import jwt  # noqa: F401
        import cryptography  # noqa: F401

        return True
    except ImportError:
        return False


class ProviderTransport:
    """One request, no redirects, no ambient proxy, same caller deadline."""

    def request(self, url, method, body, deadline):
        try:
            host = urlsplit(url).hostname
            conn = net.PinnedHTTPS(host, net.address(host, deadline), net.trust_context(), deadline)
            try:
                headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
                if body is not None:
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                conn.request(method, urlsplit(url).path or "/", body=body, headers=headers)
                response = conn.getresponse()
                if response.status != 200:
                    fail()
                return net.response_body(response, net.response_headers(response), MAX_RESPONSE, conn, deadline)
            finally:
                conn.close()
        except Exception:
            fail()


def jwt_part(value):
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        fail()
    try:
        return strict_json(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)))
    except (ValueError, TypeError):
        fail()


def jwt_parts(token):
    if not text_field(token, MAX_RESPONSE):
        fail()
    parts = token.split(".")
    if len(parts) != 3 or not re.fullmatch(r"[A-Za-z0-9_-]+", parts[2]):
        fail()
    return jwt_part(parts[0]), jwt_part(parts[1])


def key_for(jwks, kid):
    keys = jwks.get("keys")
    if not isinstance(keys, list) or not 1 <= len(keys) <= 16:
        fail()
    seen = set()
    selected = None
    for key in keys:
        if not isinstance(key, dict) or not text_field(key.get("kid"), 256) or key["kid"] in seen:
            fail()
        if any(name in key for name in ("d", "p", "q", "dp", "dq", "qi", "oth", "x5u", "jku")):
            fail()
        seen.add(key["kid"])
        if key["kid"] == kid:
            selected = key
    if selected is None:
        fail()
    return selected


def public_key(key):
    if key.get("kty") != "RSA" or key.get("use", "sig") != "sig" or key.get("alg", "RS256") != "RS256":
        fail()
    if any(k in key for k in ("d", "p", "q", "dp", "dq", "qi", "oth", "x5u", "jku")):
        fail()
    if "key_ops" in key and key["key_ops"] != ["verify"]:
        fail()
    try:
        from jwt.algorithms import RSAAlgorithm

        value = RSAAlgorithm.from_jwk(key)
        if not 2048 <= value.key_size <= 8192:
            fail()
        return value
    except Exception:
        fail()


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def _audience_matches(aud, client_id):
    if aud == client_id:
        return True
    return isinstance(aud, list) and 1 <= len(aud) <= 16 and all(text_field(x, 512) for x in aud) and client_id in aud


def _validate_audience(claims, config):
    aud = claims.get("aud")
    azp = claims.get("azp")
    if not _audience_matches(aud, config.client_id):
        fail()
    if "azp" in claims and azp != config.client_id:
        fail()
    if isinstance(aud, list) and len(aud) > 1 and azp != config.client_id:
        fail()


def _validate_times(claims, now):
    exp, iat, nbf = claims.get("exp"), claims.get("iat"), claims.get("nbf")
    if not numeric(exp) or not numeric(iat) or ("nbf" in claims and not numeric(nbf)):
        fail()
    if exp <= now or iat > now + 5 or (nbf is not None and nbf > now):
        fail()
    return exp, iat, nbf


def validate_claims(claims, config, nonce, now):
    _validate_audience(claims, config)
    exp, iat, nbf = _validate_times(claims, now)
    if claims.get("iss") != config.issuer or not text_field(claims.get("sub"), 255) or claims.get("nonce") != nonce:
        fail()
    return Identity(config.issuer, claims["sub"], exp, iat, nbf)


class OIDCClient:
    def __init__(self, config, transport=None, clock=time.time):
        self.config, self.transport, self.clock = config, transport or ProviderTransport(), clock

    def authorization(self, state, nonce, verifier, redirect_uri):
        import hashlib

        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
        )
        fields = {
            "response_type": "code",
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return self.config.authorization_endpoint + "?" + urlencode(fields)

    def exchange(self, code, verifier, nonce, redirect_uri):
        if not dependencies_available() or not all(text_field(x, 4096) for x in (code, verifier, nonce, redirect_uri)):
            fail()
        fields = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.config.client_id,
            "code_verifier": verifier,
        }
        if self.config.client_secret is not None:
            fields["client_secret"] = self.config.client_secret
        deadline = time.monotonic() + DEADLINE_SECONDS
        try:
            raw = self.transport.request(self.config.token_endpoint, "POST", urlencode(fields).encode(), deadline)
            result = strict_json(raw)
            token = result.get("id_token")
            header, claims = jwt_parts(token)
            if (
                set(header) - {"alg", "kid", "typ"}
                or header.get("alg") != "RS256"
                or not text_field(header.get("kid"), 256)
            ):
                fail()
            jwks = strict_json(self.transport.request(self.config.jwks_uri, "GET", None, deadline))
            key = public_key(key_for(jwks, header["kid"]))
            import jwt

            jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                options={
                    "verify_exp": False,
                    "verify_iat": False,
                    "verify_nbf": False,
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_sub": False,
                },
            )
            return validate_claims(claims, self.config, nonce, self.clock())
        except Exception:
            fail()
