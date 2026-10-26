"""Bounded read-only Linux listener witnesses; no launch, stop or backend selection."""
from contextlib import ExitStack
import ctypes
import math
import os
import re
import secrets
import select
import socket
import stat
import struct
import sys
import time
from .common import Invalid

MAX_BYTES=1048576
MAX_MESSAGES=8192
MAX_TASKS=4096
MAX_FDS=4096
MAX_LINKS=32768
MAX_READ=65536
MAX_DATAGRAM=65536


def fail(code):
    """Expose closed public failure codes rather than kernel paths or task data."""
    raise Invalid('LISTENER_'+code)


def remaining(deadline):
    """One monotonic deadline governs every bounded observation loop."""
    value=deadline-time.monotonic()
    if value<=0:fail('DEADLINE')
    return value


def filesystem(fd, magic):
    """Require a real kernel filesystem; directory names alone grant no authority."""
    libc=ctypes.CDLL(None,use_errno=True);fn=libc.fstatfs
    fn.argtypes=(ctypes.c_int,ctypes.c_void_p);fn.restype=ctypes.c_int
    data=ctypes.create_string_buffer(256)
    if fn(fd,data)!=0 or ctypes.c_long.from_buffer(data).value!=magic:fail('FILESYSTEM')


def directory(parent, name, stack):
    """Open a fixed child directory without following a substituted symlink."""
    fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
    stack.callback(os.close,fd)
    return fd


def read_file(parent, name, deadline):
    """Read finite proc/cgroup bytes with descriptor cleanup on every branch."""
    remaining(deadline)
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=parent)
    try:
        result=bytearray()
        while True:
            remaining(deadline);chunk=os.read(fd,MAX_READ+1-len(result))
            if not chunk:return bytes(result)
            result.extend(chunk)
            if len(result)>MAX_READ:fail('READ_BOUND')
    finally:os.close(fd)


def live(pidfd):
    """A pidfd must remain non-readable; numeric PID reuse cannot revive it."""
    poller=select.poll();poller.register(pidfd,select.POLLIN|select.POLLHUP|select.POLLERR)
    return not poller.poll(0)


class RetainedCgroup:
    """Internal fd/callback capability supplied by the future live service owner."""
    def __init__(self, directory_fd, owner_alive):
        self._fd=None;self._owner_alive=owner_alive
        if sys.platform!='linux' or type(directory_fd) is not int or not callable(owner_alive):fail('SCOPE')
        try:
            self._fd=os.dup(directory_fd);os.set_inheritable(self._fd,False)
            value=os.fstat(self._fd)
            if not stat.S_ISDIR(value.st_mode):fail('SCOPE')
            self._identity=(value.st_dev,value.st_ino);self.validate()
        except Exception as error:
            self.close()
            if isinstance(error,Invalid):raise
            fail('SCOPE_UNAVAILABLE')
        except BaseException:
            self.close();raise

    def validate(self):
        """Revalidate both retained directory identity and current owner authority."""
        if self._fd is None:fail('SCOPE_CLOSED')
        try:allowed=self._owner_alive()
        except Exception:fail('SCOPE_UNAVAILABLE')
        if allowed is not True:fail('SCOPE_REVOKED')
        value=os.fstat(self._fd)
        if (value.st_dev,value.st_ino)!=self._identity:fail('SCOPE_CHANGED')
        filesystem(self._fd,0x63677270)

    def members(self, deadline):
        """Read exact live members from the retained cgroup, never a saved path/PID."""
        self.validate();remaining(deadline)
        if read_file(self._fd,'cgroup.type',deadline)!=b'domain\n':fail('CGROUP_TYPE')
        raw=read_file(self._fd,'cgroup.procs',deadline);rows=raw.splitlines()
        if len(rows)>MAX_TASKS:fail('TASK_BOUND')
        if any(not re.fullmatch(rb'[1-9][0-9]{0,9}',row) for row in rows):fail('MEMBERS')
        values=tuple(sorted(int(row) for row in rows))
        if len(set(values))!=len(values):fail('MEMBERS')
        self.validate();remaining(deadline);return values

    def close(self):
        """Release only our duplicate; the service owner retains its original fd."""
        if self._fd is not None:
            fd=self._fd;self._fd=None;os.close(fd)


