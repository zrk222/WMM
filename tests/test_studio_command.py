"""Actual synchronous command descendants and bounded cleanup proof."""
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from mission_control import studio_command as target
from mission_control.common import Invalid


@unittest.skipUnless(os.name=='nt','Windows owned command acceptance')
class CommandTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wmm-command-test-');self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)

    def command(self,script,**kwargs):
        return target.capture_owned_command([sys.executable,'-u','-c',script],folder=self.folder,timeout=2,**kwargs)

    def test_exited_launcher_descendant_is_stopped_before_capture_returns(self):
        import _winapi
        descendant="import os,time;from pathlib import Path;Path('ready').write_text(str(os.getpid()));time.sleep(30)"
        script="import subprocess,sys,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-u','-c',"+repr(descendant)+"]);\nwhile not Path('ready').exists():time.sleep(.01)\nprint('{\"ok\":true}')"
        result=self.command(script)
        self.assertEqual(result['code'],0);self.assertIn('true',result['stdout'])
        pid=int((self.folder/'ready').read_text())
        try:handle=_winapi.OpenProcess(0x100000,False,pid)
        except OSError:return
        try:self.assertEqual(_winapi.WaitForSingleObject(handle,1000),0)
        finally:_winapi.CloseHandle(handle)

    def test_continuous_descendant_output_is_capped_without_caller_reads(self):
        retained=[]
        script="import subprocess,sys,time;p=subprocess.Popen([sys.executable,'-u','-c','import sys;sys.stdout.write(\"x\"*2000000);sys.stdout.flush()']);time.sleep(10)"
        with self.assertRaises(Invalid):self.command(script,diagnostics=retained.append)
        self.assertTrue(retained[0]['tree_stopped']);self.assertTrue(retained[0]['overflow'])
        self.assertLessEqual(len(retained[0]['stdout'].encode())+len(retained[0]['stderr'].encode()),target.CAP)

    def test_nonzero_exit_preserves_stdout_and_stderr_and_stopped_receipt(self):
        retained=[]
        result=self.command("import sys;print('partial');print('synthetic error',file=sys.stderr);sys.exit(3)",diagnostics=retained.append)
        self.assertEqual(result['code'],3);self.assertIn('partial',result['stdout'])
        self.assertIn('synthetic error',result['stderr']);self.assertTrue(retained[0]['tree_stopped'])

    def test_timeout_and_cancellation_retain_partial_diagnostics(self):
        retained=[]
        with self.assertRaises(Invalid):self.command("import time;print('before timeout',flush=True);time.sleep(10)",diagnostics=retained.append)
        self.assertIn('before timeout',retained[0]['stdout']);self.assertTrue(retained[0]['tree_stopped'])
        start=time.monotonic();retained=[]
        def alive():
            if time.monotonic()-start>.1:raise Invalid('Synthetic cancellation')
        with self.assertRaises(Invalid):self.command("import time;print('before cancel',flush=True);time.sleep(10)",alive=alive,diagnostics=retained.append)
        self.assertTrue(retained[0]['interrupted']);self.assertTrue(retained[0]['tree_stopped'])

    def test_unconfirmed_stop_is_never_success_and_is_retained_separately(self):
        from types import SimpleNamespace
        def failed():raise Invalid('Synthetic stop failure')
        child=SimpleNamespace(poll=lambda:0,stop=failed,overflow=False,failure=None)
        retained=[]
        with patch.object(target,'spawn_studio_child',return_value=child),self.assertRaisesRegex(Invalid,'unconfirmed'):
            self.command('never executed',diagnostics=retained.append)
        self.assertEqual(retained[0]['cleanup_failure'],'Invalid');self.assertFalse(retained[0]['tree_stopped'])
        recovery=retained[0]['recovery_id'];self.assertIn(recovery,target.PENDING_CLEANUP)
        child.stop=lambda:None
        self.assertTrue(target.retry_cleanup(recovery)['tree_stopped'])
        self.assertNotIn(recovery,target.PENDING_CLEANUP)

    def test_diagnostic_callback_failure_is_not_masked_as_command_success(self):
        def failed(value):raise OSError('Synthetic private storage failure')
        with self.assertRaisesRegex(Invalid,'diagnostics could not be retained'):
            self.command("print('completed')",diagnostics=failed)

    def test_missing_executable_retains_launch_failure(self):
        retained=[]
        with self.assertRaises(Invalid):
            target.capture_owned_command([str(self.folder/'missing.exe')],folder=self.folder,diagnostics=retained.append)
        self.assertEqual(retained[0]['command_failure'],'Invalid');self.assertTrue(retained[0]['tree_stopped'])

    def test_output_snapshot_and_deliver_require_confirmed_cleanup(self):
        (self.folder/'stdout.log').write_bytes(b'partial command')
        value=target.output_snapshot(self.folder,0,True,None,None,None)
        self.assertEqual(value['stdout'],'partial command')
        self.assertEqual(target.deliver(None,value,self.folder)['code'],0)
        for field in ('cleanup_failure','command_failure','overflow','capture_failure'):
            changed=dict(value);changed[field]='SyntheticFailure' if field.endswith('failure') else True
            with self.assertRaises(Invalid):target.deliver(None,changed,self.folder)

    def test_unconfirmed_launch_rollback_is_preserved_as_pending_owned_cleanup(self):
        from types import SimpleNamespace
        owner=SimpleNamespace(overflow=False,failure=None,stop=lambda:None)
        retained=[]
        error=target.LaunchCleanupPending(owner)
        with patch.object(target,'spawn_studio_child',side_effect=error),self.assertRaisesRegex(Invalid,'unconfirmed'):
            self.command('never executed',diagnostics=retained.append)
        value=retained[0]
        self.assertFalse(value['tree_stopped']);self.assertIsNotNone(value['recovery_id'])
        self.assertEqual(value['cleanup_failure'],'LaunchCleanupPending')
        self.assertTrue(target.retry_cleanup(value['recovery_id'])['tree_stopped'])

    def test_failed_log_read_cannot_hide_unconfirmed_cleanup(self):
        from types import SimpleNamespace
        def failed():raise Invalid('Synthetic teardown failure')
        child=SimpleNamespace(poll=lambda:0,stop=failed,overflow=False,failure=None)
        retained=[]
        with patch.object(target,'spawn_studio_child',return_value=child),patch.object(target,'output_snapshot',side_effect=OSError('Synthetic log read failure')):
            with self.assertRaisesRegex(Invalid,'unconfirmed'):self.command('never executed',diagnostics=retained.append)
        value=retained[0]
        self.assertFalse(value['tree_stopped']);self.assertEqual(value['diagnostic_read_failure'],'OSError')
        self.assertIn(value['recovery_id'],target.PENDING_CLEANUP)
        child.stop=lambda:None
        self.assertTrue(target.retry_cleanup(value['recovery_id'])['tree_stopped'])

    def test_recovery_snapshot_keeps_pending_identity_when_log_io_fails(self):
        with patch.object(target,'output_snapshot',side_effect=OSError('Synthetic log failure')):
            value=target.recovery_snapshot(self.folder,None,False,'Invalid','Invalid',None)
        self.assertEqual(value['recovery_id'],self.folder.name)
        self.assertFalse(value['tree_stopped']);self.assertEqual(value['diagnostic_read_failure'],'OSError')


if __name__=='__main__':unittest.main()
