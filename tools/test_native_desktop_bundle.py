"""Verify the exact staged native shell and engine in disposable workspaces."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def isolated_environment(profile):
    environment_keys = (
        "PATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "ProgramFiles",
        "ProgramFiles(x86)",
        "ProgramData",
        "SystemDrive",
    )
    env = {key: os.environ[key] for key in environment_keys if key in os.environ}
    env.update(
        LOCALAPPDATA=str(profile),
        APPDATA=str(profile),
        USERPROFILE=str(profile),
        XDG_DATA_HOME=str(profile),
        HOME=str(profile),
    )
    return env


def run(shell, profile):
    return subprocess.run(
        [str(shell), "--verify-bundled-engine"],
        cwd=shell.parent,
        env=isolated_environment(profile),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=75,
    ).returncode


def verify_bundle(folder):
    folder = folder.resolve()
    suffix = ".exe" if sys.platform == "win32" else ""
    shell, engine = (folder / (name + suffix) for name in ("WMM-Mission-Control", "WMM"))
    if not shell.is_file() or not engine.is_file():
        raise ValueError("Native package must contain both the shell and frozen engine")
    with tempfile.TemporaryDirectory(prefix="wmm-native-package-") as temporary:
        isolated = Path(temporary)
        profile = isolated / "accepted"
        if run(shell, profile) != 0:
            raise RuntimeError("Exact packaged engine verification failed")
        data_root = profile / "Library/Application Support" if sys.platform == "darwin" else profile
        database = data_root / "Wize Marketing Machine" / "mission-control.sqlite3"
        if not database.is_file():
            raise RuntimeError("Packaged engine did not open its disposable workspace")
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        try:
            if conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] != 0:
                raise RuntimeError("Disposable package check unexpectedly created work")
        finally:
            conn.close()

        altered = isolated / "altered-bundle"
        altered.mkdir()
        shutil.copy2(shell, altered / shell.name)
        (altered / engine.name).write_bytes(b"disposable digest mismatch fixture")
        rejected = isolated / "rejected"
        if run(altered / shell.name, rejected) == 0 or rejected.exists():
            raise RuntimeError("Native shell did not reject an altered engine before startup")
    return dict(
        status="PASS",
        shell_sha256=digest(shell),
        engine_sha256=digest(engine),
        exact_engine="VERIFIED",
        graceful_shutdown=True,
        altered_engine="REJECTED_BEFORE_START",
        profile="DISPOSABLE_SYNTHETIC",
        interactive_webview="NOT_RUN",
    )


def close_owned_windows_window(child, database):
    """Find the launched window by process and title before posting its close event."""
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL("user32", use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = (callback_type, wintypes.LPARAM)
    user.EnumWindows.restype = wintypes.BOOL
    user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user.GetWindowTextW.restype = ctypes.c_int
    user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user.PostMessageW.restype = wintypes.BOOL
    windows = []

    @callback_type
    def collect(window, _parameter):
        owner = wintypes.DWORD()
        user.GetWindowThreadProcessId(window, ctypes.byref(owner))
        if owner.value == child.pid:
            title = ctypes.create_unicode_buffer(64)
            user.GetWindowTextW(window, title, len(title))
            if title.value == "Wize Marketing Machine":
                windows.append(window)
        return True

    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError("Mission Control exited before opening its window")
        if database.is_file():
            if not user.EnumWindows(collect, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            if windows:
                if len(windows) != 1:
                    raise RuntimeError("Mission Control opened more than one primary window")
                if not user.PostMessageW(windows[0], 0x0010, 0, 0):  # WM_CLOSE
                    raise ctypes.WinError(ctypes.get_last_error())
                return
        time.sleep(0.25)
    raise RuntimeError("Mission Control native window or disposable workspace was unavailable")


def verify_windows_window(folder):
    """Exercise the real Windows entry point and the operating system window-close event."""
    if sys.platform != "win32":
        raise ValueError("Native window verification requires Windows")
    shell = folder.resolve(strict=True) / "WMM-Mission-Control.exe"
    with tempfile.TemporaryDirectory(prefix="wmm-native-window-", ignore_cleanup_errors=True) as temporary:
        profile = Path(temporary)
        env = isolated_environment(profile)
        env["WEBVIEW2_USER_DATA_FOLDER"] = str(profile / "webview")
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        child = subprocess.Popen(
            [str(shell)],
            cwd=shell.parent,
            env=env,
            startupinfo=startup,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            database = profile / "Wize Marketing Machine" / "mission-control.sqlite3"
            close_owned_windows_window(child, database)
            exit_code = child.wait(timeout=50)
            if exit_code != 0:
                raise RuntimeError(f"Mission Control returned {exit_code} after its native window closed")
            if not database.is_file():
                raise RuntimeError("Native window did not use its disposable workspace")
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    return dict(
        status="PASS",
        window="VERIFIED_WINDOWS_NATIVE_HANDLE",
        exit_code=0,
        profile="DISPOSABLE_SYNTHETIC",
        shell_sha256=digest(shell),
    )


def linux_window_id(listing, pid):
    """Select only the expected titled window owned by the launched process."""
    matches = []
    for row in listing.splitlines():
        fields = row.split(maxsplit=4)
        if (
            len(fields) == 5
            and fields[2] == str(pid)
            and fields[4] == "Wize Marketing Machine"
            and re.fullmatch(r"0x[0-9a-fA-F]+", fields[0])
        ):
            matches.append(fields[0])
    if len(matches) > 1:
        raise RuntimeError("Mission Control opened more than one primary window")
    return matches[0] if matches else None


def linux_window_observation(env, pid):
    result = subprocess.run(
        ["wmctrl", "-l", "-p"],
        env=env,
        timeout=5,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        reason = result.stderr.strip()[-1024:]
        return None, reason or f"wmctrl exited with status {result.returncode}"
    return linux_window_id(result.stdout, pid), None


def verify_linux_window(folder):
    """Launch the bundled Linux window on an isolated, unprivileged CI display."""
    if (
        sys.platform != "linux"
        or os.geteuid() == 0
        or any(
            os.environ.get(key) != value
            for key, value in (("CI", "true"), ("GITHUB_ACTIONS", "true"), ("WMM_LINUX_NATIVE_WINDOW_CI", "1"))
        )
        or not all(os.environ.get(key) for key in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"))
    ):
        raise RuntimeError("Linux window verification requires the disposable unprivileged CI display")
    folder = folder.resolve(strict=True)
    shell, engine = folder / "WMM-Mission-Control", folder / "WMM"
    with tempfile.TemporaryDirectory(prefix="wmm-native-window-") as temporary:
        profile = Path(temporary)
        env = isolated_environment(profile)
        env.update({key: os.environ[key] for key in ("DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS")})
        env["GDK_BACKEND"] = "x11"
        manager = subprocess.Popen(
            ["openbox", "--sm-disable"],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        child = None
        try:
            for _ in range(40):
                if manager.poll() is not None:
                    raise RuntimeError("Disposable window manager stopped")
                if subprocess.run(["wmctrl", "-m"], env=env, timeout=5, capture_output=True).returncode == 0:
                    break
                time.sleep(0.25)
            else:
                raise RuntimeError("Disposable window manager did not start")
            with (profile / "window.log").open("w+b") as log:
                child = subprocess.Popen(
                    [str(shell)], cwd=folder, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT
                )
                database = profile / "Wize Marketing Machine" / "mission-control.sqlite3"
                deadline = time.monotonic() + 35
                last_window_error = None
                try:
                    while child.poll() is None and time.monotonic() < deadline:
                        if manager.poll() is not None:
                            raise RuntimeError("Disposable window manager stopped during startup")
                        window, observation_error = linux_window_observation(env, child.pid)
                        if observation_error:
                            last_window_error = observation_error
                        if window and database.is_file():
                            subprocess.run(
                                ["wmctrl", "-i", "-c", window], env=env, timeout=5, check=True, capture_output=True
                            )
                            if child.wait(timeout=45) != 0:
                                raise RuntimeError("Mission Control failed after the native close event")
                            break
                        time.sleep(0.25)
                    else:
                        reason = f": {last_window_error}" if last_window_error else ""
                        raise RuntimeError(
                            "Native Mission Control window or disposable workspace did not open" + reason
                        )
                except (RuntimeError, subprocess.SubprocessError) as error:
                    log.seek(max(0, log.seek(0, os.SEEK_END) - 4096))
                    raise RuntimeError(f"{error}\n{log.read().decode(errors='replace')}") from error
        finally:
            for process in (child, manager):
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=10)
    return dict(
        status="PASS",
        window="VERIFIED_LINUX_X11_NATIVE_HANDLE",
        exit_code=0,
        profile="DISPOSABLE_SYNTHETIC",
        shell_sha256=digest(shell),
        engine_sha256=digest(engine),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    native = parser.add_mutually_exclusive_group()
    native.add_argument("--windows-window", action="store_true")
    native.add_argument("--linux-window", action="store_true")
    args = parser.parse_args()
    verify = (
        verify_windows_window if args.windows_window else verify_linux_window if args.linux_window else verify_bundle
    )
    print(json.dumps(verify(args.folder)))


if __name__ == "__main__":
    main()
