"""Integrity behavior over isolated files; real installed readback is separate."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from mission_control import hypit_installation as target
from mission_control.common import Invalid


def short_windows_path(path):
    """Return a native 8.3 alias when Windows provides one, otherwise None."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        get_short = kernel.GetShortPathNameW
        get_short.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint)
        get_short.restype = ctypes.c_uint
        size = get_short(str(path), None, 0)
        if not size:
            return None
        buffer = ctypes.create_unicode_buffer(size)
        if not get_short(str(path), buffer, size):
            return None
        alias = Path(buffer.value)
        if os.path.normcase(str(alias)) == os.path.normcase(str(path)):
            return None
        return alias
    except (AttributeError, OSError):
        return None


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wmm-installation-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'hypit'
        self.entry = self.put('bin/hypit.mjs', b'// synthetic entrypoint')
        self.node = self.base / 'node.exe'
        self.node.write_bytes(b'synthetic executable identity; never executed')
        self.put('package.json', json.dumps(dict(name='@hypit/hypit', version='0.3.1')).encode())
        for name in ('tsx', 'vite', '@hypit/video'):
            self.put('node_modules/'+name+'/package.json', json.dumps(dict(name=name)).encode())
        self.dependency = self.put('node_modules/tsx/index.js', b'export const fixture = 1;')
        self.reviewed = {}
        for name in target.REVIEWED:
            content = ('// isolated fixture '+name).encode()
            self.put('node_modules/@hypit/studio/src/'+name, content)
            self.reviewed[name] = hashlib.sha256(content).hexdigest()
        self.patch = patch.object(target, 'REVIEWED', self.reviewed)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def put(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def read(self):
        return target.fingerprint(self.node, self.entry)

    def test_exact_fingerprint_revalidates_and_public_summary_has_no_paths(self):
        value = self.read()
        self.assertEqual(target.revalidate(value), value)
        public = target.public_summary(value)
        self.assertEqual(public['status'], 'FINGERPRINTED_NOT_EXECUTED')
        self.assertEqual(public['runtime_acceptance'], 'NOT_RUN')
        self.assertEqual(public['files'], 12)
        self.assertEqual(public['bytes'], sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()))
        self.assertNotIn(str(self.base), json.dumps(public))
        self.assertTrue({'node','root','entrypoint'}.isdisjoint(public))

    def test_changed_dependency_rejects_old_identity_without_changing_wrapper(self):
        value = self.read()
        self.dependency.write_bytes(b'export const fixture = 2;')
        self.assertNotEqual(self.read()['tree_sha256'], value['tree_sha256'])
        with self.assertRaisesRegex(Invalid, 'changed'):
            target.revalidate(value)

    def test_added_and_removed_files_change_membership_identity(self):
        value = self.read()
        extra = self.put('node_modules/extra.js', b'new dependency')
        with self.assertRaisesRegex(Invalid, 'changed'):
            target.revalidate(value)
        extra.unlink()
        self.assertEqual(target.revalidate(value), value)
        self.dependency.unlink()
        with self.assertRaisesRegex(Invalid, 'changed'):
            target.revalidate(value)

    def test_node_and_entrypoint_changes_reject(self):
        for path in (self.node, self.entry):
            value = self.read()
            previous = path.read_bytes()
            path.write_bytes(previous+b' changed')
            with self.assertRaisesRegex(Invalid, 'changed'):
                target.revalidate(value)
            path.write_bytes(previous)

    def test_each_reviewed_file_is_required_and_pinned(self):
        for name in self.reviewed:
            path = self.root/'node_modules/@hypit/studio/src'/name
            original = path.read_bytes()
            path.write_bytes(original+b' changed')
            with self.assertRaisesRegex(Invalid, 'reviewed'):
                self.read()
            path.unlink()
            with self.assertRaisesRegex(Invalid, 'reviewed'):
                self.read()
            path.write_bytes(original)

    def test_wrong_and_malformed_package_manifests_reject(self):
        path = self.root/'package.json'
        for content in (b'[]', b'{', b'{"name":"other","version":"0.3.1"}',
                        b'{"name":"@hypit/hypit","version":"0.3.2"}'):
            path.write_bytes(content)
            with self.assertRaises(Invalid):
                self.read()

    def test_missing_transitive_package_identity_rejects(self):
        (self.root/'node_modules/vite/package.json').unlink()
        with self.assertRaises(Invalid):
            self.read()

    def test_bounds_and_linked_paths_reject(self):
        for name, limit in (('MAX_FILES',1),('MAX_FILE_BYTES',1),('MAX_TREE_BYTES',1)):
            with patch.object(target,name,limit), self.assertRaisesRegex(Invalid,'bound|too many'):
                self.read()
        linked = self.root/'node_modules/linked.js'
        try:
            linked.symlink_to(self.dependency)
        except OSError:
            self.skipTest('Host does not permit an isolated symlink')
        with self.assertRaisesRegex(Invalid,'linked'):
            self.read()

    def test_windows_reparse_directory_is_denied_without_following(self):
        from types import SimpleNamespace
        info = SimpleNamespace(st_mode=0o40755,st_file_attributes=1024)
        with patch.object(Path,'lstat',return_value=info):
            with self.assertRaisesRegex(Invalid,'reparse'):
                target.plain(self.root,directory=True)

    def test_change_after_an_earlier_file_hash_is_detected(self):
        original = target.file_hash
        def changed(path):
            value = original(path)
            if path.name == 'feedback-server.ts':
                self.entry.write_bytes(b'changed after entrypoint was hashed')
            return value
        with patch.object(target,'file_hash',side_effect=changed):
            with self.assertRaisesRegex(Invalid,'changed while reading'):
                self.read()

    def test_membership_change_during_fingerprinting_rejects(self):
        original = target.members
        calls = []
        def changed(root):
            calls.append(1)
            if len(calls)==2:
                self.put('new.js',b'new member during hashing')
            return original(root)
        with patch.object(target,'members',side_effect=changed):
            with self.assertRaisesRegex(Invalid,'membership changed'):
                self.read()

    def test_direct_and_npm_discovery_does_not_execute_hypit(self):
        with patch.object(target.shutil,'which',side_effect=lambda n:str(self.entry if n=='hypit' else self.node)), patch.object(target,'capture') as execute:
            self.assertEqual(target.discover(),self.read())
            execute.assert_not_called()
        npm = self.base/'npm'
        npm.mkdir()
        launcher = npm/'hypit.cmd'
        launcher.write_text('synthetic wrapper')
        with patch.object(target.shutil, 'which', side_effect=lambda n: str(launcher if n == 'hypit' else self.node)), \
                patch.object(target, 'fingerprint', return_value={'fixture': True}) as inspect, \
                patch.object(target, 'capture') as execute:
            self.assertEqual(target.discover(),{'fixture':True})
            expected_entry = (npm/'node_modules/@hypit/hypit/bin/hypit.mjs').resolve()
            self.assertEqual(inspect.call_args.args,(self.node.resolve(),expected_entry))
            execute.assert_not_called()

    def test_npm_discovery_normalizes_native_windows_8dot3_alias_without_execution(self):
        npm = self.base/'npm'
        npm.mkdir()
        launcher = npm/'hypit.cmd'
        launcher.write_text('synthetic wrapper')
        alias_base = short_windows_path(self.base)
        if alias_base is None:
            return
        alias_launcher = alias_base/'npm/hypit.cmd'
        self.assertTrue(alias_launcher.is_file())
        with patch.object(target.shutil,'which',side_effect=lambda n:str(alias_launcher if n=='hypit' else self.node)), \
                patch.object(target,'fingerprint',return_value={'fixture':True}) as inspect, \
                patch.object(target,'capture') as execute:
            self.assertEqual(target.discover(),{'fixture':True})
            expected_entry = (npm/'node_modules/@hypit/hypit/bin/hypit.mjs').resolve()
            self.assertEqual(inspect.call_args.args,(self.node.resolve(),expected_entry))
            execute.assert_not_called()

    def test_volta_discovery_uses_only_fixed_which_arguments(self):
        shim = self.base/'Volta/bin/hypit.cmd'
        volta = self.base/'volta.exe'
        def which(name):
            return str({'hypit':shim,'node':self.node,'volta':volta}[name])
        def result(args,**kwargs):
            self.assertEqual(args[:2],[str(volta),'which'])
            extra = {'PATHEXT': '.EXE;.CMD;.BAT;.COM'} if os.name=='nt' else {}
            self.assertEqual(kwargs,dict(timeout=15,extra_env=extra))
            path = self.base/'hypit-install/hypit' if args[2]=='hypit' else self.node
            return dict(code=0,stdout=str(path)+'\n',stderr='')
        with patch.object(target.shutil,'which',side_effect=which), patch.object(target,'capture',side_effect=result) as execute, patch.object(target,'fingerprint',return_value={'fixture':True}):
            self.assertEqual(target.discover(),{'fixture':True})
            self.assertEqual([c.args[0][-1] for c in execute.call_args_list],['hypit','node'])
        with patch.object(target,'capture') as execute:
            with self.assertRaises(Invalid):
                target.volta_path('--unsafe-command')
            execute.assert_not_called()

    def test_direct_hypit_with_a_volta_node_resolves_the_executing_node(self):
        shim = self.base/'Program Files/Volta/node.EXE'
        with patch.object(target.shutil,'which',side_effect=lambda n:str(self.entry if n=='hypit' else shim)), patch.object(target,'volta_path',return_value=self.node) as resolve:
            value=target.discover()
            resolve.assert_called_once_with('node')
            self.assertEqual(value['node'],str(self.node.resolve()))

    def test_bad_discovery_and_malformed_expected_identity_reject(self):
        with patch.object(target.shutil,'which',return_value=None):
            with self.assertRaises(Invalid): target.discover()
        with patch.object(target.shutil,'which',return_value='volta'), patch.object(target,'capture',return_value=dict(code=1,stdout='',stderr='private diagnostic')):
            with self.assertRaisesRegex(Invalid,'discovery failed'):
                target.volta_path('hypit')
        for value in (None, {}, {'node':str(self.node)}):
            with self.assertRaises(Invalid): target.revalidate(value)


if __name__=='__main__':
    unittest.main()
