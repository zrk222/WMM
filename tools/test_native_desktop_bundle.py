"""Verify the exact staged native shell and engine in disposable workspaces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def isolated_environment(profile):
    environment_keys = ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG', 'LC_ALL',
                        'ProgramFiles', 'ProgramFiles(x86)', 'ProgramData', 'SystemDrive')
    env = {key: os.environ[key] for key in environment_keys if key in os.environ}
    env.update(LOCALAPPDATA=str(profile), APPDATA=str(profile), USERPROFILE=str(profile),
               XDG_DATA_HOME=str(profile), HOME=str(profile))
    return env


def run(shell, profile):
    return subprocess.run([str(shell), '--verify-bundled-engine'], cwd=shell.parent,
                          env=isolated_environment(profile),
                          stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL, timeout=75).returncode


def verify_bundle(folder):
    folder = folder.resolve()
    suffix = '.exe' if sys.platform == 'win32' else ''
    shell, engine = (folder / (name + suffix) for name in ('WMM-Mission-Control', 'WMM'))
    if not shell.is_file() or not engine.is_file():
        raise ValueError('Native package must contain both the shell and frozen engine')
    with tempfile.TemporaryDirectory(prefix='wmm-native-package-') as temporary:
        isolated = Path(temporary)
        profile = isolated / 'accepted'
        if run(shell, profile) != 0:
            raise RuntimeError('Exact packaged engine verification failed')
        database = profile / 'Wize Marketing Machine' / 'mission-control.sqlite3'
        if not database.is_file():
            raise RuntimeError('Packaged engine did not open its disposable workspace')
        conn = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            if conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0] != 0:
                raise RuntimeError('Disposable package check unexpectedly created work')
        finally:
            conn.close()

        altered = isolated / 'altered-bundle'
        altered.mkdir()
        shutil.copy2(shell, altered / shell.name)
        (altered / engine.name).write_bytes(b'disposable digest mismatch fixture')
        rejected = isolated / 'rejected'
        if run(altered / shell.name, rejected) == 0 or rejected.exists():
            raise RuntimeError('Native shell did not reject an altered engine before startup')
    return dict(status='PASS', shell_sha256=digest(shell), engine_sha256=digest(engine),
                exact_engine='VERIFIED', graceful_shutdown=True, altered_engine='REJECTED_BEFORE_START',
                profile='DISPOSABLE_SYNTHETIC', interactive_webview='NOT_RUN')


def close_owned_windows_window(child, database):
    """Find the launched window by process and title before posting its close event."""
    import ctypes
    from ctypes import wintypes

    user = ctypes.WinDLL('user32', use_last_error=True)
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
            if title.value == 'Wize Marketing Machine':
                windows.append(window)
        return True

    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('Mission Control exited before opening its window')
        if database.is_file():
            if not user.EnumWindows(collect, 0):
                raise ctypes.WinError(ctypes.get_last_error())
            if windows:
                if len(windows) != 1:
                    raise RuntimeError('Mission Control opened more than one primary window')
                if not user.PostMessageW(windows[0], 0x0010, 0, 0):  # WM_CLOSE
                    raise ctypes.WinError(ctypes.get_last_error())
                return
        time.sleep(.25)
    raise RuntimeError('Mission Control native window or disposable workspace was unavailable')


def verify_windows_window(folder):
    """Exercise the real Windows entry point and the operating system window-close event."""
    if sys.platform != 'win32':
        raise ValueError('Native window verification requires Windows')
    shell = folder.resolve(strict=True) / 'WMM-Mission-Control.exe'
    with tempfile.TemporaryDirectory(prefix='wmm-native-window-', ignore_cleanup_errors=True) as temporary:
        profile = Path(temporary)
        env = isolated_environment(profile)
        env['WEBVIEW2_USER_DATA_FOLDER'] = str(profile / 'webview')
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 7  # SW_SHOWMINNOACTIVE
        child = subprocess.Popen([str(shell)], cwd=shell.parent, env=env, startupinfo=startup,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            database = profile / 'Wize Marketing Machine' / 'mission-control.sqlite3'
            close_owned_windows_window(child, database)
            exit_code = child.wait(timeout=50)
            if exit_code != 0:
                raise RuntimeError(f'Mission Control returned {exit_code} after its native window closed')
            if not database.is_file():
                raise RuntimeError('Native window did not use its disposable workspace')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    return dict(status='PASS', window='VERIFIED_WINDOWS_NATIVE_HANDLE', exit_code=0,
                profile='DISPOSABLE_SYNTHETIC', shell_sha256=digest(shell))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--windows-window', action='store_true')
    args = parser.parse_args()
    verify = verify_windows_window if args.windows_window else verify_bundle
    print(json.dumps(verify(args.folder)))


if __name__ == '__main__':
    main()
