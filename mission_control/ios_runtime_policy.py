"""Reject desktop process routes inside the trusted bundled iOS interpreter.

This is an operational guard, not a sandbox for hostile Python/native code.
Only signed bundled code belongs in this interpreter; iOS remains the OS boundary.
Importing this module on a desktop does not install a hook.
"""
import sys

_active = False
_PROBE = 'wmm.ios.process_policy_probe'
_PROCESS_EVENTS = frozenset({
    'subprocess.Popen', '_posixsubprocess.fork_exec', 'os.system',
    'os.exec', 'os.posix_spawn', 'os.spawn', 'os.fork', 'os.forkpty',
    'os.startfile', 'os.startfile/2',
})


def _deny_process(event, args):
    if event in _PROCESS_EVENTS or event == _PROBE:
        # Never interpolate argv, environment or paths: these may contain secrets.
        raise PermissionError('Desktop process execution is unavailable in WMM iOS.')


def activate():
    """Install once on iOS, proving registration before permitting engine startup."""
    global _active
    if sys.platform != 'ios':
        raise RuntimeError('The WMM iOS runtime policy requires iOS.')
    if not _active:
        sys.addaudithook(_deny_process)
        # addaudithook may silently refuse registration if another hook rejects it.
        try:
            sys.audit(_PROBE)
        except PermissionError:
            _active = True
        else:
            raise RuntimeError('WMM iOS process policy did not activate.')

