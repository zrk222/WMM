"""Exercise the launcher protocol against the real isolated loopback child."""

import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from queue import Queue
from threading import Thread
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from mission_control.desktop import DesktopRuntime

NONCE = b"42" * 32
CHALLENGE = "35" * 32
COMMAND = [sys.executable, "-B", "-m", "mission_control.desktop", "--native-sidecar"]


class DesktopSidecarTests(unittest.TestCase):
    def start_child(self, directory):
        env = {**os.environ, "LOCALAPPDATA": directory, "XDG_DATA_HOME": directory, "HOME": directory}
        return subprocess.Popen(COMMAND, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_pipe_proof_then_activation_and_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            for activate in (False, True):
                with self.subTest(activate=activate), self.start_child(folder) as child:
                    try:
                        stdin, stdout = child.stdin, child.stdout
                        assert stdin is not None and stdout is not None
                        stdin.write(NONCE + b"\n")
                        stdin.flush()
                        ready = Queue(maxsize=1)
                        reader = Thread(
                            target=lambda queue=ready, pipe=stdout: queue.put(pipe.readline(512)),
                            daemon=True,
                        )
                        reader.start()
                        line = ready.get(timeout=15)
                        self.assertTrue(line.endswith(b"\n"), line)
                        frame = json.loads(line)
                        self.assertEqual(set(frame), {"protocol", "pid", "port", "sha256", "packaged"})
                        self.assertEqual(frame["protocol"], "wmm.desktop-sidecar.v1")
                        self.assertEqual(frame["pid"], child.pid)
                        self.assertFalse(frame["packaged"])
                        self.assertRegex(frame["sha256"], r"^[a-f0-9]{64}$")
                        self.assertNotIn(NONCE, line)
                        origin = f"http://127.0.0.1:{frame['port']}"
                        client = build_opener(ProxyHandler({}))
                        route = origin + "/api/desktop-proof"
                        headers = {"X-WMM-Desktop-Challenge": CHALLENGE}
                        expected = hmac.new(
                            bytes.fromhex(NONCE.decode()), line + bytes.fromhex(CHALLENGE), hashlib.sha256
                        ).hexdigest()
                        with client.open(Request(route, headers=headers), timeout=5) as response:
                            self.assertEqual(json.load(response), {"proof": expected})
                            self.assertNotIn("Set-Cookie", response.headers)
                            self.assertEqual(response.headers["Cache-Control"], "no-store")
                        for address, request_headers, status in (
                            (route, {}, 400),
                            (route, {**headers, "Host": "localhost"}, 403),
                            (route, {**headers, "Origin": origin}, 403),
                            (route + "?extra=1", headers, 404),
                        ):
                            with self.assertRaises(HTTPError) as error:
                                client.open(Request(address, headers=request_headers), timeout=5)
                            self.assertEqual(error.exception.code, status)
                            error.exception.close()
                        telemetry = origin + "/api/apps/sample-one/workflow-telemetry"

                        def last_poll(client=client, telemetry=telemetry):
                            with client.open(telemetry, timeout=5) as response:
                                return json.load(response)["worker"]["last_success"]

                        self.assertIsNone(last_poll())
                        if activate:
                            stdin.write(b"START\n")
                            stdin.flush()
                            for _ in range(50):
                                try:
                                    with client.open(Request(route, headers=headers), timeout=2):
                                        time.sleep(0.05)
                                except HTTPError as error:
                                    self.assertEqual(error.code, 404)
                                    error.close()
                                    break
                            else:
                                self.fail("Proof remained available after activation")
                            for _ in range(50):
                                if last_poll() is not None:
                                    break
                                time.sleep(0.05)
                            else:
                                self.fail("The existing worker never reported a successful poll")
                        stdin.close()
                        self.assertEqual(child.wait(timeout=15), 0)
                        self.assertEqual(stdout.read(), b"")
                    finally:
                        if child.poll() is None:
                            child.kill()

    def test_sidecar_uses_the_relay_port_or_a_working_private_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            for occupied in (True, False):
                with self.subTest(occupied=occupied), socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
                    if occupied:
                        blocker.bind(("127.0.0.1", 8765))
                        blocker.listen(1)
                    with self.start_child(folder) as child:
                        frame_line, stderr = child.communicate(NONCE + b"\n", timeout=15)
                    self.assertEqual(child.returncode, 0, stderr)
                    frame = json.loads(frame_line)
                    self.assertEqual(frame["pid"], child.pid)
                    if occupied:
                        self.assertNotEqual(frame["port"], 8765)
                    else:
                        self.assertEqual(frame["port"], 8765)

    def test_malformed_pipe_frame_creates_no_workspace(self):
        with tempfile.TemporaryDirectory() as folder, self.start_child(folder) as child:
            stdout, stderr = child.communicate(b"42" * 512 + b"\n", timeout=15)
            self.assertNotEqual(child.returncode, 0)
            self.assertEqual(stdout, b"")
            self.assertIn(b"valid private startup frame", stderr)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_ordinary_runtime_has_no_proof_route(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = DesktopRuntime(folder, 0)
            try:
                origin = runtime.start(workers=False)
                client = build_opener(ProxyHandler({}))
                with self.assertRaises(HTTPError) as error:
                    client.open(origin + "/api/desktop-proof", timeout=5)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
            finally:
                runtime.close()
