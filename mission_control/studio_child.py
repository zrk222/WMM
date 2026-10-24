"""Windows owned process tree and continuously bounded private diagnostics.

Authority is an unnamed, non-inheritable Job handle, never a recorded PID.
The initial thread is resumed only after assignment; breakaway is not enabled.
See Microsoft Job Objects / AssignProcessToJobObject / TerminateJobObject docs.
"""
import ctypes
from ctypes import wintypes as w
import os
from pathlib import Path
import subprocess
import socket
import threading
import time

from .common import Invalid

STOP_SECONDS = 10


class _Limits(ctypes.Structure):
    _fields_ = [('times', ctypes.c_int64 * 2), ('flags', w.DWORD),
                ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t),
                ('count', w.DWORD), ('affinity', ctypes.c_size_t),
                ('priority', w.DWORD), ('scheduling', w.DWORD)]


class _Extended(ctypes.Structure):
    _fields_ = [('basic', _Limits), ('io', ctypes.c_uint64 * 6),
                ('memory', ctypes.c_size_t * 4)]


class _Accounting(ctypes.Structure):
    _fields_ = [('times', ctypes.c_int64 * 4), ('faults', w.DWORD),
                ('total', w.DWORD), ('active', w.DWORD), ('terminated', w.DWORD)]


def _native():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    for name, args, result in (
        ('CreateJobObjectW', [w.LPVOID, w.LPCWSTR], w.HANDLE),
        ('SetInformationJobObject', [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD], w.BOOL),
        ('AssignProcessToJobObject', [w.HANDLE, w.HANDLE], w.BOOL),
        ('TerminateJobObject', [w.HANDLE, w.UINT], w.BOOL),
        ('QueryInformationJobObject', [w.HANDLE, ctypes.c_int, w.LPVOID, w.DWORD, w.LPVOID], w.BOOL),
        ('ResumeThread', [w.HANDLE], w.DWORD),
        ('IsProcessInJob', [w.HANDLE, w.HANDLE, ctypes.POINTER(w.BOOL)], w.BOOL),
    ):
        fn = getattr(kernel, name)
        fn.argtypes, fn.restype = args, result
    return kernel