def messages(data, sequence, recipient):
    """Validate complete aligned netlink framing before interpreting payloads."""
    offset=0;result=[]
    while offset<len(data):
        if len(data)-offset<16:fail('NETLINK_FRAME')
        size,kind,flags,seq,pid=struct.unpack_from('=IHHII',data,offset)
        if size<16 or offset+size>len(data):fail('NETLINK_FRAME')
        if seq!=sequence or pid not in (0,recipient) or flags&0x10:fail('NETLINK_IDENTITY')
        aligned=(size+3)&~3
        if offset+aligned>len(data):fail('NETLINK_FRAME')
        result.append((kind,data[offset+16:offset+size]));offset+=aligned
    return result


def attributes(raw):
    """Reject malformed extension attributes while allowing kernel-added fields."""
    offset=0
    while offset<len(raw):
        if len(raw)-offset<4:fail('DIAG_ATTRIBUTE')
        size=struct.unpack_from('=H',raw,offset)[0]
        if size<4 or offset+size>len(raw):fail('DIAG_ATTRIBUTE')
        offset+=(size+3)&~3
        if offset>len(raw):fail('DIAG_ATTRIBUTE')


def diag_row(raw):
    """Decode IPv4 TCP LISTEN records and retain the kernel socket cookie."""
    if len(raw)<72 or raw[0]!=socket.AF_INET or raw[1]!=10:fail('DIAG_ROW')
    attributes(raw[72:])
    if raw[12:24]!=bytes(12) or raw[6:8]!=bytes(2) or raw[24:40]!=bytes(16):fail('DIAG_ROW')
    port=struct.unpack_from('!H',raw,4)[0];inode=struct.unpack_from('=I',raw,68)[0]
    cookie=struct.unpack_from('=II',raw,44)
    return (raw[8:12],port,inode,cookie)


def diag_request(sequence):
    """Request a fresh IPv4 TCP LISTEN dump from the kernel only."""
    body=struct.pack('=BBBBI',socket.AF_INET,socket.IPPROTO_TCP,0,0,1<<10)+bytes(40)+b'\xff'*8
    return struct.pack('=IHHII',16+len(body),20,0x301,sequence,0)+body


def consume(rows, matches, port):
    """Require clean completion; ambiguous endpoint rows cannot yield a witness."""
    done=False
    for kind,body in rows:
        if done:fail('NETLINK_AFTER_DONE')
        if kind==3:
            if body not in (b'',bytes(4)):fail('NETLINK_DONE')
            done=True
        elif kind==20:
            row=diag_row(body)
            if row[0]==socket.inet_aton('127.0.0.1') and row[1]==port:matches.append(row)
        else:fail('NETLINK_ERROR')
    return done


def receive_dump(stream, sequence, recipient, port, deadline, budget=None):
    """Require complete kernel output within byte/message/deadline budgets."""
    matches=[]
    if budget is None:budget=[0,0]
    while True:
        stream.settimeout(remaining(deadline));raw,_,flags,sender=stream.recvmsg(MAX_DATAGRAM)
        if flags or sender!=(0,0) or not raw:fail('NETLINK_RECEIVE')
        budget[0]+=len(raw)
        if budget[0]>MAX_BYTES:fail('DIAG_BYTE_BOUND')
        rows=messages(raw,sequence,recipient);budget[1]+=len(rows)
        if budget[1]>MAX_MESSAGES:fail('DIAG_MESSAGE_BOUND')
        if consume(rows,matches,port):return matches


def diagnostic(port, deadline, budget=None):
    """Own and close one kernel-only netlink request socket per observation."""
    sequence=secrets.randbits(32) or 1
    with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,4) as stream:
        stream.settimeout(remaining(deadline));stream.bind((0,0));recipient=stream.getsockname()[0]
        request=diag_request(sequence)
        if stream.sendto(request,(0,0))!=len(request):fail('NETLINK_SEND')
        matches=receive_dump(stream,sequence,recipient,port,deadline,budget)
    if len(matches)!=1:return None
    if not matches[0][2] or matches[0][3]==(0xffffffff,0xffffffff):fail('SOCKET_IDENTITY')
    return matches[0]


