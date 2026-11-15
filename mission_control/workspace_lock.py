"""Nonblocking operating-system lock for a local workspace lifetime."""

import errno
import os
from pathlib import Path


class WorkspaceBusy(RuntimeError):
    """Another desktop or headless runtime owns this workspace."""


class WorkspaceLock:
    def __init__(self, directory):
        self.path = Path(directory).resolve() / ".wmm-runtime.lock"
        self.file = None

    def acquire(self):
        if self.file is not None:
            raise RuntimeError("Workspace lock already held")
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        file = os.fdopen(fd, "r+b", buffering=0)
        locked = False
        try:
            if os.name == "nt":
                import msvcrt

                if os.fstat(fd).st_size == 0:
                    file.write(b"0")
                file.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as error:
            if error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK, 13, 36):
                raise WorkspaceBusy("Workspace is already running") from None
            raise
        finally:
            if not locked:
                file.close()
        self.file = file

    def release(self):
        file, self.file = self.file, None
        if file is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
        finally:
            file.close()
