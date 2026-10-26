"""Linux-local executable discovery; fixtures do not establish provider sign-in."""
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.linux_agent_paths import package_roots,candidates,native_file
from mission_control.agent_native import locate,native_candidate


class LinuxAgentPathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.home=Path(self.temp.name)

    def binary(self,path):
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'\x7fELFsynthetic fixture, not an official binary');path.chmod(0o700);return path

    def test_fixed_linux_candidates_never_require_windows_or_path(self):
        rows=candidates('claude',self.home);self.assertEqual(rows[0][0],self.home/'.local/bin/claude')
        self.assertTrue(all('Windows' not in str(r[0]).replace(str(self.home),'') and 'AppData' not in str(r[0]).replace(str(self.home),'') for r in rows))
        self.assertEqual(candidates('arbitrary-tool',self.home),[])

    def test_native_installer_payload_is_hash_bound_without_execution(self):
        path=self.binary(self.home/'.local/bin/codex')
        with patch('mission_control.agent_native.sys.platform','linux'),patch('os.access',return_value=True):
            first=locate('codex',self.home);self.assertEqual(first['executable'],str(path.resolve()))
            path.write_bytes(path.read_bytes()+b'changed');second=locate('codex',self.home)
        self.assertNotEqual(first['sha256'],second['sha256']);self.assertNotEqual(first['fingerprint'],second['fingerprint'])

    def test_npm_native_payload_requires_matching_package_metadata(self):
        package=self.home/'.npm-global/lib/node_modules/@openai/codex';binary=self.binary(package/'node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex')
        metadata=package/'package.json';metadata.write_text(json.dumps(dict(name='wrong-package',version='1.2.3')),encoding='utf-8')
        fixed=[(binary,metadata,'@openai/codex')]
        with patch('mission_control.agent_native.sys.platform','linux'),patch('mission_control.agent_native.candidates',return_value=fixed),patch('os.access',return_value=True):
            with self.assertRaises(Invalid):locate('codex',self.home)
            metadata.write_text(json.dumps(dict(name='@openai/codex',version='1.2.3')),encoding='utf-8')
            self.assertEqual(locate('codex',self.home)['package_version'],'1.2.3')
        self.assertIn(fixed[0],candidates('codex',self.home))

    def test_scripts_nonexecutables_and_missing_files_are_rejected(self):
        path=self.home/'shim';path.write_bytes(b'#!/bin/sh\necho synthetic')
        self.assertFalse(native_file(path));self.assertFalse(native_file(self.home/'missing'))
        self.binary(path)
        with patch('os.access',return_value=False):self.assertFalse(native_file(path))
        with patch('os.access',return_value=True):self.assertTrue(native_file(path))
        with patch('mission_control.agent_native.sys.platform','linux'),patch('os.access',return_value=True):self.assertTrue(native_candidate(path))
        self.assertFalse(native_candidate(self.home/'missing'))

    def test_nvm_scan_is_bounded_and_has_no_untrusted_request_root(self):
        for i in range(35):(self.home/'.nvm/versions/node'/str(i)/'lib/node_modules').mkdir(parents=True)
        self.assertEqual(len(package_roots(self.home)),37)
        self.assertTrue(all(isinstance(row,Path) for row in package_roots(self.home)))

    @unittest.skipUnless(os.name=='posix','Actual POSIX process acceptance runs in the Linux profile')
    def test_actual_local_posix_process_and_cancellation_need_no_other_host(self):
        import sys
        from mission_control.agent_process import capture
        result=capture([sys.executable,'-c',"print('SYNTHETIC_LOCAL_LINUX_PROCESS')"],timeout=5)
        self.assertEqual(result['code'],0);self.assertIn('SYNTHETIC_LOCAL_LINUX_PROCESS',result['stdout'])
        def stop():raise Invalid('Synthetic cancellation')
        with self.assertRaisesRegex(Invalid,'cancellation'):capture([sys.executable,'-c','import time;time.sleep(30)'],alive=stop,timeout=5)
