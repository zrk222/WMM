"""Real hidden-console Ctrl+C against an isolated Windows headless child only."""

import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

from mission_control.workspace_lock import WorkspaceLock


HELPER = r"""
import ctypes, json, os, sys, time
from ctypes import wintypes
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.AttachConsole.argtypes = [wintypes.DWORD]
kernel.AttachConsole.restype = wintypes.BOOL
kernel.GetConsoleProcessList.argtypes = [ctypes.POINTER(wintypes.DWORD), wintypes.DWORD]
kernel.GetConsoleProcessList.restype = wintypes.DWORD
kernel.SetConsoleCtrlHandler.argtypes = [ctypes.c_void_p, wintypes.BOOL]
kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
kernel.GenerateConsoleCtrlEvent.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
target = int(sys.argv[1])
kernel.FreeConsole()
if not kernel.AttachConsole(target):
    raise OSError(ctypes.get_last_error(), 'AttachConsole failed')
try:
    clients = (wintypes.DWORD * 32)()
    count = kernel.GetConsoleProcessList(clients, len(clients))
    actual = sorted(clients[:count]) if 0 < count <= len(clients) else []
    expected = sorted([target, os.getpid()])
    if actual != expected:
        raise RuntimeError('Refusing Ctrl+C: console clients differ from test child and helper')
    if not kernel.SetConsoleCtrlHandler(None, True):
        raise OSError(ctypes.get_last_error(), 'Cannot protect signal helper')
    if not kernel.GenerateConsoleCtrlEvent(0, 0):
        raise OSError(ctypes.get_last_error(), 'GenerateConsoleCtrlEvent failed')
    print(json.dumps({'status':'SENT','clients':actual,'target':target,'helper':os.getpid()}), flush=True)
    time.sleep(.25)
finally:
    kernel.FreeConsole()
"""


@unittest.skipUnless(sys.platform == "win32", "Windows console control events only")
class WindowsHeadlessSignalTests(unittest.TestCase):
    def test_hidden_console_ctrl_c_exits_and_releases_workspace_lock(self):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", 8765))
            except OSError as exc:
                self.skipTest(f"Fixed loopback port is unavailable: {exc}")
        with tempfile.TemporaryDirectory(prefix="wmm-headless-signal-") as folder:
            env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP", "PATH") if key in os.environ}
            env.update(LOCALAPPDATA=folder, APPDATA=folder, USERPROFILE=folder, HOME=folder, PYTHONUTF8="1")
            info = subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow = 0
            child = subprocess.Popen(
                [sys.executable, "-u", "-m", "mission_control.desktop", "--headless"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                startupinfo=info,
            )
            try:
                lines = queue.Queue()
                threading.Thread(target=lambda: lines.put(child.stdout.readline()), daemon=True).start()
                try:
                    line = lines.get(timeout=30)
                except queue.Empty:
                    self.fail("Disposable headless child did not start within 30 seconds")
                self.assertTrue(line, "Disposable headless child exited before its startup receipt")
                self.assertEqual(
                    json.loads(line), {"status": "RUNNING", "origin": "http://127.0.0.1:8765", "mode": "HEADLESS"}
                )
                self.assertIsNone(child.poll(), "Disposable child exited before signal")
                helper = subprocess.run(
                    [sys.executable, "-c", HELPER, str(child.pid)],
                    env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                receipt = json.loads(helper.stdout)
                self.assertEqual(receipt["target"], child.pid)
                self.assertEqual(set(receipt["clients"]), {child.pid, receipt["helper"]})
                print("Isolated Ctrl+C receipt: " + json.dumps(receipt), flush=True)
                try:
                    result = child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.fail("Headless child did not exit within 10 seconds after isolated Ctrl+C")
                self.assertEqual(result, 0, child.stderr.read())
                lock = WorkspaceLock(Path(folder) / "Wize Marketing Machine")
                lock.acquire()
                lock.release()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
                child.stdout.close()
                child.stderr.close()


if __name__ == "__main__":
    unittest.main()
