"""Verify native package assembly and reject invalid smoke observations."""
import hashlib
import io
from pathlib import Path
import runpy
import shutil
import sqlite3
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


class NativeDesktopPackageTests(unittest.TestCase):
    def test_public_installer_compiles_with_the_publisher_device_client(self):
        workflow=(ROOT/'.github/workflows/desktop-packages.yml').read_text(encoding='utf-8')
        step=workflow.split('      - name: Build native Mission Control and its frozen engine\n',1)[1].split('      - name:',1)[0]
        self.assertIn('WMM_GITHUB_DEVICE_CLIENT_ID: ${{ vars.WMM_GITHUB_DEVICE_CLIENT_ID }}',step)
        self.assertIn('python tools/build_desktop.py --native-window',step)

    def test_native_probe_supplies_disposable_windows_home_without_inheriting_credentials(self):
        run = runpy.run_path(str(ROOT / 'tools/test_native_desktop_bundle.py'))['run']
        profile = Path('disposable-profile')
        with patch.dict('os.environ', {'PATH': 'fixture', 'GITHUB_TOKEN': 'synthetic-secret'}, clear=True), \
             patch('subprocess.run') as process:
            run(Path('bundle/WMM-Mission-Control.exe'), profile)
        env = process.call_args.kwargs['env']
        for key in ('USERPROFILE', 'LOCALAPPDATA', 'HOME', 'XDG_DATA_HOME'):
            self.assertEqual(env[key], str(profile))
        self.assertNotIn('GITHUB_TOKEN', env)

    def test_installer_acceptance_refuses_missing_or_failed_native_shell(self):
        from types import SimpleNamespace

        for script, native, windows in (
            ('tools/test_windows_installer.py', 'WMM-Mission-Control.exe', True),
            ('tools/test_linux_package.py', 'WMM-Mission-Control', False),
        ):
            verify = runpy.run_path(str(ROOT / script))['verify_binary']
            with self.subTest(script=script), tempfile.TemporaryDirectory() as temporary:
                folder = Path(temporary)
                binary = folder / ('WMM.exe' if windows else 'WMM')
                arguments = (binary, folder, {}, 'synthetic') if windows else (binary, {}, 'synthetic')
                with patch.dict(verify.__globals__, {'run': lambda *a, **k: self.fail('Invoked missing native shell')}):
                    with self.assertRaisesRegex(AssertionError, 'native Mission Control window is missing'):
                        verify(*arguments)
                (folder / native).write_bytes(b'synthetic native shell')
                with patch.dict(verify.__globals__, {'run': lambda *a, **k: SimpleNamespace(stdout='{"status":"FAIL"}')}):
                    with self.assertRaisesRegex(AssertionError, 'native .*verification failed'):
                        verify(*arguments)

    def test_build_pins_exact_frozen_executable_before_copying_window(self):
        build = runpy.run_path(str(ROOT / 'tools/build_desktop.py'))['build_native_window']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / 'bundle'
            folder.mkdir()
            engine = folder / 'WMM.exe'
            engine.write_bytes(b'synthetic frozen engine')
            release = root / '.factory/native-window-build/release'
            release.mkdir(parents=True)
            (release / 'wmm-mission-control.exe').write_bytes(b'synthetic native shell')
            with patch.dict(build.__globals__, {'ROOT': root}), patch('sys.platform', 'win32'), \
                 patch.dict('os.environ', {'WMM_GITHUB_DEVICE_CLIENT_ID':'synthetic_publisher_client'}), \
                 patch('subprocess.run') as cargo:
                self.assertEqual(build(folder), 'WMM-Mission-Control.exe')
                self.assertIn('--locked', cargo.call_args.args[0])
                self.assertEqual(cargo.call_args.kwargs['env']['WMM_NATIVE_ENGINE_SHA256'],
                                 hashlib.sha256(engine.read_bytes()).hexdigest())
                self.assertEqual(cargo.call_args.kwargs['env']['WMM_GITHUB_DEVICE_CLIENT_ID'],'synthetic_publisher_client')
                self.assertEqual((folder / 'WMM-Mission-Control.exe').read_bytes(), b'synthetic native shell')
                engine.unlink()
                with self.assertRaisesRegex(RuntimeError, 'exact frozen WMM engine'):
                    build(folder)
                cargo.assert_called_once()

    def test_ubuntu_archive_uses_native_entry_and_dependency_only_for_native_bundle(self):
        build = runpy.run_path(str(ROOT / 'tools/build_linux_package.py'))['main']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(ROOT / 'packaging/linux', root / 'packaging/linux')
            bundle = root / 'dist/desktop/WMM'
            bundle.mkdir(parents=True)
            (bundle / 'WMM').write_bytes(b'synthetic frozen engine')
            with patch.dict(build.__globals__, {'ROOT': root}), patch('sys.platform', 'linux'), \
                 patch('platform.machine', return_value='x86_64'):
                for native in (False, True):
                    if native:
                        (bundle / 'WMM-Mission-Control').write_bytes(b'synthetic native shell')
                    build()
                    raw = (root / 'dist/linux/wize-marketing-machine_0.1.0_amd64.deb').read_bytes()
                    members, cursor = {}, 8
                    while cursor < len(raw):
                        header = raw[cursor:cursor + 60]
                        size = int(header[48:58])
                        members[header[:16].decode().strip()] = raw[cursor + 60:cursor + 60 + size]
                        cursor += 60 + size + size % 2
                    with tarfile.open(fileobj=io.BytesIO(members['control.tar.gz'])) as control:
                        self.assertEqual(b'libwebkit2gtk-4.1-0' in control.extractfile('./control').read(), native)
                    with tarfile.open(fileobj=io.BytesIO(members['data.tar.gz'])) as data:
                        launcher = data.extractfile('./usr/bin/wize-marketing-machine').read()
                        self.assertEqual(b'WMM-Mission-Control' in launcher, native)

    def test_smoke_rejects_false_success_for_altered_engine(self):
        verify = runpy.run_path(str(ROOT / 'tools/test_native_desktop_bundle.py'))['verify_bundle']

        def fixture_run(shell, profile):
            if profile.name == 'rejected':
                return failure_code
            workspace = profile / 'Wize Marketing Machine'
            workspace.mkdir(parents=True)
            db = sqlite3.connect(workspace / 'mission-control.sqlite3')
            try:
                db.execute('CREATE TABLE jobs (id INTEGER)')
                db.commit()
            finally:
                db.close()
            return 0

        with tempfile.TemporaryDirectory() as temporary:
            bundle = Path(temporary)
            for name in ('WMM.exe', 'WMM-Mission-Control.exe'):
                (bundle / name).write_bytes(b'synthetic')
            with patch('sys.platform', 'win32'), patch.dict(verify.__globals__, {'run': fixture_run}):
                failure_code = 1
                self.assertEqual(verify(bundle)['status'], 'PASS')
                failure_code = 0
                with self.assertRaisesRegex(RuntimeError, 'did not reject an altered engine'):
                    verify(bundle)
