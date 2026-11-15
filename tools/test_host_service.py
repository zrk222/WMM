"""Opt-in disposable Ubuntu CI user-manager lifecycle test; never provision a host."""

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

BINARY = Path("/usr/lib/wize-marketing-machine/WMM")
UNIT = Path("/usr/share/wize-marketing-machine/wmm-worker.service")
ORIGIN = "http://127.0.0.1:8765"
APP = "host-packet-fixture"
STAGE = 1
APP_FACTS = {
    "name": "Synthetic host packet",
    "job": "Find the next task to finish",
    "audience": "Independent app makers",
    "activation": "Choose one next task",
    "release": "0.1.0",
    "locale": "en-US",
}


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


def command(env, *args, check=True, timeout=75, stdin=None):
    return subprocess.run(
        [str(x) for x in args], env=env, check=check, capture_output=True, text=True, timeout=timeout, input=stdin
    )


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


def request_json(client, origin, path, body=None, csrf=None, *, canary=None, timeout=2):
    headers = {"Origin": origin}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers.update({"Content-Type": "application/json", "X-CSRF-Token": csrf})
    if not re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}", origin) or not path.startswith("/api/"):
        raise ValueError("Expected an API path on the exact loopback origin")
    try:
        response = client.open(Request(origin + path, data=data, headers=headers), timeout=timeout)  # noqa: S310
    except HTTPError as exc:
        if canary is None:
            raise
        with exc:
            assert_secret_absent(exc.headers.as_bytes(), canary)
            assert_secret_absent(exc.read(), canary)
        raise AssertionError(f"Protected fixture request returned HTTP {exc.code}") from None
    with response:
        raw = response.read()
        if canary is not None:
            assert_secret_absent(response.headers.as_bytes(), canary)
            assert_secret_absent(raw, canary)
        return json.loads(raw)


def register_app(client, origin, csrf):
    app = request_json(client, origin, "/api/apps", {"id": APP, "data": APP_FACTS}, csrf)
    facts = app.get("data")
    if (
        app.get("id") != APP
        or app.get("version") != 1
        or not isinstance(facts, dict)
        or any(facts.get(field) != value for field, value in APP_FACTS.items())
    ):
        raise AssertionError("Synthetic app was not registered as a fresh workspace")
    return facts


def assert_secret_absent(value, canary):
    if canary.encode() in value or b"BEGIN PRIVATE KEY" in value:
        raise AssertionError("Protected test material escaped the native keyring")


def open_disposable_keyring(env):
    # This account has its own fresh home and user bus. Remove the packaged socket
    # activation path so only the daemon launched on the explicit bus can serve it.
    systemctl(env, "stop", "gnome-keyring-daemon.socket", "gnome-keyring-daemon.service")
    unlock = command(
        env, "gnome-keyring-daemon", "--unlock", "--components=secrets", stdin=uuid4().hex, timeout=20, check=False
    )
    if unlock.returncode:
        raise RuntimeError("Disposable Secret Service did not initialize")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        reply = command(
            env,
            "busctl",
            "--address=" + env["DBUS_SESSION_BUS_ADDRESS"],
            "--timeout=2",
            "call",
            "org.freedesktop.secrets",
            "/org/freedesktop/secrets",
            "org.freedesktop.Secret.Service",
            "ReadAlias",
            "s",
            "default",
            timeout=4,
            check=False,
        )
        if reply.returncode == 0 and re.fullmatch(
            r'o "/org/freedesktop/secrets/collection/[A-Za-z0-9_]+"', reply.stdout.strip()
        ):
            return
        time.sleep(0.25)
    raise RuntimeError("Disposable Secret Service did not expose a default collection on the worker bus")


def register_protected_connection(env, client, csrf):
    # The generated key is held in process memory until the existing local setup
    # route hands it to Secret Service.
    open_disposable_keyring(env)
    empty = request_json(client, ORIGIN, f"/api/apps/{APP}")
    if empty["connections"]:
        raise AssertionError("Disposable app unexpectedly has an existing connection")
    generated = command(
        env, "openssl", "genpkey", "-algorithm", "EC", "-pkeyopt", "ec_paramgen_curve:P-256", timeout=10
    )
    key = generated.stdout.strip()
    canary = key.splitlines()[1][-32:]
    response = request_json(
        client,
        ORIGIN,
        f"/api/apps/{APP}/connections",
        {
            "provider": "app_store",
            "store_app_id": "123",
            "issuer_id": "fixture",
            "key_id": "fixture",
            "private_key": key,
        },
        csrf,
        canary=canary,
    )
    record = response["record"]
    if response["status"] != "CONFIGURED_UNTESTED" or record["kind"] != "connection":
        raise AssertionError("Local protected setup did not retain the synthetic binding")
    return record, canary


