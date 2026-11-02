"""Terminal-free controller for the same private local WMM runtime."""
import errno
import json
import os
from pathlib import Path
import signal
import sys
import threading
import webbrowser


def data_directory(platform=None, environ=None, home=None):
    """Keep durable data outside the executable and its extracted resources."""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    home = Path.home() if home is None else Path(home)
    if platform == 'win32':
        base = Path(environ.get('LOCALAPPDATA') or home / 'AppData' / 'Local')
    elif platform == 'darwin':
        base = home / 'Library' / 'Application Support'
    else:
        candidate = Path(environ.get('XDG_DATA_HOME') or home / '.local' / 'share')
        base = candidate if candidate.is_absolute() else home / '.local' / 'share'
    return base / 'Wize Marketing Machine'


class DesktopRuntime:
    """Own exactly one listener and its existing workers; no startup registration."""

    def __init__(self, directory=None, preferred_port=8765, fixed_port=False):
        from mission_control.server import Server, check_timezone_support
        from mission_control.store import Store
        from mission_control.workspace_lock import WorkspaceLock
        check_timezone_support()
        self.directory = Path(directory) if directory is not None else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = WorkspaceLock(self.directory)
        self.lock.acquire()
        try:
            store = Store(self.directory / 'mission-control.sqlite3')
            try:
                self.server = Server(('127.0.0.1', preferred_port), store)
            except OSError as error:
                if fixed_port or error.errno not in (errno.EADDRINUSE, errno.EACCES, 10048, 10013):
                    raise
                self.server = Server(('127.0.0.1', 0), store)
        except BaseException:
            self.lock.release()
            raise
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)
        self.thread = None
        self.closed = False

    def start(self, workers=True):
        """Start on the chosen port once; opening a browser issues no authority."""
        if self.closed:
            raise RuntimeError('This desktop runtime is closed')
        if self.thread is not None:
            return self.origin
        try:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            if workers:
                self.server.runner.start()
                self.server.audit_runner.start()
        except BaseException:
            self.close()
            raise
        return self.origin

    def close(self):
        """Stop only this runtime, retaining user data and existing provider receipts."""
        if self.closed:
            return
        self.closed = True
        try:
            failed = stop_workers(self.server)
            if self.thread is not None and self.thread.ident is not None:
                self.server.shutdown()
                self.thread.join(timeout=10)
            self.server.server_close()
        finally:
            if stopped_runtime(self.server, self.thread):
                self.lock.release()
        if failed:
            raise failed


def stop_workers(server):
    failed = None
    for worker in (server.runner, server.audit_runner):
        if worker.thread is not None and worker.thread.ident is not None:
            try:
                worker.stop()
            except Exception as error:
                failed = failed or error
    return failed


def stopped_runtime(server, thread):
    workers = (server.runner, server.audit_runner)
    return not any(w.thread is not None and w.thread.is_alive() for w in workers) and (
        thread is None or not thread.is_alive())


def headless():
    """Run the same workspace without a GUI, browser or startup registration."""
    stopped = threading.Event()
    previous = {}
    def request_stop(signum, frame):
        stopped.set()
    try:
        for name in ('SIGINT', 'SIGTERM'):
            sig = getattr(signal, name, None)
            if sig is not None:
                previous[sig] = signal.signal(sig, request_stop)
        runtime = DesktopRuntime(fixed_port=True)
        try:
            origin = runtime.start()
            print(json.dumps(dict(status='RUNNING', origin=origin, mode='HEADLESS')), flush=True)
            # A finite wait returns control to Python so Windows can dispatch
            # pending console signal handlers even while the worker is idle.
            while True:
                stopped.wait(0.5)
                if stopped.is_set():
                    break
        finally:
            runtime.close()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def dispatch(arguments):
    """Frozen executables expose only the two existing fixed agent adapters."""
    modules = {'--agent-cli': 'agent_cli', '--mcp': 'agent_mcp'}
    if not arguments or arguments[0] not in modules:
        return False
    from importlib import import_module
    adapter = import_module('.' + modules[arguments[0]], 'mission_control')
    previous = sys.argv
    try:
        sys.argv = [previous[0], *arguments[1:]]
        result = adapter.main()
        if result:
            raise SystemExit(result)
    finally:
        sys.argv = previous
    return True


