"""Reference relay implements the v1 contract with bearer auth and idempotency."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "relay-test-token-0123456789"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class CloudRelayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.port = free_port()
        env = dict(os.environ, WMM_CLOUD_TOKEN=TOKEN, WMM_CLOUD_DB=str(Path(cls.folder.name) / "relay.sqlite3"),
                   WMM_CLOUD_HOST="127.0.0.1", WMM_CLOUD_PORT=str(cls.port))
        cls.process = subprocess.Popen([sys.executable, str(ROOT / "cloud" / "relay.py")], env=env,
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                cls.call("GET", "/v1/health")
                break
            except Exception:
                time.sleep(0.1)
        else:
            cls.process.kill()
            raise RuntimeError("relay did not start")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=10)
        cls.folder.cleanup()

    @classmethod
    def call(cls, method, path, body=None, token=TOKEN, key=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        request = Request(f"http://127.0.0.1:{cls.port}" + path, data=data, headers=headers, method=method)
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_health_requires_token_and_sends_no_evidence(self):
        with self.assertRaises(HTTPError) as error:
            self.call("GET", "/v1/health", token="wrong-token-000000")
        self.assertEqual(error.exception.code, 401)
        status, value = self.call("GET", "/v1/health")
        self.assertEqual((status, value["schema"], value["status"]), (200, "wmm.cloud.v1", "READY"))

    def test_batch_idempotency_and_content_conflict(self):
        batch = {"batch": {"source": "MMP", "installs": []}}
        status, first = self.call("POST", "/v1/install-batches", batch, key="request-0001")
        self.assertEqual((status, first["status"]), (201, "ACCEPTED"))
        status, second = self.call("POST", "/v1/install-batches", batch, key="request-0001")
        self.assertEqual((status, second["status"], second["receipt"]), (200, "DUPLICATE", first["receipt"]))
        with self.assertRaises(HTTPError) as error:
            self.call("POST", "/v1/install-batches", {"batch": {"source": "OTHER"}}, key="request-0001")
        self.assertEqual(error.exception.code, 409)


    def test_concurrent_retries_share_one_committed_receipt(self):
        def send(_):
            return self.call("POST", "/v1/install-batches", {"batch": {"source": "MMP"}},
                             key="concurrent-0001")

        with ThreadPoolExecutor(max_workers=6) as pool:
            replies = list(pool.map(send, range(12)))
        self.assertEqual([code for code, _ in replies].count(201), 1)
        self.assertEqual([code for code, _ in replies].count(200), 11)
        self.assertEqual(len({body["receipt"] for _, body in replies}), 1)