def holds(directory_fd, inode, deadline, budget):
    """Inspect only required member fd links, bounded across the observation."""
    found=False;count=0
    with os.scandir(directory_fd) as entries:
        for entry in entries:
            remaining(deadline);count+=1;budget[0]+=1
            if count>MAX_FDS or budget[0]>MAX_LINKS:fail('FD_BOUND')
            if not entry.name.isdecimal():fail('FD_ENTRY')
            value=os.readlink(entry.name,dir_fd=directory_fd)
            if len(value)>4096:fail('FD_LINK_BOUND')
            if value=='socket:['+str(inode)+']':found=True
    return found


def holder(proc, pid, inode, deadline, budget):
    """Pin a task before reading its proc directory and retain only a live holder."""
    try:pin=os.pidfd_open(pid,0)
    except ProcessLookupError:return None
    result=None
    try:
        if not live(pin):return None
        with ExitStack() as stack:
            task=directory(proc,str(pid),stack);fds=directory(task,'fd',stack)
            if not holds(fds,inode,deadline,budget):return None
            group=read_file(task,'cgroup',deadline)
            if not re.fullmatch(rb'0::/[^\x00\n]*\n',group):fail('TASK_CGROUP')
        if live(pin):result=(pid,pin,group)
        return result
    finally:
        if result is None:os.close(pin)


def select_member(proc, members, row, deadline, preferred):
    """Inspect required members, retaining one chosen pidfd and closing the rest."""
    chosen=None;budget=[0]
    try:
        for pid in members:
            remaining(deadline);item=holder(proc,pid,row[2],deadline,budget)
            if item is None:continue
            if chosen is None and (preferred is None or pid==preferred):chosen=item
            else:os.close(item[1])
        return chosen
    except BaseException:
        if chosen is not None:os.close(chosen[1])
        raise


def witness(scope, row, deadline, preferred=None):
    """Choose one stable live scoped holder; inherited same-scope holders are valid."""
    members=scope.members(deadline);chosen=None
    try:
        with ExitStack() as stack:
            proc=directory(None,'/proc',stack);filesystem(proc,0x9fa0)
            chosen=select_member(proc,members,row,deadline,preferred)
        if chosen is not None and chosen[0] not in scope.members(deadline):
            os.close(chosen[1]);chosen=None
        return chosen
    except BaseException:
        if chosen is not None:os.close(chosen[1])
        raise


def observed(scope, port, deadline):
    """Retain the first pidfd across the second kernel and membership observation."""
    budget=[0,0];first_row=diagnostic(port,deadline,budget)
    if first_row is None:return False
    first=witness(scope,first_row,deadline)
    if first is None:return False
    try:
        if not live(first[1]) or diagnostic(port,deadline,budget)!=first_row:return False
        second=witness(scope,first_row,deadline,first[0])
        if second is None:return False
        try:
            remaining(deadline)
            result=first[0]==second[0] and first[2]==second[2] and live(first[1]) and live(second[1]) and first[0] in scope.members(deadline)
        finally:os.close(second[1])
    finally:os.close(first[1])
    remaining(deadline)
    return result


def request_deadline(scope, port, timeout):
    """Validate closed component inputs before any kernel observation."""
    if not isinstance(scope,RetainedCgroup) or type(port) is not int or not 1<=port<=65535:fail('INPUT')
    if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=2:fail('DEADLINE_INPUT')
    return time.monotonic()+timeout


def owns_listener(scope, port, timeout=1.0):
    """Component observation only; true is neither exclusive ownership nor a TCP lease."""
    if sys.platform!='linux' or not hasattr(os,'pidfd_open'):fail('UNSUPPORTED')
    deadline=request_deadline(scope,port,timeout)
    try:
        scope.validate()
        result=observed(scope,port,deadline)
        remaining(deadline)
        return result
    except Invalid:raise
    except (OSError,ValueError,AttributeError):fail('INSPECTION_UNAVAILABLE')
