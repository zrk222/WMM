"""BYOC ingest SDK is HTTPS/token-bound and has no silent local fallback."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import unittest

from mission_control.cloud_ingest import CloudIngest, IngestError

TOKEN = "owner-cloud-token-123"


class Handler(BaseHTTPRequestHandler):
    calls = []

    def log_message(self, *args):
        return

    def _send(self, status, value):
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        type(self).calls.append(("GET", self.path, self.headers.get("Authorization"), None))
        if self.path == "/v1/health":
            return self._send(200, {"schema": "wmm.cloud.v1", "status": "READY", "tenant": "own", "version": "1"})
        return self._send(404, {"error": "missing"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        type(self).calls.append(("POST", self.path, self.headers.get("Authorization"),
                                (self.headers.get("Idempotency-Key"), body)))
        if self.path == "/v1/install-batches":
            return self._send(201, {"schema": "wmm.cloud.v1", "status": "ACCEPTED", "receipt": "receipt-1", "tenant": "own"})
        return self._send(404, {"error": "missing"})


class Redirect(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def do_GET(self):
        self.send_response(302)
        self.send_header("Location", "http://example.test/v1/health")
        self.end_headers()


class CloudIngestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Handler.calls.clear()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_sends_token_but_no_evidence(self):
        value = CloudIngest(self.base, TOKEN).health()
        self.assertEqual(value["status"], "READY")
        method, path, auth, body = Handler.calls[-1]
        self.assertEqual((method, path, auth, body), ("GET", "/v1/health", "Bearer " + TOKEN, None))

    def test_batch_has_idempotency_and_receipt(self):
        batch = {"source": "APPSFLYER", "installs": []}
        value = CloudIngest(self.base, TOKEN).send_batch(batch, "request-0001")
        self.assertEqual(value["status"], "ACCEPTED")
        method, path, auth, body = Handler.calls[-1]
        self.assertEqual(method, "POST")
        self.assertEqual(body[0], "request-0001")
        self.assertEqual(body[1], {"batch": batch})

    def test_plain_http_remote_and_redirects_reject(self):
        for endpoint in ("http://example.test", "https://user:pass@example.test", "https://example.test/path"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                CloudIngest(endpoint, TOKEN)
        redirect = ThreadingHTTPServer(("127.0.0.1", 0), Redirect)
        thread = Thread(target=redirect.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(IngestError):
                CloudIngest("http://127.0.0.1:" + str(redirect.server_port), TOKEN).health()
        finally:
            redirect.shutdown()
            redirect.server_close()

    def test_invalid_endpoint_and_key_never_become_a_local_fallback(self):
        with self.assertRaises(ValueError):
            CloudIngest(self.base + "/nope", TOKEN)
        with self.assertRaises(ValueError):
            CloudIngest(self.base, TOKEN).send_batch({"source": "MMP"}, "short")