def _check(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


class _TcpRow(ctypes.Structure):
    _fields_ = [(name, w.DWORD) for name in
                ('state', 'address', 'port', 'remote_address', 'remote_port', 'pid')]


def _listener_rows():
    api = ctypes.WinDLL('iphlpapi', use_last_error=True).GetExtendedTcpTable
    api.argtypes = [w.LPVOID, ctypes.POINTER(w.DWORD), w.BOOL, w.ULONG, ctypes.c_int, w.ULONG]
    api.restype = w.DWORD
    size = w.DWORD(0)
    for _ in range(4):
        if size.value > 16 * 1024 * 1024:
            raise Invalid('Studio listener table exceeded inspection bound')
        data = ctypes.create_string_buffer(max(size.value, 4))
        status = api(data, ctypes.byref(size), False, 2, 3, 0)
        if status == 122:  # ERROR_INSUFFICIENT_BUFFER; table can grow between calls
            continue
        if status:
            raise ctypes.WinError(status)
        count = w.DWORD.from_buffer(data).value
        if 4 + count * ctypes.sizeof(_TcpRow) > len(data):
            raise Invalid('Studio listener table is malformed')
        return [_TcpRow.from_buffer_copy(data, 4 + i * ctypes.sizeof(_TcpRow)) for i in range(count)]
    raise Invalid('Studio listener table did not stabilize')


def _listener_pid(port):
    address = int.from_bytes(socket.inet_aton('127.0.0.1'), 'little')
    matches = [row.pid for row in _listener_rows()
               if row.state == 2 and row.address == address and socket.ntohs(row.port & 0xffff) == port]
    if len(matches) > 1:
        raise Invalid('Studio listener ownership is ambiguous')
    return matches[0] if matches else None


class StudioChild:
    def __init__(self, kernel, job, process, pid, cap):
        self._kernel, self._job, self._process = kernel, job, process
        self.pid, self._cap, self._written = pid, cap, 0
        self.overflow, self.failure = False, None
        self._budget = threading.Lock()
        self._authority = threading.RLock()
        self._stopping = threading.Lock()
        self._threads = []
        self._code = None

    def _failed(self, operation, error):
        # Exception messages can contain argv, paths or output; retain only class.
        with self._budget:
            if self.failure is None:
                self.failure = operation + ': ' + type(error).__name__

    def _terminate(self):
        with self._authority:
            if self._job is not None:
                _check(self._kernel.TerminateJobObject(self._job, 1))

    def _drain(self, source, output):
        try:
            with source, output:
                while True:
                    data = source.read(65536)
                    if not data:
                        break
                    with self._budget:
                        room = self._cap - self._written
                        retained = data[:room]
                        if retained:
                            # Reserve before I/O: even a partial failed write
                            # must not let the other pipe reuse these bytes.
                            self._written += len(retained)
                            count = output.write(retained)
                            if count != len(retained):
                                raise OSError('short diagnostic write')
                        exceeded = len(data) > room
                        self.overflow |= exceeded
                    if exceeded:
                        self._terminate()
        except Exception as error:
            self._failed('diagnostic capture', error)
            try:
                self._terminate()
            except Exception as stop_error:
                self._failed('automatic termination', stop_error)

    def poll(self):
        import _winapi
        with self._authority:
            if self._process is not None and _winapi.WaitForSingleObject(self._process, 0) == 0:
                self._code = _winapi.GetExitCodeProcess(self._process)
            return self._code

    def _active(self):
        info = _Accounting()
        _check(self._kernel.QueryInformationJobObject(
            self._job, 1, ctypes.byref(info), ctypes.sizeof(info), None))
        return info.active

    def owns_listener(self, port):
        """Observe a live exact loopback listener belonging to this retained job.

        The process handle pins identity across the second table observation.
        This is an observation, not an atomic lease on future TCP connections.
        """
        import _winapi
        if type(port) is not int or not 1 <= port <= 65535:
            raise Invalid('Studio listener port is invalid')
        with self._authority:
            if self._job is None:
                return False
            try:
                pid = _listener_pid(port)
                if pid is None:
                    return False
                handle = _winapi.OpenProcess(0x00101000, False, pid)
                try:
                    member = w.BOOL()
                    _check(self._kernel.IsProcessInJob(handle, self._job, ctypes.byref(member)))
                    return bool(member.value) and self._same_live_listener(handle, pid, port)
                finally:
                    _winapi.CloseHandle(handle)
            except Exception as error:
                raise Invalid('Owned Studio listener inspection failed') from error

    def _same_live_listener(self, handle, pid, port):
        import _winapi
        if _winapi.WaitForSingleObject(handle, 0) != 258:
            return False
        same = _listener_pid(port) == pid
        return same and _winapi.WaitForSingleObject(handle, 0) == 258

    def stop(self):
        """Confirm the whole job is empty before relinquishing process authority.

        A failure leaves handles owned so a later stop may retry. Diagnostic
        failure is exposed separately in failure; it never fabricates log success.
        """
        import _winapi
        with self._stopping:
            if self._job is None:
                return
            try:
                self._terminate()
                deadline = time.monotonic() + STOP_SECONDS
                while self._active():
                    if time.monotonic() >= deadline:
                        raise Invalid('Owned Studio tree termination was not confirmed')
                    time.sleep(.01)
                self._confirm_drained(deadline)
                with self._authority:
                    self.poll()
                    if self._process is not None:
                        _winapi.CloseHandle(self._process)
                        self._process = None
                    _winapi.CloseHandle(self._job)
                    self._job = None
            except Exception as error:
                self._failed('owned tree stop', error)
                raise Invalid('Owned Studio tree stop failed or is unconfirmed') from error

    def _confirm_drained(self,deadline):
        """A partially released process handle is already confirmed, not waitable."""
        import _winapi
        remaining=max(0,int((deadline-time.monotonic())*1000))
        if self._process is not None and _winapi.WaitForSingleObject(self._process,remaining)!=0:
            raise Invalid('Owned Studio launcher termination was not confirmed')
        for thread in self._threads:
            thread.join(max(0,deadline-time.monotonic()))
            if thread.is_alive():raise Invalid('Owned Studio diagnostic drain did not stop')


def _validate_launch(argv, max_log_bytes):
    """Launch without a shell; fail closed outside the Windows native backend.

    The caller supplies a private directory. Log files are exclusive new files;
    existing files/links are rejected. No ambient handles except the three
    explicit standard handles are passed to the child.
    """
    if os.name != 'nt':
        raise Invalid('Owned Studio trees require the Windows Job Object backend')
    if type(max_log_bytes) is not int or max_log_bytes < 1:
        raise Invalid('Studio diagnostic byte cap must be positive')
    if not isinstance(argv, (list, tuple)) or not argv or not all(isinstance(v, str) for v in argv):
        raise Invalid('Studio argv must be a nonempty string sequence')


class LaunchCleanupPending(Invalid):
    """Launch failed with retained native authority requiring an explicit retry."""
    def __init__(self, owner):
        super().__init__('Studio launch failed; owned cleanup requires retry')
        self.owner = owner
        self.cleanup_confirmed = False


class _Launch:
    """Resource ledger for suspended construction and rollback."""
    def __init__(self):
        self.kernel = _native()
        self.job = self.process = self.thread = self.owned = None
        self.streams, self.inherited = [], []
        self.pid = None
        self.failure = None
        self.cleanup_confirmed = False
        self._cleanup_lock = threading.Lock()

    @property
    def overflow(self):
        return self.owned.overflow if self.owned is not None else False

    def poll(self):
        import _winapi
        if self.owned is not None:
            return self.owned.poll()
        if self.process is not None and _winapi.WaitForSingleObject(self.process, 0) == 0:
            return _winapi.GetExitCodeProcess(self.process)
        return None

    def job_create(self):
        self.job = _check(self.kernel.CreateJobObjectW(None, None))
        limits = _Extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _check(self.kernel.SetInformationJobObject(self.job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))

    def pipes(self, stdout_path, stderr_path):
        import msvcrt
        outputs = []
        for path in (stdout_path, stderr_path):
            output = open(Path(path), 'xb', buffering=0)
            self.streams.append(output)
            outputs.append(output)
        reads, writes = [], []
        for _ in range(2):
            read_fd, write_fd = os.pipe()
            read = os.fdopen(read_fd, 'rb', buffering=0)
            write = os.fdopen(write_fd, 'wb', buffering=0)
            self.streams.extend((read, write))
            reads.append(read)
            writes.append(write)
        stdin = open(os.devnull, 'rb', buffering=0)
        self.streams.append(stdin)
        self.inherited = [msvcrt.get_osfhandle(s.fileno()) for s in (stdin, *writes)]
        return reads, outputs

    def reset_inheritance(self):
        while self.inherited:
            handle = self.inherited[-1]
            os.set_handle_inheritable(handle, False)
            self.inherited.pop()

    def close_streams(self):
        while self.streams:
            stream = self.streams[-1]
            stream.close()
            self.streams.pop()

    def create(self, argv, folder, env):
        import _winapi
        for handle in self.inherited:
            os.set_handle_inheritable(handle, True)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags = subprocess.STARTF_USESTDHANDLES
        startup.hStdInput, startup.hStdOutput, startup.hStdError = self.inherited
        startup.lpAttributeList = {'handle_list': self.inherited}
        self.process, self.thread, pid, _ = _winapi.CreateProcess(
            argv[0], subprocess.list2cmdline(argv), None, None, True,
            0x00000004 | 0x08000000, env, str(folder), startup)
        self.pid = pid
        self.reset_inheritance()
        _check(self.kernel.AssignProcessToJobObject(self.job, self.process))
        return pid

    def readers(self, reads, outputs):
        for read, output in zip(reads, outputs):
            worker = threading.Thread(target=self.owned._drain, args=(read, output), daemon=True)
            worker.start()
            self.owned._threads.append(worker)
            self.streams.remove(read)
            self.streams.remove(output)

    def resume(self):
        import _winapi
        if self.kernel.ResumeThread(self.thread) != 1:
            raise OSError('Initial Studio thread did not resume from suspended state')
        _winapi.CloseHandle(self.thread)
        self.thread = None

    def terminate_failed_launch(self):
        import _winapi
        if self.owned is not None:
            self.owned.stop()
            self.process = self.job = None
        elif self.process is not None:
            if _winapi.WaitForSingleObject(self.process, 0) != 0:
                _winapi.TerminateProcess(self.process, 1)
            if _winapi.WaitForSingleObject(self.process, 10000) != 0:
                raise Invalid('Failed Studio launch termination is unconfirmed')
        if self.job is not None:
            _check(self.kernel.TerminateJobObject(self.job, 1))
            self.confirm_empty_job()

    def confirm_empty_job(self):
        deadline = time.monotonic() + STOP_SECONDS
        info = _Accounting()
        while True:
            _check(self.kernel.QueryInformationJobObject(
                self.job, 1, ctypes.byref(info), ctypes.sizeof(info), None))
            if not info.active:
                return
            if time.monotonic() >= deadline:
                raise Invalid('Failed launch job termination is unconfirmed')
            time.sleep(.01)

    def close_confirmed_handles(self):
        import _winapi
        for name in ('thread', 'process', 'job'):
            handle = getattr(self, name)
            if handle is not None:
                _winapi.CloseHandle(handle)
                setattr(self, name, None)

    def stop(self):
        """Retry cleanup without giving up any unconfirmed native authority."""
        with self._cleanup_lock:
            if self.cleanup_confirmed:
                return
            try:
                self.reset_inheritance()
                self.close_streams()
                self.terminate_failed_launch()
                self.close_confirmed_handles()
            except Exception as error:
                self.failure = 'launch cleanup: ' + type(error).__name__
                raise LaunchCleanupPending(self) from error
            self.cleanup_confirmed = True

    def rollback(self):
        self.stop()


def spawn_studio_child(argv, folder, env, stdout_path, stderr_path, max_log_bytes):
    """Launch shell-free into a retained job with exclusive new private logs."""
    _validate_launch(argv, max_log_bytes)
    launch = _Launch()
    try:
        launch.job_create()
        reads, outputs = launch.pipes(stdout_path, stderr_path)
        pid = launch.create(argv, folder, env)
        launch.owned = StudioChild(launch.kernel, launch.job, launch.process, pid, max_log_bytes)
        launch.readers(reads, outputs)
        launch.resume()
        launch.reset_inheritance()
        launch.close_streams()
        return launch.owned
    except Exception as error:
        launch.rollback()
        raise Invalid('Owned Studio launch failed: ' + type(error).__name__) from error
