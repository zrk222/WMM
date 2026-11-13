"""Bounded local adapter comparison; never selects a production server."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import http.cookiejar
import io
import json
import math
import os
import platform
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mission_control.server import Server  # noqa: E402
from mission_control.store import Store  # noqa: E402


class PoolServer(Server):
    """Four workers plus four admitted queued sockets, with accept backpressure."""

    def __init__(self, address: tuple[str, int], store: Store) -> None:
        self.pool = ThreadPoolExecutor(max_workers=4)
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, store)

    def process_request(
        self, request: socket.socket | tuple[bytes, socket.socket], client_address: tuple[str, int]
    ) -> None:
        self.slots.acquire()
        try:
            self.pool.submit(self.run_request, request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def run_request(self, request: socket.socket | tuple[bytes, socket.socket], address: tuple[str, int]) -> None:
        try:
            self.process_request_thread(request, address)
        finally:
            self.slots.release()

    def server_close(self) -> None:
        super().server_close()
        self.pool.shutdown(wait=True, cancel_futures=True)


def memory() -> dict[str, Any]:
    """Measure this child process, preserving resident versus peak semantics."""
    if sys.platform == "win32":
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t)
                for name in (
                    "peak",
                    "working",
                    "paged_peak",
                    "paged",
                    "nonpaged_peak",
                    "nonpaged",
                    "pagefile",
                    "pagefile_peak",
                )
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo")
        return {
            "resident_bytes": counters.working,
            "peak_resident_bytes": counters.peak,
            "method": "GetProcessMemoryInfo.WorkingSetSize",
        }
    if sys.platform.startswith("linux"):
        pages = int(Path("/proc/self/statm").read_text().split()[1])
        return {"resident_bytes": pages * os.sysconf("SC_PAGE_SIZE"), "method": "/proc/self/statm resident pages"}
    raise RuntimeError("Resident memory measurement supports Windows and Linux only")


def child(adapter: str) -> None:
    """Serve synthetic state until parent closes stdin; parent enforces lifetime."""
    with tempfile.TemporaryDirectory(prefix="wmm-http-benchmark-") as directory:
        factory = Server if adapter == "baseline" else PoolServer
        server = factory(("127.0.0.1", 0), Store(Path(directory) / "state.sqlite"))
        identity = {"principal": "github:12345", "login": "synthetic", "provider": "GITHUB", "verified_at": "synthetic"}
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        try:
            with patch("mission_control.operator_identity.github_read", return_value=identity):
                thread.start()
                print(json.dumps({"port": server.server_port}), flush=True)
                sys.stdin.readline()
                print(json.dumps(memory()), flush=True)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def summarize(samples: list[float]) -> dict[str, Any]:
    """Use nearest-rank percentiles and reject malformed/nonfinite samples."""
    if not samples or any(
        type(value) not in (int, float) or not math.isfinite(value) or value <= 0 for value in samples
    ):
        raise ValueError("Expected finite positive latency samples")
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "p50_ms": ordered[math.ceil(len(samples) * 0.50) - 1],
        "p95_ms": ordered[math.ceil(len(samples) * 0.95) - 1],
        "samples_ms": samples,
    }


def parity(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> None:
    """Identical failures are insufficient: both must pass fixed expectations."""
    if not left or left != right or any(row["actual"] != row["expected"] for row in left):
        raise ValueError("Adapter route/auth/CSRF parity failed")


def measure(adapter: str, count: int, warmup: int) -> dict[str, Any]:
    """Run one isolated subprocess with bounded readiness and teardown."""
    process = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--child", adapter],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    ready: list[str] = []
    assert process.stdout is not None
    stdout_pipe = process.stdout
    reader = threading.Thread(target=lambda: ready.append(stdout_pipe.readline()), daemon=True)
    reader.start()
    try:
        reader.join(timeout=30)
        if reader.is_alive() or not ready or not ready[0]:
            raise RuntimeError("Server readiness timed out or child exited")
        base = f"http://127.0.0.1:{json.loads(ready[0])['port']}"
        client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        csrf = ""

        def request(
            path: str, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None
        ) -> tuple[int, Any]:
            request_headers = {
                "Origin": base,
                "X-CSRF-Token": csrf,
                "Content-Type": "application/json",
                **(headers or {}),
            }
            req = Request(  # noqa: S310 - base is a child-owned ephemeral loopback HTTP port
                base + path, data=json.dumps(body).encode() if body is not None else None, headers=request_headers
            )
            try:
                response = client.open(req, timeout=5)
            except HTTPError as error:
                response = error
            with response:
                raw = response.read()
                value = (
                    json.loads(raw) if response.headers.get("Content-Type", "").startswith("application/json") else raw
                )
                return int(response.code), value

        cold_start = time.perf_counter_ns()
        status, bootstrap = request("/api/bootstrap")
        cold_ms = (time.perf_counter_ns() - cold_start) / 1e6
        if status != 200 or bootstrap["identity"] != {"status": "SIGNED_OUT"}:
            raise ValueError("Invalid bootstrap")
        csrf = bootstrap["csrf"]
        probes: list[dict[str, Any]] = []

        def probe(name: str, actual: Any, expected: Any) -> None:
            probes.append({"name": name, "actual": actual, "expected": expected})

        probe("signed-out", bootstrap["identity"], {"status": "SIGNED_OUT"})
        probe("protected-unauthorized", request("/api/apps/synthetic/access/unknown", {})[0], 403)
        probe("missing-route", request("/api/not-a-route")[0], 404)
        probe("host-boundary", request("/api/bootstrap", headers={"Host": "evil.test"})[0], 403)
        probe("csrf-rejected", request("/api/identity/logout", {}, {"X-CSRF-Token": "wrong"})[0], 403)
        probe("origin-rejected", request("/api/identity/logout", {}, {"Origin": "https://evil.test"})[0], 403)
        probe("invalid-login", request("/api/identity/login", {"token": "invalid"})[0], 400)
        status, login = request("/api/identity/login", {"token": "synthetic_benchmark_token_000"})
        probe(
            "authorized-login",
            [status, login.get("status"), login.get("principal")],
            [200, "AUTHENTICATED", "github:12345"],
        )
        probe("protected-authenticated-dispatch", request("/api/apps/synthetic/access/unknown", {})[0], 404)
        _, current = request("/api/bootstrap")
        probe("session-principal", current["identity"].get("principal"), "github:12345")
        probe("authorized-logout", request("/api/identity/logout", {}), (200, {"status": "SIGNED_OUT"}))
        _, current = request("/api/bootstrap")
        probe("logout-clears-principal", current["identity"], {"status": "SIGNED_OUT"})
        parity(probes, probes)
        for _ in range(warmup):
            if request("/api/bootstrap")[0] != 200:
                raise ValueError("Warmup failed")
        samples: list[float] = []
        for _ in range(count):
            start = time.perf_counter_ns()
            if request("/api/bootstrap")[0] != 200:
                raise ValueError("Measured request failed")
            samples.append((time.perf_counter_ns() - start) / 1e6)
        stdout, stderr = process.communicate("stop\n", timeout=15)
        if process.returncode != 0:
            raise RuntimeError(f"Child failed: {stderr[-1000:]}")
        return {
            "adapter": adapter,
            "cold_first_bootstrap_ms": cold_ms,
            "warmup_requests": warmup,
            "measurement": summarize(samples),
            "memory_after_requests": json.loads(stdout),
            "parity": probes,
        }
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)
        reader.join(timeout=5)


def suite_child(adapter: str) -> None:
    """Execute the unchanged real HTTP suite with only its server factory patched."""
    from tests import test_http

    output = io.StringIO()
    server_factory = Server if adapter == "baseline" else PoolServer
    with patch.object(test_http, "Server", server_factory), redirect_stdout(output), redirect_stderr(output):
        suite = unittest.defaultTestLoader.loadTestsFromModule(test_http)
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    print(
        json.dumps(
            {
                "adapter": adapter,
                "tests_run": result.testsRun,
                "successful": result.wasSuccessful(),
                "failures": len(result.failures),
                "errors": len(result.errors),
                "skipped": len(result.skipped),
                "log": output.getvalue(),
            }
        )
    )


def full_suites() -> list[dict[str, Any]]:
    """Keep each full-suite process isolated; retain failure evidence and fail closed."""
    evidence = ROOT / ".factory/mechanics08"
    evidence.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for adapter in ("baseline", "bounded_pool"):
        process = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--suite-child", adapter],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,
        )
        (evidence / f"{adapter}-suite.stdout.log").write_text(process.stdout, encoding="utf-8")
        (evidence / f"{adapter}-suite.stderr.log").write_text(process.stderr, encoding="utf-8")
        if process.returncode != 0:
            raise RuntimeError(f"{adapter} HTTP suite child failed; see retained logs")
        result = json.loads(process.stdout)
        results.append(result)
        (evidence / "full-suite-results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    if any(not result["successful"] or result["tests_run"] <= 0 or result["skipped"] for result in results):
        raise ValueError("Full HTTP suite parity failed; see full-suite-results.json")
    if results[0]["tests_run"] != results[1]["tests_run"]:
        raise ValueError("Full HTTP suite counts differ")
    return results


def benchmark(count: int = 100, warmup: int = 5, *, full_parity: bool = False) -> dict[str, Any]:
    """Return raw measurements and hash-bound scope without production mutation."""
    if not 1 <= count <= 10000 or not 0 <= warmup <= 100:
        raise ValueError("Request/warmup count outside bounded range")
    suites = full_suites() if full_parity else []
    results = [measure(adapter, count, warmup) for adapter in ("baseline", "bounded_pool")]
    parity(results[0]["parity"], results[1]["parity"])
    critical = [
        "tools/benchmark_http.py",
        "tests/test_http_benchmark.py",
        "tests/test_http.py",
        "mission_control/server.py",
        "mission_control/operator_identity.py",
        "mission_control/http_body.py",
    ]
    return {
        "schema": "wmm.http-comparison.v1",
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in critical},
        "environment": {"python": sys.version, "platform": platform.platform()},
        "parity_pass": True,
        "full_http_suite": suites,
        "scope": "Sequential loopback bootstrap requests; same Handler/Server; synthetic identity provider; bounded probes plus optional unchanged full tests.test_http suite; not a framework comparison",
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", choices=("baseline", "bounded_pool"))
    parser.add_argument("--suite-child", choices=("baseline", "bounded_pool"))
    parser.add_argument("--full-parity", action="store_true")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--out", type=Path, default=ROOT / ".factory/mechanics08/benchmark.json")
    args = parser.parse_args()
    if args.suite_child:
        suite_child(args.suite_child)
        return
    if args.child:
        child(args.child)
        return
    receipt = benchmark(args.requests, args.warmup, full_parity=args.full_parity)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
