"""Ephemeral browser-bound, one-use authorization flow."""
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from .hosted_oidc import OIDCError, dependencies_available, text_field

MAX_PENDING = 256
FLOW_SECONDS = 600
MAX_EXCHANGES = 4


def reject():
    raise OIDCError("Authentication unavailable or invalid")


def valid_binding(origin, redirect_uri):
    try:
        parts = urlsplit(origin)
        return (parts.scheme == "http" and parts.hostname == "127.0.0.1" and
                parts.port is not None and parts.netloc == "127.0.0.1:" + str(parts.port) and
                not parts.path and not parts.query and not parts.fragment and
                redirect_uri == origin + "/auth/callback")
    except (ValueError, TypeError):
        return False


def _callback_pair(pair, result):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        reject()
    key, value = pair
    if not isinstance(key, str) or key not in ("code", "state", "error") or key in result or not text_field(value, 4096):
        reject()
    result[key] = value


def callback_fields(params):
    if not isinstance(params, (list, tuple)) or len(params) != 2:
        reject()
    result = {}
    for pair in params:
        _callback_pair(pair, result)
    if set(result) not in ({"code", "state"}, {"error", "state"}):
        reject()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", result["state"]):
        reject()
    return result


class LoginFlow:
    def __init__(self, provider, clock=time.monotonic):
        self.provider, self.clock = provider, clock
        self.lock = threading.RLock()
        self.slots = threading.BoundedSemaphore(MAX_EXCHANGES)
        self.contexts = {}

    def _clean(self):
        now = self.clock()
        for browser in [k for k, v in self.contexts.items() if v["expires"] <= now]:
            del self.contexts[browser]

    def context(self):
        with self.lock:
            self._clean()
            if len(self.contexts) >= MAX_PENDING:
                reject()
            browser, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.contexts[browser] = {"csrf": csrf, "expires": self.clock() + FLOW_SECONDS,
                                      "generation": secrets.token_urlsafe(32), "flow": None, "committed": False}
            return browser, csrf

    def context_for(self, browser):
        with self.lock:
            self._clean()
            if browser not in self.contexts:
                reject()
            return self.contexts[browser]["csrf"]

    def start(self, browser, csrf, origin, redirect_uri):
        if not valid_binding(origin, redirect_uri) or not dependencies_available():
            reject()
        with self.lock:
            self._clean()
            item = self.contexts.get(browser)
            if not item or not isinstance(csrf, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", csrf) or not secrets.compare_digest(item["csrf"], csrf):
                reject()
            state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
            item.update(generation=secrets.token_urlsafe(32), expires=self.clock() + FLOW_SECONDS, committed=False,
                        flow=(state, nonce, verifier, origin, redirect_uri, self.provider.config))
            return self.provider.authorization(state, nonce, verifier, redirect_uri)

    def _consume(self, browser, origin, redirect_uri, fields):
        with self.lock:
            self._clean()
            item = self.contexts.get(browser)
            flow = item and item["flow"]
            if not flow or flow[3:5] != (origin, redirect_uri) or flow[5] != self.provider.config:
                reject()
            if not secrets.compare_digest(flow[0], fields["state"]):
                reject()
            item["flow"] = None
            return flow, item["generation"]

    def callback(self, browser, origin, redirect_uri, params):
        fields = callback_fields(params)
        flow, generation = self._consume(browser, origin, redirect_uri, fields)
        if "error" in fields or not self.slots.acquire(blocking=False):
            reject()
        try:
            identity = self.provider.exchange(fields["code"], flow[2], flow[1], redirect_uri)
            return identity, generation
        finally:
            self.slots.release()

    def commit_if_current(self, browser, generation, commit):
        with self.lock:
            self._clean()
            item = self.contexts.get(browser)
            if not item or item["generation"] != generation or item["flow"] is not None or item["committed"]:
                reject()
            item["committed"] = True
            return commit()

    def invalidate(self, browser, cleanup=None):
        with self.lock:
            self.contexts.pop(browser, None)
            if cleanup is not None:
                return cleanup()
