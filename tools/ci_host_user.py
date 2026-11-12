"""Root-only, disposable GitHub Ubuntu CI wrapper for the host-service test."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path("/usr/lib/wize-marketing-machine/WMM")
UNIT = Path("/usr/share/wize-marketing-machine/wmm-worker.service")
TEMP_ROOT = Path("/tmp")
SYSTEM_PYTHON = Path("/usr/bin/python3")


def preflight(env):
    # Before making directories, accounts, lingering configuration or services.
    required = {
        "CI": "true",
        "GITHUB_ACTIONS": "true",
        "WMM_HOST_SERVICE_CI": "1",
        "WMM_LINUX_PACKAGE_TEST": "1",
        "WMM_ISOLATED_NATIVE_KEYRING": "1",
    }
    if not sys.platform.startswith("linux") or any(env.get(k) != v for k, v in required.items()) or os.geteuid() != 0:
        raise RuntimeError("Requires explicitly enabled root isolated GitHub Ubuntu package CI")
    temp = Path(env.get("RUNNER_TEMP", "/nonexistent"))
    if (
        not temp.is_absolute()
        or not temp.is_dir()
        or temp.resolve() != temp
        or not re.fullmatch(r"/[A-Za-z0-9_./-]+", str(temp))
        or not Path("/run/systemd/system").is_dir()
        or not BINARY.is_file()
        or not os.access(BINARY, os.X_OK)
        or not UNIT.is_file()
        or not os.access(UNIT, os.R_OK)
        or not SYSTEM_PYTHON.is_file()
        or not os.access(SYSTEM_PYTHON, os.X_OK)
        or not TEMP_ROOT.is_dir()
        or TEMP_ROOT.is_symlink()
        or TEMP_ROOT.stat().st_uid != 0
        or not TEMP_ROOT.stat().st_mode & 0o1000
    ):
        raise RuntimeError("CI temporary path, installed WMM, unit or systemd is unavailable")
    for executable in ("useradd", "userdel", "runuser", "systemctl", "loginctl"):
        if not shutil.which(executable):
            raise RuntimeError(f"Missing required CI executable: {executable}")
    if command("systemctl", "is-active", "systemd-logind.service", check=False).returncode != 0:
        raise RuntimeError("An active systemd-logind service is required for disposable user managers")
    return TEMP_ROOT


def command(*argv, check=True, timeout=90):
    return subprocess.run([str(item) for item in argv], check=check, text=True, capture_output=True, timeout=timeout)


def wait_user_manager(uid):
    bus = Path("/run/user") / str(uid) / "bus"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        active = command("systemctl", "is-active", f"user@{uid}.service", check=False)
        if active.returncode == 0 and bus.exists():
            return
        time.sleep(0.25)
    raise RuntimeError("Disposable user manager or bus did not start")


def stage_harness(parent):
    """Copy only the standalone script; the isolated user never traverses the checkout."""
    data = (ROOT / "tools/test_host_service.py").read_bytes()
    staged = parent / "test_host_service.py"
    with staged.open("xb") as target:
        target.write(data)
    staged.chmod(0o644)
    if staged.read_bytes() != data:
        raise RuntimeError("Staged CI harness differs from the source script")
    return staged


def child_command(name, home, runtime, parent, staged):
    child_env = [
        f"HOME={home}",
        f"USER={name}",
        f"LOGNAME={name}",
        f"XDG_RUNTIME_DIR={runtime}",
        f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus",
        f"RUNNER_TEMP={parent}",
        "PATH=/usr/sbin:/usr/bin:/sbin:/bin",
        "CI=true",
        "GITHUB_ACTIONS=true",
        "WMM_HOST_SERVICE_CI=1",
        "WMM_ISOLATED_USER_MANAGER=1",
    ]
    return ["runuser", "-u", name, "--", "/usr/bin/env", "-i", *child_env, str(SYSTEM_PYTHON), str(staged)]


def run_host_service(env):
    """Run while the package is installed; return only after verified cleanup."""
    temp = preflight(env)
    import pwd

    name = "wmm-ci-" + uuid4().hex[:12]
    linger = Path("/var/lib/systemd/linger") / name
    try:
        pwd.getpwnam(name)
    except KeyError:
        pass
    else:
        raise RuntimeError("Generated CI user already exists")
    if linger.exists() or linger.is_symlink():
        raise RuntimeError("Generated CI user has pre-existing lingering state")
    parent = Path(tempfile.mkdtemp(prefix="wmm-host-user-", dir=temp))
    home = parent / "home"
    created = False
    manager_attempted = False
    uid = None
    try:
        parent.chmod(0o711)
        staged = stage_harness(parent)
        command(
            "useradd",
            "--no-create-home",
            "--gid",
            "nogroup",
            "--home-dir",
            str(home),
            "--shell",
            "/usr/sbin/nologin",
            "--password",
            "!",
            name,
        )
        created = True
        account = pwd.getpwnam(name)
        uid = account.pw_uid
        if uid == 0 or Path(account.pw_dir) != home or account.pw_shell != "/usr/sbin/nologin":
            raise RuntimeError("Created CI account does not match its intended scope")
        runtime = Path("/run/user") / str(uid)
        state = command("systemctl", "show", f"user@{uid}.service", "--property=ActiveState", "--value").stdout.strip()
        if runtime.exists() or runtime.is_symlink() or state != "inactive" or linger.exists() or linger.is_symlink():
            raise RuntimeError("Refusing a pre-existing user manager, runtime or lingering state")
        home.mkdir(mode=0o700)
        os.chown(home, uid, account.pw_gid)
        for path, mode in ((parent, "-x"), (staged, "-r"), (UNIT, "-r"), (SYSTEM_PYTHON, "-x")):
            command("runuser", "-u", name, "--", "/usr/bin/test", mode, path)
        manager_attempted = True
        command("loginctl", "enable-linger", name)
        command("systemctl", "start", f"user@{uid}.service")
        wait_user_manager(uid)
        try:
            result = command(*child_command(name, home, runtime, parent, staged), timeout=240)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Disposable host lifecycle failed: {exc.stdout}\n{exc.stderr}") from exc
        print(result.stdout, end="")
    finally:
        if created:
            current = pwd.getpwnam(name)
            if uid is None or current.pw_uid != uid or Path(current.pw_dir) != home:
                raise RuntimeError("Refusing cleanup because CI account identity changed")
            if manager_attempted:
                command("loginctl", "disable-linger", name)
                command("systemctl", "stop", f"user@{uid}.service")
                command("systemctl", "stop", f"user-runtime-dir@{uid}.service")
                if (
                    Path("/run/user", str(uid)).exists()
                    or linger.exists()
                    or command("systemctl", "is-active", f"user@{uid}.service", check=False).returncode == 0
                ):
                    raise RuntimeError("Disposable user manager cleanup is incomplete")
            command("userdel", name)  # Deliberately no -r: only our checked parent is removed below.
            try:
                pwd.getpwnam(name)
            except KeyError:
                pass
            else:
                raise RuntimeError("Disposable CI user still exists")
        if (
            parent.is_symlink()
            or parent.resolve().parent != temp
            or parent.stat().st_uid != 0
            or not parent.name.startswith("wmm-host-user-")
        ):
            raise RuntimeError("Refusing cleanup of an unexpected CI temporary parent")
        shutil.rmtree(parent)
        if parent.exists() or parent.is_symlink():
            raise RuntimeError("Disposable CI home remains")
    print("WMM_HOST_USER_CLEANUP=VERIFIED")


if __name__ == "__main__":
    run_host_service(dict(os.environ))
