"""Actual offline container primitives only; NOT native systemd/desktop acceptance."""
import json
import os
import platform
import socket
from mission_control.common import Invalid
from mission_control.studio_listener_linux import RetainedCgroup, owns_listener, live

fd=os.open('/sys/fs/cgroup',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
active=[True];scope=RetainedCgroup(fd,lambda:active[0]);os.close(fd)
results=dict(profile='OFFLINE_UBUNTU_CONTAINER_COMPONENT_ONLY',kernel=platform.release(),python=platform.python_version(),
             distribution=platform.freedesktop_os_release().get('PRETTY_NAME'),
             unit_containment='NOT_RUN',desktop_support='NOT_RUN',cgroup_source='CONTAINER_ROOT_NOT_TRANSIENT_UNIT')
try:
    with socket.socket() as source:
        source.bind(('127.0.0.1',0));source.listen();port=source.getsockname()[1]
        before=len(os.listdir('/proc/self/fd'))
        results['exact_listener']=owns_listener(scope,port,2)
        reader,writer=os.pipe();pid=os.fork()
        if pid==0:
            os.close(writer);os.read(reader,1);os.close(reader);os._exit(0)
        os.close(reader);pin=os.pidfd_open(pid,0)
        try:
            results['inherited_same_scope_holder']=owns_listener(scope,port,2)
        finally:
            os.write(writer,b'x');os.close(writer);os.waitpid(pid,0)
        results['exited_pidfd_not_live']=not live(pin);os.close(pin)
        for _ in range(3):assert owns_listener(scope,port,2)
        results['inspection_fd_count_preserved']=len(os.listdir('/proc/self/fd'))==before
        active[0]=False
        try:owns_listener(scope,port,2)
        except Invalid as error:results['revoked_scope_denied']=str(error)=='LISTENER_SCOPE_REVOKED'
        active[0]=True
    results['closed_listener_unowned']=not owns_listener(scope,port,2)
    with socket.socket() as wildcard:
        wildcard.bind(('0.0.0.0',0));wildcard.listen()
        results['wildcard_unowned']=not owns_listener(scope,wildcard.getsockname()[1],2)
    other=os.open('/workspace',os.O_RDONLY|os.O_DIRECTORY)
    try:
        try:RetainedCgroup(other,lambda:True)
        except Invalid as error:results['non_cgroup_filesystem_denied']=str(error)=='LISTENER_FILESYSTEM'
    finally:os.close(other)
finally:scope.close()
print(json.dumps(results,sort_keys=True))
assert all(value is True for value in results.values() if isinstance(value,bool))
