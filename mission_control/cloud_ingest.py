"""Minimal BYOC ingest SDK: HTTPS token health/ingest, fail closed, no fallback."""
from __future__ import annotations

import json
import re
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

SCHEMA = "wmm.cloud.v1"
KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}")


class IngestError(RuntimeError):
    """Safe transport/provider failure without reflecting tokens or payloads."""


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise IngestError("Cloud redirects are not accepted")


def _endpoint(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError("Use an HTTPS cloud endpoint")
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Use a plain HTTPS base URL without credentials or query")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname == "127.0.0.1"):
        raise ValueError("Use HTTPS; plain HTTP is allowed only on 127.0.0.1 for tests")
    if not parsed.hostname or parsed.path not in ("", "/"):
        raise ValueError("Use a base URL without a path")
    return value.rstrip("/")


class CloudIngest:
    def __init__(self, endpoint, token, *, timeout=10, opener=None):
        self.endpoint = _endpoint(endpoint)
        if not isinstance(token, str) or not 8 <= len(token) <= 4096 or "\n" in token or "\r" in token:
            raise ValueError("Use a valid cloud token")
        self._token = token
        self.timeout = timeout
        self._opener = opener or build_opener(_RejectRedirects())

    def _request(self, method, path, body=None, idempotency_key=None):
        headers = {"Authorization": "Bearer " + self._token, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or not KEY.fullmatch(idempotency_key):
                raise ValueError("Use an 8-128 character idempotency key")
            headers["Idempotency-Key"] = idempotency_key
        request = Request(self.endpoint + path, data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                if response.status not in (200, 201):
                    raise IngestError("Cloud returned HTTP " + str(response.status))
                value = json.loads(response.read().decode("utf-8"))
        except IngestError:
            raise
        except Exception as exc:
            raise IngestError("Cloud request failed: " + type(exc).__name__) from None
        if not isinstance(value, dict):
            raise IngestError("Cloud returned a non-object response")
        return value

    def health(self):
        """Test token and contract without sending evidence."""
        value = self._request("GET", "/v1/health")
        if value.get("schema") != SCHEMA or value.get("status") != "READY":
            raise IngestError("Cloud health does not match the WMM v1 contract")
        return {key: value.get(key) for key in ("schema", "status", "tenant", "version")}

    def send_batch(self, batch, idempotency_key):
        """Send one already-validated batch; no retry and no local fallback."""
        if not isinstance(batch, dict) or not batch:
            raise ValueError("Use one validated install batch")
        value = self._request("POST", "/v1/install-batches",
                              {"batch": batch}, idempotency_key=idempotency_key)
        if value.get("schema") != SCHEMA or value.get("status") not in ("ACCEPTED", "DUPLICATE"):
            raise IngestError("Cloud did not accept the install batch")
        receipt = value.get("receipt")
        if not isinstance(receipt, str) or not receipt:
            raise IngestError("Cloud acceptance requires a receipt")
        return {"status": value["status"], "receipt": receipt, "tenant": value.get("tenant")}
