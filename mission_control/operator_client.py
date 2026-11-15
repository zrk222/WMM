"""Bounded local HTTP transport. No proxy, redirect, credential loading or auto retry."""

import json
import re
from http.client import HTTPException
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .common import Invalid, canonical
from .operation_catalog import request_data

MAX_BYTES = 16777216
MAX_JSON_DEPTH = 64
TIMEOUT_SECONDS = 15


def request_timeout(path, body):
    """Fixed longer observation bounds for approved synchronous local Studio work."""
    operation = body.get("operation") if isinstance(body, dict) else None
    actions = ("plan", "start", "sessions", "read", "edit", "inspect", "close")
    if path == "/api/agent-operations/call" and operation in tuple("studio." + a for a in actions):
        return 900
    if re.fullmatch(r"/api/apps/[a-z0-9-]+/studio/(?:[a-z0-9-]+/)?(?:" + "|".join(actions) + ")", path):
        return 900
    if path == "/api/agent-operations/reviews/resume":
        return 900
    return TIMEOUT_SECONDS


class ClientError(Exception):
    """Stable failure classification without dumping raw server responses or credentials."""

    def __init__(self, code, message, status=None, outcome=None, reconciliation_required=False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.outcome = outcome
        self.reconciliation_required = reconciliation_required


def error_fields(error):
    value = dict(code=error.code, message=str(error), http_status=error.status)
    if error.outcome is not None:
        value.update(outcome=error.outcome, reconciliation_required=error.reconciliation_required)
    return value


_SIGN_IN_REASONS = frozenset(
    (
        "Sign in with GitHub before changing verified access or reviews",
        "Authenticated operator session changed; sign in again",
        "Authenticated operator session was replaced; sign in again",
        "Authenticated identity changed; sign in again",
    )
)
_ROLE_REASONS = frozenset(
    ("This GitHub account has no active role in this app", "This action requires the app's owner role")
)
_SESSION_REASONS = frozenset(
    (
        "Reload the current research session",
        "Reload the current campaign session",
        "Session expired; reload before saving",
    )
)


def rejection_envelope(error):
    """Read at most one small JSON object without exposing server text."""
    if error.code not in (403, 409):
        return {}
    try:
        if error.headers.get_content_type() != "application/json":
            return {}
        raw = error.read(4097)
        if len(raw) > 4096:
            return {}
        value = strict_json(raw)
        return value if type(value) is dict else {}
    except (OSError, ValueError, Invalid, HTTPException):
        return {}


def access_error(value, grant):
    """Translate only exact local reasons; unfamiliar messages remain private."""
    reason = value.get("error")
    if grant:
        return "AGENT_ACCESS_DENIED", "Ask the owner to check this agent grant for the app and operation."
    if set(value) == {"error"} and type(reason) is str:
        if reason in _SIGN_IN_REASONS:
            return (
                "SIGN_IN_REQUIRED",
                "Sign in with GitHub in WMM to continue as the owner. For an agent or CLI, use a scoped WMM agent grant.",
            )
        if reason in _ROLE_REASONS:
            return "APP_ACCESS_REQUIRED", "Use the account that owns this app in WMM, or ask the app owner for access."
        if reason in _SESSION_REASONS:
            return (
                "SESSION_REFRESH_REQUIRED",
                "Reopen WMM to refresh your session, then review your request before retrying.",
            )
    return "ACCESS_DENIED", "Check the app and your WMM access. Ask the owner to review access if this continues."


class NoRedirect(HTTPRedirectHandler):
    """Never forward a session or POST to a redirected destination."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ClientError("REDIRECT_REJECTED", "The local server redirected the request; no follow-up was sent", code)


def origin_data(value):
    """Allow only a literal canonical IPv4 loopback origin with an explicit valid port."""
    if not isinstance(value, str):
        raise Invalid("Use http://127.0.0.1:PORT as the WMM origin")
    match = re.fullmatch(r"http://127\.0\.0\.1:([1-9][0-9]{0,4})", value)
    if not match or int(match[1]) > 65535:
        raise Invalid("Use http://127.0.0.1:PORT with a port from 1 through 65535")
    return value


def unique_pairs(pairs):
    """Reject duplicate keys instead of accepting a different caller/server interpretation."""
    value = {}
    for key, item in pairs:
        if key in value:
            raise Invalid("Duplicate JSON keys are forbidden")
        value[key] = item
    return value


def invalid_constant(value):
    """Keep NaN and infinity out of transport data."""
    raise Invalid("Nonfinite JSON values are forbidden")


def validate_json_depth(text):
    """Reject excessive containers before parsing; quoted delimiters are ordinary text."""
    depth = 0
    quoted = False
    escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise Invalid("JSON exceeds the 64 container nesting limit")
        elif char in "]}":
            depth -= 1


def strict_json(raw: bytes) -> Any:
    """Bound bytes and reject malformed UTF-8, duplicate keys, constants and deep trees."""
    if len(raw) > MAX_BYTES:
        raise Invalid("JSON exceeds the 16777216 bytes limit")
    try:
        text = raw.decode("utf-8")
        validate_json_depth(text)
        value = json.loads(text, object_pairs_hook=unique_pairs, parse_constant=invalid_constant)
        # Re-encoding also rejects values overflowing JSON's finite numeric range.
        canonical(value)
        return value
    except Invalid:
        raise
    except (UnicodeError, ValueError, RecursionError) as error:
        raise Invalid("Invalid strict UTF-8 JSON: " + type(error).__name__) from error


def response_data(response):
    """Require bounded JSON; do not print a remote HTML error document."""
    if response.headers.get_content_type() != "application/json":
        raise ClientError("INVALID_RESPONSE", "WMM returned a non-JSON response")
    raw = response.read(MAX_BYTES + 1)
    try:
        return strict_json(raw)
    except Invalid as error:
        raise ClientError("INVALID_RESPONSE", str(error)) from error


def reject_http(error, path, body):
    """Classify one closed HTTP failure without retrying an uncertain mutation."""
    try:
        value = rejection_envelope(error)
    finally:
        error.close()
    if error.code == 403:
        code, message = access_error(value, path.startswith("/api/agent-operations/"))
        raise ClientError(code, message, error.code) from None
    if (
        error.code == 409
        and set(value) == {"error", "outcome", "reconciliation_required"}
        and type(value["error"]) is str
        and value["outcome"] == "UNKNOWN"
        and value["reconciliation_required"] is True
    ):
        raise ClientError(
            "OUTCOME_UNKNOWN",
            "Local operation outcome is uncertain; inspect the saved attempt before retrying",
            error.code,
            outcome="UNKNOWN",
            reconciliation_required=True,
        ) from None
    if error.code == 409 and request_timeout(path, body) == 900:
        raise ClientError(
            "RESULT_UNCONFIRMED",
            "The local operation result is unconfirmed; inspect saved history before any retry.",
            error.code,
            outcome="UNKNOWN",
            reconciliation_required=True,
        ) from None
    raise ClientError(
        "HTTP_REJECTED",
        "WMM rejected the operation; HTTP " + str(error.code) + ". Refresh current app/source data before retrying.",
        error.code,
    ) from error


class OperatorClient:
    """Use existing trusted-local API semantics; this client grants no extra authority."""

    def __init__(self, origin, grant_token=None):
        self.origin = origin_data(origin)
        if grant_token is not None and (
            not isinstance(grant_token, str) or not re.fullmatch(r"wmmg_[A-Za-z0-9_-]{43}", grant_token)
        ):
            raise Invalid("Use a valid WMM agent grant credential")
        self.grant_token = grant_token
        self.csrf = None
        self.cookies = CookieJar()
        self.opener = build_opener(ProxyHandler({}), HTTPCookieProcessor(self.cookies), NoRedirect())

    def bootstrap(self):
        """Retain the session in RAM only and discard every other bootstrap field."""
        result = self.request("GET", "/api/bootstrap")
        token = result.get("csrf") if isinstance(result, dict) else None
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{20,256}", token):
            raise ClientError("INVALID_SESSION", "WMM bootstrap did not provide a valid CSRF token")
        self.csrf = token

    def call(self, envelope):
        """Resolve the fixed catalog before networking; retry policy is always caller controlled."""
        value = request_data(envelope)
        # Validate serialization and size before creating a session.
        encode_body(value["body"])
        if self.grant_token is not None:
            return self.request("POST", "/api/agent-operations/call", envelope)
        if self.csrf is None:
            self.bootstrap()
        return self.request(value["method"], value["path"], value["body"])

    def request(self, method, path, body=None):
        """Execute one internal fixed route with exact origin, cookie and CSRF boundaries."""
        payload = encode_body(body)
        headers = {"Accept": "application/json", "Origin": self.origin}
        if self.grant_token is not None:
            from .agent_review_protocol import PATHS

            if method != "POST" or path not in ("/api/agent-operations/call", *PATHS.values()):
                raise Invalid("Grant credentials may address only fixed scoped operation gateways")
            headers["Authorization"] = "Bearer " + self.grant_token
        if payload is not None:
            headers.update({"Content-Type": "application/json", "X-CSRF-Token": self.csrf or ""})
        # origin_data restricts the destination to literal IPv4 loopback HTTP.
        request = Request(self.origin + path, data=payload, headers=headers, method=method)  # noqa: S310
        try:
            with self.opener.open(request, timeout=request_timeout(path, body)) as response:
                return response_data(response)
        except HTTPError as error:
            reject_http(error, path, body)
        except (URLError, TimeoutError, OSError, HTTPException) as error:
            raise ClientError(
                "TRANSPORT_UNAVAILABLE",
                "The local WMM operation did not return a confirmed result. Inspect saved history before retrying a write.",
            ) from error

    def review(self, action, body):
        """Reviewed requests require a grant and never bootstrap a browser session."""
        from .agent_review_protocol import validate

        if self.grant_token is None:
            raise Invalid("Agent review actions require --use-grant")
        path = validate(action, body)
        encode_body(body)
        return self.request("POST", path, body)


def encode_body(value):
    """Validate finite bounded payloads before any network activity."""
    if value is None:
        return None
    try:
        raw = canonical(value).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as error:
        raise Invalid("Operation input must be finite serializable JSON") from error
    if len(raw) > MAX_BYTES:
        raise Invalid("Operation input exceeds 16777216 bytes")
    return raw


def grant_environment(enabled):
    """Read an explicitly enabled host-supplied credential without command arguments."""
    if not enabled:
        return None
    import os

    value = os.environ.get("WMM_AGENT_GRANT")
    if not value or not re.fullmatch(r"wmmg_[A-Za-z0-9_-]{43}", value):
        raise Invalid("--use-grant requires WMM_AGENT_GRANT in the process environment")
    return value
