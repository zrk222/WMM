"""Opt-in disposable Ubuntu CI user-manager lifecycle test; never provision a host."""

import json
from http.cookiejar import CookieJar
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import HTTPRedirectHandler, HTTPCookieProcessor, ProxyHandler, Request, build_opener
from uuid import uuid4

BINARY = Path("/usr/lib/wize-marketing-machine/WMM")
UNIT = Path("/usr/share/wize-marketing-machine/wmm-worker.service")
ORIGIN = "http://127.0.0.1:8765"


def port_available():
    """Ignore closed TCP connections while refusing an active Linux listener."""
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", 8765))
        except OSError as exc:
            raise RuntimeError("Fixed WMM loopback port is occupied") from exc


def preflight(env):
    # All checks here are read-only: do not even create a temporary directory first.
    if (
        not sys.platform.startswith("linux")
        or env.get("CI") != "true"
        or env.get("GITHUB_ACTIONS") != "true"
        or env.get("WMM_HOST_SERVICE_CI") != "1"
        or env.get("WMM_ISOLATED_USER_MANAGER") != "1"
    ):
        raise RuntimeError("Requires explicitly isolated disposable Ubuntu CI user manager")
    import pwd

    uid = os.geteuid()
    user = pwd.getpwuid(uid)
    runtime = Path(env.get("XDG_RUNTIME_DIR", "/nonexistent"))
    home = Path(env.get("HOME", "/nonexistent"))
    temp = Path(env.get("RUNNER_TEMP", "/nonexistent"))
    if (
        uid == 0
        or not user.pw_name.startswith("wmm-ci-")
        or not home.is_absolute()
        or not temp.is_absolute()
        or not home.is_dir()
        or not temp.is_dir()
        or Path(user.pw_dir) != home
        or home.owner() != user.pw_name
        or not home.resolve().is_relative_to(temp.resolve())
        or runtime != Path("/run/user") / str(uid)
        or not runtime.is_dir()
        or runtime.stat().st_uid != uid
        or env.get("DBUS_SESSION_BUS_ADDRESS") != f"unix:path={runtime}/bus"
        or not (runtime / "bus").exists()
        or not BINARY.is_file()
        or not os.access(BINARY, os.X_OK)
        or not UNIT.is_file()
        or not os.access(UNIT, os.R_OK)
    ):
        raise RuntimeError("Disposable user, manager bus, temporary home or installed binary is invalid")
    # Do not interfere with any already-running listener on the fixed port.
    port_available()
    return runtime


def command(env, *args, check=True, timeout=75):
    return subprocess.run([str(x) for x in args], env=env, check=check, capture_output=True, text=True, timeout=timeout)


def systemctl(env, *args, check=True):
    return command(env, "systemctl", "--user", *args, check=check)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def session(origin=ORIGIN, timeout=45):
    """Create a fresh, proxy-free session restricted to the exact loopback origin."""
    if not re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}", origin):
        raise ValueError("Expected exact loopback origin with explicit port")
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()), NoRedirect())
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with client.open(origin + "/api/bootstrap", timeout=2) as response:
                bootstrap = json.load(response)
                if bootstrap.get("apps") and bootstrap.get("csrf"):
                    return client, bootstrap["csrf"]
        except (OSError, ValueError):
            pass
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    raise RuntimeError("Service did not serve bootstrap before timeout")


def request_json(client, origin, path, body=None, csrf=None):
    headers = {"Origin": origin}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.update({"Content-Type": "application/json", "X-CSRF-Token": csrf})
    with client.open(Request(origin + path, data=data, headers=headers), timeout=2) as response:
        return json.load(response)


def submit(client, origin, csrf, key):
    row = request_json(
        client,
        origin,
        "/api/apps/sample-one/jobs",
        {"action": "pipeline", "data": {"stage": 5}, "request_key": key},
        csrf,
    )
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"]
        or row.get("app_id") != "sample-one"
        or row.get("action") != "pipeline"
        or row.get("data") != {"stage": 5}
        or row.get("request_key") != key
    ):
        raise AssertionError("Queued job identity does not match the synthetic request")
    return row