def assert_connection_status(client, record, canary, status, cleanup=None):
    workspace = request_json(client, ORIGIN, f"/api/apps/{APP}", canary=canary)
    expected = {"status": status}
    if cleanup is not None:
        expected["cleanup"] = cleanup
    if workspace["connections"].get(record["id"]) != expected:
        raise AssertionError("Saved connection does not match its expected protected state")


def remove_protected_connection(client, csrf, record, canary):
    reply = request_json(
        client,
        ORIGIN,
        f"/api/apps/{APP}/connections/{record['id']}/disconnect",
        {"version": record["version"]},
        csrf,
        canary=canary,
    )
    if reply != {
        "status": "DISCONNECTED",
        "provider_revocation": "NOT_PERFORMED",
        "cleanup": "PRIOR_LOCAL_KEY_REMOVED",
    }:
        raise AssertionError("Disposable protected item was not removed locally")
    assert_connection_status(client, record, canary, "DISCONNECTED", "NOT_PRESENT")


def assert_workspace_private(workspace, canary):
    for filename in ("mission-control.sqlite3", "mission-control.sqlite3-wal", "mission-control.sqlite3-journal"):
        path = workspace / filename
        if filename == "mission-control.sqlite3" or path.exists():
            assert_secret_absent(path.read_bytes(), canary)


def assert_service_output_private(output, canary):
    raw = output.read_bytes()
    assert_secret_absent(raw, canary)
    if raw.count(b'"status": "RUNNING"') != 2:
        raise AssertionError("Expected private output from both service invocations")


def submit(client, origin, csrf, key):
    row = request_json(
        client,
        origin,
        f"/api/apps/{APP}/jobs",
        {"action": "pipeline", "data": {"stage": STAGE}, "request_key": key},
        csrf,
    )
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"]
        or row.get("app_id") != APP
        or row.get("action") != "pipeline"
        or row.get("data") != {"stage": STAGE}
        or row.get("request_key") != key
    ):
        raise AssertionError("Queued job identity does not match the synthetic request")
    return row


