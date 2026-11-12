"""Finite local browser sign-in for isolated assigned-client read dashboards."""

import hashlib
import hmac
from http.server import ThreadingHTTPServer
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qsl, urlsplit

from .common import Invalid, canonical
from .hosted_read_control import Unauthenticated
from .hosted_read_http import ReadHandler, ROUTE, failure
from .http_body import read_exact

STATIC = Path(__file__).parent / "static"
ASSETS = {
    "/": ("client-dashboard.html", "text/html; charset=utf-8"),
    "/static/client-dashboard.js": ("client-dashboard.js", "text/javascript; charset=utf-8"),
    "/static/client-dashboard.css": ("client-dashboard.css", "text/css; charset=utf-8"),
}
CSP = "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; form-action 'self' https:; base-uri 'none'; frame-ancestors 'none'"
_OPAQUE = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def cookies(headers):
    """Accept unambiguous host-only browser/session cookies, never a bearer."""
    values = headers.get_all("Cookie", [])
    if len(values) > 1:
        raise Invalid("Ambiguous cookies")
    result = {}
    for field in values[0].split(";") if values else ():
        name, sep, value = field.strip().partition("=")
        if not sep or name in result or not name or len(value) > 128:
            raise Invalid("Invalid cookies")
        result[name] = value
    validate_cookies(result)
    return result


def validate_cookies(result):
    for name in ("wmm_browser", "wmm_read"):
        value = result.get(name, "")
        check = value[5:] if name == "wmm_read" and value.startswith("wmmr_") else value
        if value and not _OPAQUE.fullmatch(check):
            raise Invalid("Invalid cookies")


def fields(raw, expected):
    """Exact form grammar; preserve duplicates until checked."""
    if len(raw) > 4096 or re.search(r"%(?![a-fA-F0-9]{2})", raw):
        raise Invalid("Invalid form")
    pairs = parse_qsl(
        raw, keep_blank_values=True, strict_parsing=True, encoding="utf-8", errors="strict", max_num_fields=4
    )
    values = dict(pairs)
    if len(values) != len(pairs) or set(values) != expected:
        raise Invalid("Invalid form")
    if any(not value or len(value) > 2048 or not value.isprintable() for value in values.values()):
        raise Invalid("Invalid form")
    return pairs


class BrowserServer(ThreadingHTTPServer):
    """Trusted startup configuration only. This increment is local HTTP only."""

    daemon_threads = True

    def __init__(self, address, control, registry, login=None):
        if address[0] != "127.0.0.1":
            raise Invalid("Browser dashboard may bind only to 127.0.0.1")
        self.control, self.registry, self.login = control, registry, login
        self.csrf_key = secrets.token_bytes(32)
        self.browser_sessions = {}
        super().__init__(address, BrowserHandler)

    def csrf(self, token):
        return hmac.new(self.csrf_key, token.encode("ascii"), hashlib.sha256).hexdigest()

    def choices(self, token):
        admissions, more = self.control.choices(token)
        clients, entries = [], []
        for admission in admissions:
            entry = self.registry.resolve(admission.tenant_id, admission.client_id)
            apps, app_more = self.registry.apps(entry)
            entries.append(entry)
            clients.append(
                dict(
                    tenant_id=admission.tenant_id,
                    client_id=admission.client_id,
                    role=admission.role,
                    apps=apps,
                    more_available=app_more,
                )
            )
        for entry in entries:
            self.registry.check(entry)
        self.control.finish_choices(token, admissions, more)
        return dict(clients=clients, more_available=more, csrf=self.csrf(token))


