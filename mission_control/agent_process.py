"""Bounded owned CLI processes; no shell expansion or inherited provider keys."""
import os,subprocess,tempfile,time
from pathlib import Path
from .common import Invalid
from .audit_tools import stop_owned

CAP=1048576


def environment(extra=None):
    """Official clients retain their own login stores; unrelated tokens are excluded."""
    names=('SYSTEMROOT','WINDIR','TEMP','TMP','LOCALAPPDATA','APPDATA','USERPROFILE','HOME','PATH','PROGRAMFILES')
    result={key:os.environ[key] for key in names if key in os.environ}
    result.update(extra or {})
    return result


def wait(process,output,error,alive,timeout):
    """Bound wall time, cancellation and file growth, including a stalled child."""
    deadline=time.monotonic()+timeout
    while process.poll() is None:
        alive()
        if time.monotonic()>deadline:raise Invalid('Agent timed out; quota may have been consumed. Review before retrying')
        if output.stat().st_size+error.stat().st_size>CAP:raise Invalid('Agent output exceeded its bounded size')
        time.sleep(.05)
    alive()
    if output.stat().st_size+error.stat().st_size>CAP:raise Invalid('Agent output exceeded its bounded size')


def capture(args,input_text='',alive=lambda:None,timeout=120,folder=None,extra_env=None):
    """Use preopened files so a child that never reads stdin cannot block the parent."""
    if not 1<=timeout<=180 or len(input_text.encode())>32768:raise Invalid('Agent input or deadline exceeds its limit')
    with tempfile.TemporaryDirectory(prefix='growth-agent-owned-') as temporary:
        root=Path(folder) if folder else Path(temporary)
        output,error,source=(Path(temporary)/name for name in ('output','error','input'))
        source.write_text(input_text,encoding='utf-8')
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        with source.open('rb') as stdin,output.open('wb') as stdout,error.open('wb') as stderr:
            process=subprocess.Popen(args,cwd=root,env=environment(extra_env),stdin=stdin,stdout=stdout,
                stderr=stderr,shell=False,creationflags=flags,start_new_session=os.name!='nt')
            try:
                wait(process,output,error,alive,timeout)
                code=process.returncode
            finally:stop_owned(process)
        return dict(code=code,stdout=output.read_text(encoding='utf-8',errors='replace'),
                    stderr=error.read_text(encoding='utf-8',errors='replace'))


def failure(value):
    """Classify operational recovery without exporting raw CLI diagnostics or credentials."""
    text=(value['stderr']+' '+value['stdout']).lower()
    if any(word in text for word in ('rate limit','quota','usage limit','limit reached')):
        return 'Agent allowance is exhausted or rate-limited; wait for reset or approve another connection'
    if any(word in text for word in ('login','log in','sign in','authentication','unauthorized','401','403')):
        return 'Agent sign-in or permission needs attention; reconnect the official account and test again'
    return 'Agent execution did not return an accepted result; review tool version and connection before retrying'