def completed_job(client, origin, job_id, key, timeout=45):
    """Find exactly one request-key row and require a real successful result."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rows = request_json(client, origin, "/api/apps/sample-one/jobs")
        if not isinstance(rows, list):
            raise AssertionError("Job history is not a list")
        matches = [row for row in rows if isinstance(row, dict) and row.get("request_key") == key]
        if len(matches) != 1 or matches[0].get("id") != job_id:
            raise AssertionError("Job history does not contain exactly the requested identity")
        row = matches[0]
        if row.get("status") == "SUCCEEDED":
            result = row.get("result")
            if (
                row.get("app_id") != "sample-one"
                or row.get("action") != "pipeline"
                or row.get("data") != {"stage": 5}
                or type(row.get("attempts")) is not int
                or row["attempts"] != 1
                or not isinstance(result, dict)
                or result.get("external_execution") != "NOT_RUN"
                or type(result.get("spend_minor")) is not int
                or result["spend_minor"] != 0
                or not isinstance(result.get("outputs"), list)
                or len(result["outputs"]) != 1
                or not isinstance(result["outputs"][0], dict)
                or type(result["outputs"][0].get("stage")) is not int
                or result["outputs"][0]["stage"] != 5
                or result["outputs"][0].get("status") not in ("PREPARED", "BLOCKED")
                or not isinstance(result["outputs"][0].get("packet"), dict)
                or result["outputs"][0]["packet"].get("schema") != "growth.stage-packet.v1"
                or result["outputs"][0]["packet"].get("app_id") != "sample-one"
                or result["outputs"][0]["packet"].get("stage") != 5
                or result["outputs"][0]["packet"].get("external_execution") != "NOT_RUN"
            ):
                raise AssertionError("Completed job does not prove the requested local preparation")
            return row
        if row.get("status") not in ("QUEUED", "RUNNING"):
            raise AssertionError(f"Job ended without success: {row.get('status')}")
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))
    raise RuntimeError("Job did not complete before timeout")


def verify_replay(initial, replay, durable):
    if replay != initial or durable != initial:
        raise AssertionError("Replay changed the durable job or result")


def assert_stopped(env, name):
    state = systemctl(env, "show", name, "--property=ActiveState", "--value").stdout.strip()
    pid = systemctl(env, "show", name, "--property=MainPID", "--value").stdout.strip()
    result = systemctl(env, "show", name, "--property=Result", "--value").stdout.strip()
    if (state, pid, result) != ("inactive", "0", "success"):
        raise AssertionError(f"Service did not stop cleanly: {state}, pid={pid}, result={result}")


def main():
    env = dict(os.environ)
    runtime = preflight(env)
    # Ensure the selected bus really has a working user manager before writes.
    systemctl(env, "show-environment")
    name = f"wmm-ci-{uuid4().hex}.service"
    link = runtime / "systemd/user" / name
    if link.exists() or link.is_symlink():
        raise RuntimeError("Generated test unit name already exists")
    linked = False
    with tempfile.TemporaryDirectory(prefix="wmm-host-ci-", dir=env["HOME"]) as folder:
        directory = Path(folder)
        # systemd environment assignment is deliberately restricted to simple paths.
        if not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(directory)):
            raise RuntimeError("Disposable home path is not safe for a systemd assignment")
        unit = directory / name
        unit.write_text(
            UNIT.read_text(encoding="utf-8") + f"\n[Service]\nEnvironment=XDG_DATA_HOME={directory}/data\n",
            encoding="utf-8",
        )
        child_env = dict(env, XDG_DATA_HOME=str(directory / "data"))
        try:
            systemctl(env, "link", "--runtime", str(unit))
            linked = True
            if not link.is_symlink() or link.resolve() != unit.resolve():
                raise RuntimeError("Unexpected runtime unit link")
            systemctl(env, "start", name)
            client, csrf = session()
            workspace = directory / "data/Wize Marketing Machine"
            database = workspace / "mission-control.sqlite3"
            if not database.is_file() or database.stat().st_mode & 0o077:
                raise AssertionError("Service workspace database is not private")
            other = command(child_env, BINARY, "--headless", check=False, timeout=45)
            if (
                other.returncode == 0
                or "Workspace is already running" not in other.stderr
                or systemctl(env, "is-active", name).stdout.strip() != "active"
            ):
                raise AssertionError("A competing runtime was not excluded")
            key = "host-service-" + uuid4().hex
            queued = submit(client, ORIGIN, csrf, key)
            initial = completed_job(client, ORIGIN, queued["id"], key)
            systemctl(env, "stop", name)
            assert_stopped(env, name)
            systemctl(env, "start", name)
            client, csrf = session()
            replay = submit(client, ORIGIN, csrf, key)
            durable = completed_job(client, ORIGIN, queued["id"], key)
            verify_replay(initial, replay, durable)
            systemctl(env, "stop", name)
            assert_stopped(env, name)
        finally:
            if linked or link.is_symlink():
                if not link.is_symlink() or link.resolve() != unit.resolve():
                    raise RuntimeError("Refusing to remove a changed test unit link")
                systemctl(env, "stop", name)
                systemctl(env, "reset-failed", name, check=False)
                state = systemctl(env, "show", name, "--property=MainPID", "--value").stdout.strip()
                if state != "0":
                    raise RuntimeError("Refusing cleanup while test service process remains")
                link.unlink()
                systemctl(env, "daemon-reload")
                if link.exists() or link.is_symlink():
                    raise AssertionError("Test unit link remains")
    print(
        json.dumps(
            {
                "status": "PASS",
                "bootstrap": "VERIFIED",
                "workspace_exclusion": "VERIFIED",
                "stop_restart": "VERIFIED",
                "worker_result": "VERIFIED",
                "durable_replay": "VERIFIED",
                "job_id": initial["id"],
                "attempts": initial["attempts"],
                "stage": 5,
                "preparation_status": initial["result"]["outputs"][0]["status"],
                "unit_cleanup": "VERIFIED",
                "data": "DISPOSABLE_SYNTHETIC",
                "provider": "NOT_RUN",
            }
        )
    )


if __name__ == "__main__":
    main()
