"""Single-owner WMM cloud relay reference: HTTPS behind a proxy, bearer token, idempotent batches."""
from __future__ import annotations

from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCHEMA = "wmm.cloud.v1"
TENANT = "personal"
TOKEN = os.environ.get("WMM_CLOUD_TOKEN", "")
DATABASE = Path(os.environ.get("WMM_CLOUD_DB", "wmm-cloud.sqlite3"))
HOST = os.environ.get("WMM_CLOUD_HOST", "127.0.0.1")
PORT = int(os.environ.get("WMM_CLOUD_PORT", "8787"))
MAX_BODY = 2_000_000
KEY = re.compile(r"[A-Za-z0-9._:-]{8,128}")


def database():
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATABASE)
    db.execute("CREATE TABLE IF NOT EXISTS batches(idempotency_key TEXT PRIMARY KEY, receipt TEXT NOT NULL, "
               "body TEXT NOT NULL, hash TEXT NOT NULL, created TEXT NOT NULL)")
    return db


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _send(self, status, value):
        body = json.dumps(value, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        header = self.headers.get("Authorization") or ""
        if not header.startswith("Bearer ") or not TOKEN:
            return False
        return hmac.compare_digest(header[7:], TOKEN)

    def do_GET(self):
        if self.path != "/v1/health":
            return self._send(404, {"error": "not found"})
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        return self._send(200, {"schema": SCHEMA, "status": "READY", "tenant": TENANT, "version": "1"})

    def do_POST(self):
        if self.path != "/v1/install-batches":
            return self._send(404, {"error": "not found"})
        if not self._authorized():
            return self._send(401, {"error": "unauthorized"})
        key = self.headers.get("Idempotency-Key") or ""
        if not KEY.fullmatch(key):
            return self._send(400, {"error": "invalid idempotency key"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._send(400, {"error": "invalid content length"})
        if length <= 0 or length > MAX_BODY:
            return self._send(413, {"error": "invalid body size"})
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError):
            return self._send(400, {"error": "invalid JSON"})
        if not isinstance(value, dict) or set(value) != {"batch"}:
            return self._send(400, {"error": "use the exact batch envelope"})
        batch = value["batch"]
        if not isinstance(batch, dict) or not batch:
            return self._send(400, {"error": "batch must be a non-empty object"})
        body = json.dumps(batch, sort_keys=True, separators=(",", ":"))
        value_hash = hashlib.sha256(body.encode()).hexdigest()
        receipt = "wmm-" + value_hash[:32]
        with closing(database()) as db, db:
            inserted = db.execute(
                "INSERT INTO batches VALUES(?,?,?,?,datetime('now')) "
                "ON CONFLICT(idempotency_key) DO NOTHING", (key, receipt, body, value_hash)
            ).rowcount == 1
            saved_hash, saved_receipt = db.execute(
                "SELECT hash,receipt FROM batches WHERE idempotency_key=?", (key,)
            ).fetchone()
        if saved_hash != value_hash:
            return self._send(409, {"error": "idempotency key reused with different content"})
        return self._send(201 if inserted else 200, {"schema": SCHEMA,
                          "status": "ACCEPTED" if inserted else "DUPLICATE",
                          "receipt": saved_receipt, "tenant": TENANT})


def main():
    if not TOKEN or len(TOKEN) < 16:
        raise SystemExit("Set WMM_CLOUD_TOKEN to a long random value before starting the relay.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"WMM cloud relay listening on {HOST}:{PORT}; terminate HTTPS only behind a trusted proxy", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