def self_test():
    """Exercise bundled assets and actual loopback APIs in a disposable private database."""
    import tempfile
    from urllib.request import build_opener, ProxyHandler
    from mission_control.operation_catalog import catalog
    with tempfile.TemporaryDirectory() as folder:
        runtime = DesktopRuntime(Path(folder), 0)
        try:
            runtime.start(workers=False)
            client = build_opener(ProxyHandler({}))
            with client.open(runtime.origin+'/api/bootstrap', timeout=10) as response:
                assert json.load(response)['apps']
            for route, marker in (('/', b'Set your goal'), ('/app.js', b'goalOverview'),
                                  ('/guided-workflow.js', b'WMMGoalJourney')):
                with client.open(runtime.origin+route, timeout=10) as response:
                    assert marker in response.read()
            assert catalog()['operations']
        finally:
            runtime.close()
    print(json.dumps(dict(status='PASS', actual_loopback=True, bundled_assets=True,
                          provider_execution='NOT_RUN', data='DISPOSABLE_SYNTHETIC')))


def vault_self_test():
    """Roundtrip only a unique disposable WMM item; never return secret bytes."""
    from uuid import uuid4
    from mission_control.credential_vault import Vault
    vault = Vault()
    name = 'WMM/disposable-package-test/' + str(uuid4())
    value = {'probe': 'synthetic-private-' + str(uuid4())}
    if vault.get(name) is not None:
        raise RuntimeError('Disposable credential address is already occupied')
    try:
        vault.put(name, value)
        if vault.get(name) != value:
            raise RuntimeError('Protected credential readback did not match')
    finally:
        vault.delete(name)
    if vault.get(name) is not None:
        raise RuntimeError('Disposable credential cleanup could not be verified')
    print(json.dumps(dict(status='PASS', native_protected_storage=True,
                          synthetic_item_removed=True, secret_contents_returned=False)))


def main(arguments=None):
    """Show a small controller; shutting the browser alone leaves approved work running."""
    arguments = sys.argv[1:] if arguments is None else arguments
    if dispatch(arguments):
        return
    if arguments == ['--check']:
        print(json.dumps(dict(data_directory=str(data_directory()), bind='127.0.0.1',
                              credential_migration=False, automatic_startup=False)))
        return
    if arguments == ['--self-test']:
        self_test()
        return
    if arguments == ['--vault-self-test']:
        vault_self_test()
        return
    if arguments == ['--headless']:
        headless()
        return
    if arguments:
        raise SystemExit('Use the desktop app, --headless, --check, --agent-cli or --mcp')
    import tkinter as tk
    from tkinter import messagebox
    controller = tk.Tk()
    controller.title('Wize Marketing Machine')
    controller.geometry('520x260')
    runtime = None
    try:
        runtime = DesktopRuntime()
        origin = runtime.start()
        tk.Label(controller, text='Your app marketing workspace is running.', wraplength=460,
                 font=('Segoe UI', 13), padx=20, pady=18).pack()
        tk.Label(controller, text='Closing the browser keeps approved work running.\n'
                 'Quit here to stop the local worker. Saved work stays on this device.',
                 wraplength=460, padx=20, pady=12).pack()
        tk.Button(controller, text='Open my workspace', command=lambda: webbrowser.open(origin),
                  padx=16, pady=8).pack()
        tk.Button(controller, text='Quit WMM', command=controller.destroy, padx=16, pady=8).pack()
        webbrowser.open(origin)
        controller.mainloop()
    except Exception:
        messagebox.showerror('WMM could not start',
                             'Your saved work is preserved. Close other WMM windows and try again. '
                             'Check application data access and required runtime components.')
        raise
    finally:
        if runtime is not None:
            runtime.close()


if __name__ == '__main__':
    main()
