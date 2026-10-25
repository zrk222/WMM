"""Opt-in synchronous Studio commands with retained native tree ownership."""
import shutil
import tempfile
import time
from pathlib import Path
from .agent_process import CAP,environment
from .common import Invalid
from .studio_child import spawn_studio_child,LaunchCleanupPending

PENDING_CLEANUP={}


def observe(child,alive,deadline):
    """Launcher exit is followed by mandatory job teardown, not abandonment."""
    while child.poll() is None:
        alive()
        if child.overflow:raise Invalid('Studio command output exceeded its bound')
        if child.failure:raise Invalid('Studio command output capture failed')
        if time.monotonic()>=deadline:raise Invalid('Studio command observation timed out')
        time.sleep(.025)
    alive()
    return child.poll()


def output_snapshot(folder,code,finished,primary,cleanup,child):
    """Copy only bounded diagnostics after tree termination or an explicit failure."""
    value=dict(code=code,interrupted=not finished,command_failure=primary,
               cleanup_failure=cleanup,tree_stopped=cleanup is None,
               overflow=bool(child and child.overflow),capture_failure=bool(child and child.failure))
    value['recovery_id']=folder.name if cleanup is not None else None
    for name in ('stdout','stderr'):
        path=folder/(name+'.log')
        if path.is_file():
            with path.open('rb') as stream:raw=stream.read(CAP)
        else:raw=b''
        value[name]=raw.decode('utf-8',errors='replace')
    return value


def deliver(diagnostics,value,folder):
    """Diagnostic callback failure cannot erase unconfirmed teardown state."""
    try:
        if diagnostics is not None:diagnostics(value)
    except Exception as error:
        raise Invalid('Studio command diagnostics could not be retained; private capture kept for inspection') from error
    if value['cleanup_failure'] is not None:
        raise Invalid('Studio command tree cleanup is unconfirmed; private capture kept for inspection')
    if value['command_failure'] is not None:
        raise Invalid('Studio command failed: '+value['command_failure'])
    if value['overflow']:raise Invalid('Studio command output exceeded its bound')
    if value['capture_failure']:raise Invalid('Studio command output capture failed')
    return dict(code=value['code'],stdout=value['stdout'],stderr=value['stderr'])


def capture_owned_command(args,alive=lambda:None,timeout=120,folder=None,extra_env=None,diagnostics=None):
    """No stdin or daemon lifetime: only explicitly synchronous command callers."""
    if type(timeout) not in (int,float) or not 1<=timeout<=180:
        raise Invalid('Studio command deadline must be between 1 and 180 seconds')
    private=Path(tempfile.mkdtemp(prefix='wmm-studio-command-'))
    child=None;code=None;finished=False;primary=None;cleanup=None
    try:
        alive()
        child=spawn_studio_child(args,folder=folder or private,env=environment(extra_env),
            stdout_path=private/'stdout.log',stderr_path=private/'stderr.log',max_log_bytes=CAP)
        code=observe(child,alive,time.monotonic()+timeout);finished=True
    except LaunchCleanupPending as error:
        primary=type(error).__name__;child=error.owner;cleanup=type(error).__name__
        PENDING_CLEANUP[private.name]=(child,private)
    except Exception as error:
        primary=type(error).__name__
    finally:
        if child is not None and cleanup is None:
            try:child.stop()
            except Exception as error:
                cleanup=type(error).__name__;PENDING_CLEANUP[private.name]=(child,private)
    value=recovery_snapshot(private,code,finished,primary,cleanup,child)
    result=deliver(diagnostics,value,private)
    shutil.rmtree(private)
    return result


def recovery_snapshot(private,code,finished,primary,cleanup,child):
    """Publish cleanup metadata even when optional diagnostic bytes cannot be read."""
    try:return output_snapshot(private,code,finished,primary,cleanup,child)
    except Exception as error:
        return dict(code=code,interrupted=not finished,command_failure=primary or type(error).__name__,
            cleanup_failure=cleanup,tree_stopped=cleanup is None,
            recovery_id=private.name if cleanup is not None else None,
            stdout='',stderr='',diagnostic_read_failure=type(error).__name__,
            overflow=bool(child and child.overflow),capture_failure=bool(child and child.failure))


def retry_cleanup(recovery_id):
    """Use retained live Job authority only; never recover a saved numeric PID."""
    if recovery_id not in PENDING_CLEANUP:raise Invalid('Owned command cleanup handle is unavailable')
    child,private=PENDING_CLEANUP[recovery_id]
    child.stop()
    del PENDING_CLEANUP[recovery_id]
    return dict(tree_stopped=True,recovery_id=recovery_id,diagnostics_retained=True)