def job_history_reads(client, origin, timeout):
    """Bound retries and result acceptance; a socket timeout is not an HTTP deadline."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            rows = request_json(client, origin, f"/api/apps/{APP}/jobs", timeout=min(2, remaining))
        except TimeoutError:
            pass
        else:
            if time.monotonic() >= deadline:
                return
            yield rows
        time.sleep(min(0.25, max(0, deadline - time.monotonic())))


def completed_job(client, origin, job_id, key, expected_facts, timeout=45):
    """Find exactly one request-key row and require a real successful result."""
    for rows in job_history_reads(client, origin, timeout):
        if not isinstance(rows, list):
            raise AssertionError("Job history is not a list")
        matches = [row for row in rows if isinstance(row, dict) and row.get("request_key") == key]
        if len(matches) != 1 or matches[0].get("id") != job_id:
            raise AssertionError("Job history does not contain exactly the requested identity")
        row = matches[0]
        if row.get("status") == "SUCCEEDED":
            result = row.get("result")
            if (
                row.get("app_id") != APP
                or row.get("action") != "pipeline"
                or row.get("data") != {"stage": STAGE}
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
                or result["outputs"][0]["stage"] != STAGE
                or result["outputs"][0].get("status") != "PREPARED"
                or not isinstance(result["outputs"][0].get("packet"), dict)
                or result["outputs"][0]["packet"].get("schema") != "growth.stage-packet.v1"
                or result["outputs"][0]["packet"].get("app_id") != APP
                or result["outputs"][0]["packet"].get("stage") != STAGE
                or result["outputs"][0]["packet"].get("external_execution") != "NOT_RUN"
            ):
                raise AssertionError("Completed job does not prove the requested local preparation")
            packet = result["outputs"][0]["packet"]
            content = packet.get("content")
            facts = content.get("app_facts") if isinstance(content, dict) else None
            if (
                packet.get("manifest_version") != 1
                or packet.get("local_status") != "PREPARED"
                or not isinstance(content, dict)
                or facts != expected_facts
                or not content.get("operator_steps")
            ):
                raise AssertionError("Prepared packet does not contain the registered synthetic app facts")
            return row
        if row.get("status") not in ("QUEUED", "RUNNING"):
            raise AssertionError(f"Job ended without success: {row.get('status')}")
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


def login_sessions(env):
    return command(env, "loginctl", "show-user", os.geteuid(), "-p", "Sessions", "--value").stdout.split()


def service_invocation(env, name):
    result = systemctl(env, "show", name, "-p", "ActiveState", "-p", "MainPID", "-p", "InvocationID")
    fields = dict(line.split("=", 1) for line in result.stdout.splitlines())
    invocation = fields.get("InvocationID", "")
    pid = fields.get("MainPID", "")
    if (
        fields.get("ActiveState") != "active"
        or not pid.isdigit()
        or int(pid) < 2
        or not re.fullmatch(r"[0-9a-f]{32}", invocation)
        or invocation == "0" * 32
    ):
        raise AssertionError("Cannot identify the active WMM service invocation")
    return pid, invocation


def close_login_session(env, name, timeout=30):
    session_id = env.get("WMM_TEST_LOGIN_SESSION", "")
    if not re.fullmatch(r"[A-Za-z0-9]+", session_id) or login_sessions(env) != [session_id]:
        raise AssertionError("The disposable login must be the only open OS session")
    before = service_invocation(env, name)
    (Path(env["HOME"]) / ".wmm-ci-close-session").touch(exist_ok=False)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = login_sessions(env)
        if not remaining:
            if service_invocation(env, name) != before:
                raise AssertionError("WMM service restarted during logout")
            return before
        if remaining != [session_id]:
            raise AssertionError("Unexpected OS session appeared during logout")
        time.sleep(0.25)
    raise RuntimeError("The disposable OS login did not close")


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
        output = directory / "service-output.log"
        unit.write_text(
            UNIT.read_text(encoding="utf-8")
            + f"\n[Service]\nEnvironment=XDG_DATA_HOME={directory}/data\n"
            + f"Environment=DBUS_SESSION_BUS_ADDRESS={env['DBUS_SESSION_BUS_ADDRESS']}\n"
            + f"StandardOutput=append:{output}\nStandardError=inherit\n",
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
            facts = register_app(client, ORIGIN, csrf)
            protected, canary = register_protected_connection(env, client, csrf)
            assert_connection_status(client, protected, canary, "PROTECTED_KEY_PRESENT")
            invocation = close_login_session(env, name)
            client, csrf = session()
            assert_connection_status(client, protected, canary, "PROTECTED_KEY_PRESENT")
            key = "host-service-" + uuid4().hex
            queued = submit(client, ORIGIN, csrf, key)
            initial = completed_job(client, ORIGIN, queued["id"], key, facts)
            if login_sessions(env) or service_invocation(env, name) != invocation:
                raise AssertionError("WMM job did not complete in the original service with no OS login")
            assert_workspace_private(workspace, canary)
            systemctl(env, "stop", name)
            assert_stopped(env, name)
            systemctl(env, "start", name)
            client, csrf = session()
            if login_sessions(env) or service_invocation(env, name) == invocation:
                raise AssertionError("Expected a new WMM invocation and no OS login")
            assert_connection_status(client, protected, canary, "PROTECTED_KEY_PRESENT")
            persisted = completed_job(client, ORIGIN, queued["id"], key, facts)
            if persisted != initial:
                raise AssertionError("Prepared job changed before replay")
            replay = submit(client, ORIGIN, csrf, key)
            durable = completed_job(client, ORIGIN, queued["id"], key, facts)
            verify_replay(initial, replay, durable)
            remove_protected_connection(client, csrf, protected, canary)
            assert_workspace_private(workspace, canary)
            systemctl(env, "stop", name)
            assert_stopped(env, name)
            assert_service_output_private(output, canary)
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
                "disposable_os_logout": "VERIFIED_SAME_SERVICE_JOB_COMPLETED_NO_SESSIONS",
                "protected_storage": "VERIFIED_AFTER_LOGOUT_AND_RESTART_WITH_DISPOSABLE_UNLOCKED_KEYRING",
                "protected_storage_cleanup": "VERIFIED_LOCAL_REMOVAL",
                "protected_storage_privacy": "VERIFIED_HTTP_SQLITE_AND_SERVICE_OUTPUT",
                "durable_replay": "VERIFIED",
                "job_id": initial["id"],
                "attempts": initial["attempts"],
                "stage": STAGE,
                "preparation_status": initial["result"]["outputs"][0]["status"],
                "unit_cleanup": "VERIFIED",
                "data": "DISPOSABLE_SYNTHETIC",
                "provider": "NOT_RUN",
            }
        )
    )


if __name__ == "__main__":
    main()