class BrowserHandler(ReadHandler):
    """No desktop dispatcher, credentials API, workers or mutation endpoints."""

    @property
    def origin(self):
        return "http://127.0.0.1:" + str(self.server.server_port)

    def output(self, code, raw=b"", content_type="application/json; charset=utf-8", headers=()):
        self.close_connection = True
        if self.request_version == "HTTP/0.9":
            self.request_version = "HTTP/1.0"
        self.send_response(code)
        policy = "same-origin" if code == 200 and content_type.startswith("text/html") else "no-referrer"
        standard = (
            ("Content-Type", content_type),
            ("Content-Length", str(len(raw))),
            ("Cache-Control", "no-store"),
            ("Referrer-Policy", policy),
            ("X-Content-Type-Options", "nosniff"),
            ("Content-Security-Policy", CSP),
            ("Connection", "close"),
        )
        for name, value in (*standard, *headers):
            self.send_header(name, value)
        self.end_headers()
        try:
            if self.command != "HEAD":
                self.wfile.write(raw)
        except (BrokenPipeError, ConnectionError):
            pass

    def send(self, code, body, receipt=None, headers=()):
        if receipt:
            headers = (*headers, ("X-WMM-Receipt", receipt))
        self.output(code, canonical(body).encode("utf-8"), headers=headers)

    def cookie(self, name, value, age):
        return ("Set-Cookie", f"{name}={value}; Path=/; Max-Age={age}; HttpOnly; SameSite=Lax")

    def boundary_headers(self, post=False):
        if len(self.headers) > 32 or sum(len(k) + len(v) + 4 for k, v in self.headers.items()) > 8192:
            raise Invalid("Invalid headers")
        for name in ("Host", "Origin", "Authorization", "Cookie", "Content-Length", "Content-Type"):
            if len(self.headers.get_all(name, [])) > 1:
                raise Invalid("Ambiguous headers")
        self.identity_headers()
        if self.request_version not in ("HTTP/1.0", "HTTP/1.1") or self.headers.get("Host") != self.origin[7:]:
            raise Invalid("Use the exact browser dashboard origin")
        origin = self.headers.get("Origin", "" if post else self.origin)
        if origin != self.origin:
            raise Invalid("Cross-origin request rejected")

    def identity_headers(self):
        forbidden = {
            "authorization",
            "forwarded",
            "transfer-encoding",
            "x-user",
            "x-tenant",
            "x-subject",
            "x-verified",
            "cf-access-jwt-assertion",
        }
        if any(k.lower() in forbidden or k.lower().startswith("x-forwarded-") for k in self.headers):
            raise Invalid("Unsupported headers")

    def request_context(self, post=False):
        self.boundary_headers(post)
        if "#" in self.path or not re.fullmatch(r"0|[1-9][0-9]{0,3}", self.headers.get("Content-Length", "0")):
            raise Invalid("Invalid route or framing")
        if not post and self.headers.get("Content-Length", "0") != "0":
            raise Invalid("Unexpected request body")
        if len(self.path) > (4096 if self.path.startswith("/auth/callback?") else 512):
            raise Invalid("Invalid route")
        return cookies(self.headers)

    def error_response(self, error):
        code, _ = failure(error)
        if isinstance(error, (Invalid, ValueError, UnicodeError)):
            code = 400
        messages = {
            400: "Unsupported dashboard request",
            401: "Sign in to your assigned workspace",
            404: "Ask your workspace owner to confirm your access",
        }
        self.send(
            code, {"error": messages.get(code, "Dashboard unavailable. Try again or contact your workspace owner.")}
        )

    def context(self, jar):
        login = self.server.login
        if login is None:
            return self.send(200, dict(configured=False, csrf="", label="Sign in"))
        browser = jar.get("wmm_browser", "")
        try:
            csrf = login.context_for(browser)
        except Exception:
            browser, csrf = login.context()
        self.send(
            200,
            dict(configured=True, csrf=csrf, label=login.provider.config.display_label),
            headers=(self.cookie("wmm_browser", browser, 600),),
        )

    def callback(self, jar):
        query = urlsplit(self.path).query
        expected = {"error", "state"} if any(k == "error" for k, _ in parse_qsl(query)) else {"code", "state"}
        params = fields(query, expected)
        browser = jar.get("wmm_browser", "")
        login = self.server.login
        if login is None:
            raise Unauthenticated("Sign in is not configured")
        identity, generation = login.callback(browser, self.origin, self.origin + "/auth/callback", params)
        login.commit_if_current(browser, generation, lambda: self.commit_login(identity, jar, browser))

    def commit_login(self, identity, jar, browser):
        token = self.complete_login(identity, jar)
        try:
            previous = self.server.browser_sessions.pop(browser, None)
            if previous:
                self.server.control.revoke_session(previous)
            if len(self.server.browser_sessions) >= 256:
                _, evicted = self.server.browser_sessions.popitem()
                self.server.control.revoke_session(evicted)
            self.server.browser_sessions[browser] = token
            self.output(303, headers=(("Location", "/"), self.cookie("wmm_read", token, 28800)))
        except Exception:
            self.server.control.revoke_session(token)
            raise

    def complete_login(self, identity, jar):
        token = self.server.control.issue_verified_session(identity)
        try:
            if jar.get("wmm_read"):
                self.server.control.revoke_session(jar["wmm_read"])
        except Exception:
            self.server.control.revoke_session(token)
            raise
        return token

    def dashboard(self, jar):
        match = ROUTE.fullmatch(self.path)
        if not match:
            raise Invalid("Unknown dashboard route")
        token, correlation = jar.get("wmm_read", ""), secrets.token_hex(16)
        tenant, client, app = match.groups()
        try:
            data, receipt = self.collect(token, tenant, client, app, correlation)
        except Exception as error:
            return self.denied(error, token, tenant, client, app, correlation)
        self.send(200, data, receipt)

    def do_GET(self):
        try:
            jar = self.request_context()
            self.get_route(jar)
        except Exception as error:
            if self.path.startswith("/auth/callback?"):
                return self.output(303, headers=(("Location", "/?signin=failed"),))
            self.error_response(error)

    def get_route(self, jar):
        path = "/" if self.path == "/?signin=failed" else self.path
        if path in ASSETS:
            name, content_type = ASSETS[path]
            return self.output(200, (STATIC / name).read_bytes(), content_type)
        if self.path == "/auth/context":
            return self.context(jar)
        if self.path == "/api/session":
            return self.send(200, self.server.choices(jar.get("wmm_read", "")))
        if self.path.startswith("/auth/callback?"):
            return self.callback(jar)
        return self.dashboard(jar)

    def form(self):
        if self.headers.get("Content-Type", "") != "application/x-www-form-urlencoded":
            raise Invalid("Use the sign-in form")
        value = read_exact(self, 4096, "sign-in")
        return dict(fields(value.decode("utf-8"), {"csrf"}))

    def logout(self, jar, csrf):
        token = jar.get("wmm_read", "")
        if not token or not hmac.compare_digest(csrf, self.server.csrf(token)):
            raise Unauthenticated("Sign in again before changing this session")

        def revoke():
            current = self.server.browser_sessions.pop(jar.get("wmm_browser", ""), None)
            if current:
                self.server.control.revoke_session(current)
            self.server.control.revoke_session(token)

        if self.server.login:
            self.server.login.invalidate(jar.get("wmm_browser", ""), revoke)
        else:
            revoke()
        self.send(
            200, {"signed_out": True}, headers=(self.cookie("wmm_read", "", 0), self.cookie("wmm_browser", "", 0))
        )

    def do_POST(self):
        try:
            jar = self.request_context(post=True)
            if self.path not in ("/auth/start", "/auth/logout"):
                raise Invalid("Unsupported dashboard action")
            csrf = self.form()["csrf"]
            if self.path == "/auth/logout":
                return self.logout(jar, csrf)
            if self.server.login is None:
                raise Unauthenticated("Sign in is not configured")
            location = self.server.login.start(
                jar.get("wmm_browser", ""), csrf, self.origin, self.origin + "/auth/callback"
            )
            self.output(303, headers=(("Location", location),))
        except Exception as error:
            self.error_response(error)

    do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = ReadHandler.unsupported
