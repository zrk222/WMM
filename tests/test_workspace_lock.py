"""OS lock contention and release use independent local subprocesses."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from mission_control.workspace_lock import WorkspaceBusy, WorkspaceLock


class WorkspaceLockTests(unittest.TestCase):
    def test_competing_subprocess_and_abrupt_exit_release(self):
        with tempfile.TemporaryDirectory() as folder:
            code = (
                "import sys; from mission_control.workspace_lock import WorkspaceLock; "
                "lock=WorkspaceLock(sys.argv[1]); lock.acquire(); print('READY',flush=True); "
                "sys.stdin.readline()"
            )
            child = subprocess.Popen(
                [sys.executable, "-u", "-c", code, folder],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                self.assertEqual(child.stdout.readline().strip(), "READY")
                with self.assertRaises(WorkspaceBusy):
                    WorkspaceLock(Path(folder) / ".").acquire()
                child.kill()
                child.wait(timeout=10)
                lock = WorkspaceLock(folder)
                lock.acquire()
                lock.release()
                lock.release()
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=10)
                for stream in (child.stdin, child.stdout, child.stderr):
                    stream.close()

    def test_distinct_workspaces_do_not_compete(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first, second = WorkspaceLock(a), WorkspaceLock(b)
            first.acquire()
            try:
                second.acquire()
                second.release()
            finally:
                first.release()


if __name__ == "__main__":
    unittest.main()
