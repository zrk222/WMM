"""Per-intent nonblocking process locks for external paid-operation ownership."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import threading
import weakref
from .common import Invalid

_LOCAL_LOCKS = weakref.WeakValueDictionary()
_LOCAL_LOCKS_GUARD = threading.Lock()


def _local_lock(key):
    with _LOCAL_LOCKS_GUARD:
        lock = _LOCAL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock();_LOCAL_LOCKS[key] = lock
        return lock


class CampaignLockBusy(Invalid):
    """The current process or another process still owns this operation."""


def _directory(store):
    base = Path(store.path).parent.resolve()
    directory = base / '.campaign-locks'
    if directory.is_symlink():raise Invalid('Campaign lock storage is linked')
    try:directory.mkdir(mode=0o700, exist_ok=True)
    except OSError:raise Invalid('Campaign lock storage is unavailable') from None
    if directory.is_symlink() or directory.resolve() != directory or not directory.is_dir():
        raise Invalid('Campaign lock storage is not the expected private directory')
    return directory


def _lock_file(store, app_id, intent_id):
    key = hashlib.sha256((str(Path(store.path).resolve())+'\0'+app_id+'\0'+intent_id).encode()).hexdigest()
    path = _directory(store) / (key + '.lock')
    if path.is_symlink() or path.parent.resolve() != _directory(store):
        raise Invalid('Campaign lock path changed')
    return key, path


def _acquire(fd):
    if os.name == 'nt':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(fd):
    if os.name == 'nt':
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def paid_lock(store, app_id, intent_id):
    """Hold an OS lock until the exact mutation receipt or a read-only recovery."""
    key, path = _lock_file(store, app_id, intent_id)
    local_lock = _local_lock(key)
    if not local_lock.acquire(blocking=False):raise CampaignLockBusy('Campaign operation is still in progress')
    fd = None; locked = False
    try:
        flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
        try:fd = os.open(str(path), flags, 0o600)
        except OSError:raise Invalid('Campaign lock storage is unavailable') from None
        if path.is_symlink() or path.resolve().parent != path.parent.resolve():
            raise Invalid('Campaign lock path changed')
        if os.fstat(fd).st_size == 0:os.write(fd, b'0')
        try:
            _acquire(fd);locked = True
        except OSError:
            raise CampaignLockBusy('Campaign operation is still in progress') from None
        yield
    finally:
        if locked:
            try:_release(fd)
            except OSError:pass
        if fd is not None:os.close(fd)
        local_lock.release()
