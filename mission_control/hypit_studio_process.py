"""Owned private Studio process; public app/grant admission belongs to its caller."""
import json
import os
from pathlib import Path
import socket
import time
from urllib.parse import urlsplit
from urllib.error import HTTPError,URLError
from .common import Invalid,canonical
from .agent_process import environment
from .studio_command import capture_owned_command,retry_cleanup
from .studio_child import spawn_studio_child,LaunchCleanupPending
from .hypit_installation import revalidate,plain
from .hypit_runtime import local_graph
from .hypit_studio_project import sources_current,local_profile,snapshot_current,cleanup_current,runtime_directory,compiled_current
from .hypit_studio_http import session_bytes

STARTUP_SECONDS=45
HTTP_SECONDS=2
COMMAND_SECONDS=120
MAX_RESPONSE_BYTES=8388608
MAX_LOG_BYTES=1048576
POLL_SECONDS=.25
MAX_DIAGNOSTIC_BYTES=8388608


class StudioProcess:
    """Never restore process authority from persisted PID, URL or caller argv."""
    def __init__(self,folder,installation,sources,compiled,alive):
        self.folder=Path(folder).absolute();self.installation=dict(installation);self.sources=dict(sources)
        self.alive=alive;self.process=None;self.origin=None
        self.control=self.folder/'.wmm-studio-control';self.admitted=False;self.state='NEW'
        self.closed=False;self.cleanup_receipt=None
        self.launch_recovery=None
        self.compiled=json.loads(canonical(compiled));self.runtime_identity=None
        self.control_identity=None;self.command_diagnostics={}

    def write_control(self,name,value):
        """Write bounded private records atomically without following control links."""
        if name not in ('state','command-plan','command-cleanup'):
            raise Invalid('Studio private record name is unsupported')
        plain(self.folder,directory=True);info=plain(self.control,directory=True)
        if (info.st_dev,info.st_ino)!=self.control_identity:
            raise Invalid('Studio private control directory changed')
        raw=canonical(value).encode()
        if len(raw)>MAX_DIAGNOSTIC_BYTES:raise Invalid('Studio private diagnostic exceeds its bound')
        temporary=self.control/(name+'.tmp')
        with temporary.open('xb') as stream:stream.write(raw)
        temporary.replace(self.control/(name+'.json'))

    def record(self,state):
        self.state=state
        if self.control_identity is not None:
            value=dict(state=state,installation_id=self.installation['id'],sources=self.sources,
                       pid=self.process.pid if self.process is not None else None,
                       pid_is_diagnostic_only=True,runtime_identity=self.runtime_identity,compiled=self.compiled)
            value['child_overflow']=self.process.overflow if self.process is not None else False
            value['child_failure']=self.process.failure if self.process is not None else None
            self.write_control('state',value)

    def retain_command(self,phase,value):
        if phase not in ('plan','cleanup'):raise Invalid('Studio command phase is unsupported')
        self.command_diagnostics[phase]=dict(value)
        self.write_control('command-'+phase,value)

    def command(self,args,cleanup=False):
        argv=[self.installation['node'],'--dns-result-order=ipv4first',self.installation['entrypoint'],*args,'--json']
        phase='cleanup' if cleanup else 'plan'
        try:
            result=capture_owned_command(argv,folder=self.folder,timeout=COMMAND_SECONDS,extra_env=self.extra(),
                alive=(lambda:None) if cleanup else self.alive,
                diagnostics=lambda value:self.retain_command(phase,value))
        except Exception as error:
            value=dict(self.command_diagnostics.get(phase,{}),capture_failure=type(error).__name__,message=str(error)[:4096])
            self.retain_command(phase,value)
            raise
        self.retain_command(phase,dict(self.command_diagnostics.get(phase,{}),**result))
        if result['code']:raise Invalid('Studio local command failed; inspect retained diagnostics')
        try:value=json.loads(result['stdout'])
        except ValueError:raise Invalid('Studio local command returned unsupported data') from None
        if not isinstance(value,dict):raise Invalid('Studio local command receipt is unsupported')
        return value

    def extra(self):
        return {'PATHEXT':'.EXE;.CMD;.BAT;.COM'} if os.name=='nt' else {}

    def current(self):
        self.alive();sources_current(self.folder,self.sources);local_profile(self.folder)
        compiled_current(self.folder,self.sources,self.compiled)
        if self.runtime_identity is not None:runtime_directory(self.folder,self.runtime_identity)

    def logs_current(self):
        if self.process is not None and self.process.overflow:
            raise Invalid('Studio diagnostics exceeded their bound; its owned child tree was stopped')
        if self.process is not None and self.process.failure:
            raise Invalid('Studio output capture failed; inspect retained private diagnostics')
        if sum((self.control/name).stat().st_size for name in ('stdout.log','stderr.log'))>MAX_LOG_BYTES:
            raise Invalid('Studio diagnostics exceeded their bound')

    def read(self,deadline=None):
        self.current()
        if self.process is None or self.process.poll() is not None:
            self.record('NEEDS_INSPECTION')
            raise Invalid('Owned Studio is no longer running; inspect before restarting')
        self.logs_current()
        if not self.process.owns_listener(urlsplit(self.origin).port):
            raise URLError('Studio listener is not owned by the admitted child job')
        deadline=min(deadline or float('inf'),time.monotonic()+HTTP_SECONDS)
        raw=session_bytes(self.origin,self.check_read,deadline,MAX_RESPONSE_BYTES)
        try:value=json.loads(raw)
        except ValueError:raise Invalid('Studio returned invalid session data') from None
        self.current();self.logs_current()
        if self.process.poll() is not None:raise Invalid('Owned Studio exited during observation')
        if not self.process.owns_listener(urlsplit(self.origin).port):
            raise Invalid('Studio listener ownership changed during observation')
        return snapshot_current(self.folder,self.sources,self.compiled,value)

    def check_read(self):
        self.current();self.logs_current()

    def launch(self):
        with socket.socket() as address:
            address.bind(('127.0.0.1',0));port=address.getsockname()[1]
        self.origin='http://127.0.0.1:'+str(port)
        argv=[self.installation['node'],'--dns-result-order=ipv4first',self.installation['entrypoint'],
              'studio','--run','build.svrun','--runtime','runtime.json','--project',str(self.folder),'--port',str(port)]
        try:
            self.process=spawn_studio_child(argv,folder=self.folder,env=environment(self.extra()),
                stdout_path=self.control/'stdout.log',stderr_path=self.control/'stderr.log',max_log_bytes=MAX_LOG_BYTES)
        except LaunchCleanupPending as error:
            self.launch_recovery=error.owner
            raise
        self.record('STARTING')

    def observe_start(self):
        deadline=time.monotonic()+STARTUP_SECONDS
        while time.monotonic()<deadline:
            try:return self.read(deadline=deadline)
            except HTTPError as error:
                if error.code!=409:raise Invalid('Studio compilation failed; inspect retained diagnostics') from None
            except (URLError,TimeoutError):pass
            self.current();time.sleep(POLL_SECONDS)
        raise Invalid('Studio startup observation expired; inspect the retained attempt')

    def start(self):
        if self.state!='NEW' or self.control.exists():
            raise Invalid('A Studio attempt already exists; inspect it without resubmitting')
        self.current();revalidate(self.installation);self.current()
        self.control.mkdir(exist_ok=False)
        info=plain(self.control,directory=True);self.control_identity=(info.st_dev,info.st_ino)
        self.record('STARTING')
        try:
            self.runtime_identity=runtime_directory(self.folder,create=True);self.admitted=True
            local_graph(self.command(['plan','build.svrun','--runtime','runtime.json']))
            revalidate(self.installation);self.current()
            self.launch();value=self.observe_start();self.record('READY')
            return value
        except Exception:
            try:self.close();self.record('FAILED_CLEANED')
            except Exception:self.record('NEEDS_INSPECTION')
            raise

    def close(self):
        """Revocation cannot prevent cleanup of already-owned work."""
        if self.closed:return self.cleanup_receipt
        try:
            if self.process is not None:self.process.stop()
            if self.launch_recovery is not None:
                self.launch_recovery.stop();self.launch_recovery=None
            self.cleanup_commands()
            if self.admitted:
                revalidate(self.installation)
                cleanup_current(self.folder,self.sources,self.runtime_identity)
                value=self.command(['runtime','down','--runtime','runtime.json'],cleanup=True)
                if value.get('worker')!='stopped':raise Invalid('Studio private runtime shutdown is unconfirmed')
                self.cleanup_receipt=value
            self.cleanup_commands()
            self.record('CLOSED')
            self.closed=True
            return self.cleanup_receipt
        except Exception:
            self.record('NEEDS_INSPECTION');raise

    def cleanup_commands(self):
        """Unconfirmed preflight/down descendants belong to this attempt too."""
        for phase,value in list(self.command_diagnostics.items()):
            if value.get('recovery_id') and value.get('tree_stopped') is not True:
                result=retry_cleanup(value['recovery_id'])
                if result.get('tree_stopped') is not True:
                    raise Invalid('Studio command tree cleanup is still unconfirmed')
                self.retain_command(phase,dict(value,tree_stopped=True,cleanup_failure=None,recovered=True))
