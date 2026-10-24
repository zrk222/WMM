"""Real Windows process-tree ownership; no external service or stored-PID kill."""
import os
from pathlib import Path
import sys
import socket
import tempfile
import time
import unittest
from unittest.mock import patch

from mission_control import studio_child as target
from mission_control.common import Invalid


@unittest.skipUnless(os.name == 'nt', 'Windows Job Object native acceptance')
class StudioChildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wmm-owned-native-')
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def spawn(self, script, cap=4096):
        child = target.spawn_studio_child(
            [sys.executable, '-u', '-c', script], self.folder, os.environ.copy(),
            self.folder/'stdout.log', self.folder/'stderr.log', cap)
        self.addCleanup(child.stop)
        return child

    def wait(self, condition):
        deadline = time.monotonic() + 8
        while not condition():
            if time.monotonic() >= deadline:
                self.fail('native child condition timed out')
            time.sleep(.01)

    def test_descendant_survives_launcher_but_not_owned_stop(self):
        import _winapi
        descendant = "import time; from pathlib import Path; Path('ready').write_text('ready'); time.sleep(120)"
        child = self.spawn("import subprocess,sys; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c'," + repr(descendant) + "]); Path('pid').write_text(str(p.pid))")
        self.wait(lambda: (self.folder/'ready').exists() and child.poll() is not None)
        # Open only for independent liveness observation; never used to kill.
        handle = _winapi.OpenProcess(0x00100000, False, int((self.folder/'pid').read_text()))
        try:
            self.assertEqual(_winapi.WaitForSingleObject(handle, 0), 258)
            child.stop()
            self.assertEqual(_winapi.WaitForSingleObject(handle, 1000), 0)
            child.stop()
        finally:
            _winapi.CloseHandle(handle)

    def test_overflow_automatically_stops_without_snapshot_reads(self):
        child = self.spawn("import os\nwhile True:\n os.write(1,b'x'*4096)\n os.write(2,b'y'*4096)", cap=10000)
        # Native process handle observation only; no child.poll/read/stop call
        # participates in triggering the automatic log-budget shutdown.
        import _winapi
        self.assertEqual(_winapi.WaitForSingleObject(child._process, 8000), 0)
        self.assertTrue(child.overflow)
        child.stop()
        self.assertLessEqual(sum((self.folder/n).stat().st_size for n in ('stdout.log','stderr.log')), 10000)
        self.assertIsNone(child.failure)

    def test_ordinary_exit_retains_both_streams_and_cleanup(self):
        child = self.spawn("import sys; print('out'); print('err',file=sys.stderr)")
        self.wait(lambda: child.poll() is not None)
        self.assertEqual(child.poll(), 0)
        child.stop()
        self.assertEqual((self.folder/'stdout.log').read_text().strip(), 'out')
        self.assertEqual((self.folder/'stderr.log').read_text().strip(), 'err')
        self.assertIsNone(child.failure)
        self.assertFalse(child.overflow)

    def test_failed_stop_is_not_success_and_can_retry(self):
        child = self.spawn('import time; time.sleep(120)')
        with patch.object(child, '_terminate', side_effect=OSError('synthetic')):
            with self.assertRaises(Invalid):
                child.stop()
        self.assertIsNotNone(child.failure)
        self.assertIsNotNone(child._job)
        child.stop()

    def test_partial_handle_release_failure_remains_retryable(self):
        import _winapi
        child=self.spawn('import time;time.sleep(120)')
        job=child._job;original=_winapi.CloseHandle
        def close(handle):
            if handle==job:raise OSError('Synthetic job handle close failure')
            return original(handle)
        with patch.object(_winapi,'CloseHandle',side_effect=close):
            with self.assertRaises(Invalid):child.stop()
        self.assertIsNone(child._process);self.assertIsNotNone(child._job)
        child.stop();self.assertIsNone(child._job)

    def test_write_failure_automatically_stops_and_is_visible(self):
        real_open = open
        class BrokenOutput:
            def __init__(self, wrapped): self.wrapped = wrapped
            def __enter__(self): return self
            def __exit__(self, *args): self.close()
            def close(self): self.wrapped.close()
            def write(self, data): raise OSError('synthetic private detail')
        def opening(path, *args, **kwargs):
            result = real_open(path, *args, **kwargs)
            return BrokenOutput(result) if str(path).endswith('stdout.log') else result
        with patch.object(target, 'open', side_effect=opening, create=True):
            child = self.spawn("import os,time; os.write(1,b'hello'); time.sleep(120)")
        import _winapi
        self.assertEqual(_winapi.WaitForSingleObject(child._process, 8000), 0)
        self.assertEqual(child.failure, 'diagnostic capture: OSError')
        child.stop()

    def test_assignment_failure_never_runs_child(self):
        kernel = target._native()
        with patch.object(kernel, 'AssignProcessToJobObject', return_value=0), patch.object(target, '_native', return_value=kernel):
            with self.assertRaises(Invalid):
                self.spawn("from pathlib import Path; Path('escaped').write_text('bad')")
        self.assertFalse((self.folder/'escaped').exists())

    def test_existing_log_is_not_overwritten(self):
        (self.folder/'stdout.log').write_text('keep')
        with self.assertRaises(Invalid):
            self.spawn("print('bad')")
        self.assertEqual((self.folder/'stdout.log').read_text(), 'keep')

    def test_resume_failure_cleans_started_readers_and_never_runs_child(self):
        kernel = target._native()
        with patch.object(kernel, 'ResumeThread', return_value=0xffffffff), patch.object(target, '_native', return_value=kernel):
            with self.assertRaises(Invalid):
                self.spawn("from pathlib import Path; Path('escaped').write_text('bad')")
        self.assertFalse((self.folder/'escaped').exists())
        # Windows would reject deletion if either private output were still open.
        (self.folder/'stdout.log').unlink()
        (self.folder/'stderr.log').unlink()

    def test_missing_executable_is_invalid_and_releases_logs(self):
        with self.assertRaises(Invalid):
            target.spawn_studio_child(
                [str(self.folder/'does-not-exist.exe')], self.folder, os.environ.copy(),
                self.folder/'stdout.log', self.folder/'stderr.log', 100)
        (self.folder/'stdout.log').unlink()
        (self.folder/'stderr.log').unlink()

    def test_descendant_listener_remains_owned_after_launcher_exit(self):
        script = "import socket,time; from pathlib import Path; s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(); Path('port').write_text(str(s.getsockname()[1])); time.sleep(120)"
        child = self.spawn("import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(script) + "])")
        self.wait(lambda: (self.folder/'port').exists() and child.poll() is not None)
        port = int((self.folder/'port').read_text())
        self.assertTrue(child.owns_listener(port))
        child.stop()
        self.assertFalse(child.owns_listener(port))

    def test_foreign_listener_wins_released_port_and_is_not_adopted(self):
        with socket.socket() as selected:
            selected.bind(('127.0.0.1', 0))
            port = selected.getsockname()[1]
        with socket.socket() as foreign:
            foreign.bind(('127.0.0.1', port))
            foreign.listen()
            child = self.spawn("import socket; s=socket.socket(); s.bind(('127.0.0.1'," + str(port) + ")); s.listen()")
            self.wait(lambda: child.poll() is not None)
            self.assertNotEqual(child.poll(), 0)
            self.assertFalse(child.owns_listener(port))

    def test_no_listener_is_not_owned(self):
        child = self.spawn('import time; time.sleep(120)')
        with socket.socket() as unused:
            unused.bind(('127.0.0.1', 0))
            self.assertFalse(child.owns_listener(unused.getsockname()[1]))

    def test_listener_inspection_failure_is_not_false_success(self):
        child = self.spawn('import time; time.sleep(120)')
        with patch.object(target, '_listener_rows', side_effect=OSError('synthetic')):
            with self.assertRaises(Invalid):
                child.owns_listener(12345)

    def test_failed_launch_rollback_retains_owned_job_for_retry(self):
        import _winapi
        kernel = target._native()
        with patch.object(target, '_native', return_value=kernel), \
                patch.object(kernel, 'ResumeThread', return_value=0xffffffff), \
                patch.object(kernel, 'TerminateJobObject', return_value=0):
            with self.assertRaises(target.LaunchCleanupPending) as caught:
                self.spawn('import time; time.sleep(120)')
        owner = caught.exception.owner
        self.addCleanup(owner.stop)
        self.assertFalse(caught.exception.cleanup_confirmed)
        self.assertFalse(owner.cleanup_confirmed)
        self.assertIsNotNone(owner.job)
        self.assertIsNotNone(owner.process)
        self.assertIsNotNone(owner.thread)
        self.assertEqual(owner.owned._job, owner.job)
        self.assertEqual(_winapi.WaitForSingleObject(owner.process, 0), 258)
        self.assertTrue(any(t.is_alive() for t in owner.owned._threads))
        owner.stop()
        self.assertTrue(owner.cleanup_confirmed)
        self.assertIsNone(owner.job)
        self.assertIsNone(owner.process)
        self.assertIsNone(owner.thread)
        self.assertTrue(all(not t.is_alive() for t in owner.owned._threads))
        (self.folder/'stdout.log').unlink()
        (self.folder/'stderr.log').unlink()

    def test_preassignment_rollback_retains_suspended_process_for_retry(self):
        import _winapi
        kernel = target._native()
        with patch.object(target, '_native', return_value=kernel), \
                patch.object(kernel, 'AssignProcessToJobObject', return_value=0), \
                patch.object(_winapi, 'TerminateProcess', side_effect=OSError('synthetic')):
            with self.assertRaises(target.LaunchCleanupPending) as caught:
                self.spawn("from pathlib import Path; Path('escaped').write_text('bad')")
        owner = caught.exception.owner
        self.addCleanup(owner.stop)
        self.assertIsNone(owner.owned)
        self.assertFalse(owner.cleanup_confirmed)
        self.assertEqual(_winapi.WaitForSingleObject(owner.process, 0), 258)
        self.assertFalse((self.folder/'escaped').exists())
        owner.stop()
        self.assertTrue(owner.cleanup_confirmed)
        self.assertIsNone(owner.process)
        self.assertIsNone(owner.job)
        self.assertFalse((self.folder/'escaped').exists())


class UnsupportedBackendTests(unittest.TestCase):
    def test_no_unsafe_non_windows_fallback(self):
        with patch.object(target.os, 'name', 'posix'):
            with self.assertRaisesRegex(Invalid, 'Windows Job Object'):
                target.spawn_studio_child(['python'], '.', {}, 'out', 'err', 100)
