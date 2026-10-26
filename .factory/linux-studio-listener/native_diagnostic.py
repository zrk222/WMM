"""Unchanged 95/71 inventories and deadlines; record failure metadata only."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'.factory/linux-studio-listener'
if len(sys.argv)>1:
    sys.path.insert(0,str(ROOT))
    import threading
    import time
    import unittest
    from mission_control import studio_command
    original_observe=studio_command.observe;original_deliver=studio_command.deliver
    def observe(child,alive,deadline):
        started=time.monotonic()
        try:return original_observe(child,alive,deadline)
        except Exception as error:
            print(json.dumps(dict(kind='OBSERVE_FAILURE',error=type(error).__name__,detail=str(error),elapsed=time.monotonic()-started,
                                  deadline_remaining=deadline-time.monotonic(),overflow=child.overflow,capture_failure=child.failure,poll=child.poll())),flush=True)
            raise
    def deliver(callback,value,folder):
        try:return original_deliver(callback,value,folder)
        except Exception as error:
            fields={key:value.get(key) for key in ('code','interrupted','command_failure','cleanup_failure','tree_stopped','overflow','capture_failure')}
            print(json.dumps(dict(kind='DELIVER_FAILURE',error=type(error).__name__,detail=str(error),fields=fields,
                                  stdout=value.get('stdout','')[:256],stderr=value.get('stderr','')[:256])),flush=True)
            raise
    studio_command.observe=observe;studio_command.deliver=deliver
    names=['tests.test_studio_child','tests.test_studio_command','tests.test_hypit_studio_process']
    if sys.argv[1]=='combined':names.insert(0,'tests.test_studio_listener_linux')
    def threads():return [dict(name=t.name,daemon=t.daemon,alive=t.is_alive()) for t in threading.enumerate()]
    class Result(unittest.TextTestResult):
        def startTest(self,test):
            module=type(test).__module__
            if module!=getattr(self,'last_module',None):
                print(json.dumps(dict(kind='MODULE_BOUNDARY',module=module,threads=threads())),flush=True)
                self.last_module=module
            super().startTest(test)
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    def flatten(value):
        for test in value:
            if isinstance(test,unittest.TestSuite):yield from flatten(test)
            else:yield test.id()
    ids=list(flatten(suite))
    inventory=dict(profile=sys.argv[1],count=len(ids),ordered_ids=ids,
                   inventory_sha256=hashlib.sha256(json.dumps(ids,separators=(',',':')).encode()).hexdigest())
    (OUT/('diagnostic-'+sys.argv[1]+'-inventory.json')).write_text(json.dumps(inventory,indent=2),encoding='utf-8',newline='\n')
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    print(json.dumps(dict(kind='FINAL',profile=sys.argv[1],tests_run=result.testsRun,success=result.wasSuccessful(),threads=threads())),flush=True)
    raise SystemExit(not result.wasSuccessful())

import os
for profile in ('combined','baseline'):
    result=subprocess.run([sys.executable,__file__,profile],cwd=ROOT,capture_output=True,text=True,env=dict(os.environ,PYTHONUTF8='1'))
    (OUT/('diagnostic-'+profile+'.log')).write_text(result.stdout+result.stderr,encoding='utf-8',newline='\n')
    print(json.dumps(dict(profile=profile,exit=result.returncode,diagnostics=result.stdout,tail=result.stderr[-500:])),flush=True)
