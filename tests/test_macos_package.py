"""Mac package assembly and isolation contracts; no local Mac build is attempted."""
from pathlib import Path
import plistlib
import runpy
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class MacOSPackageTests(unittest.TestCase):
    def test_app_stages_exact_engine_and_window_with_native_entry(self):
        stage = runpy.run_path(str(ROOT / 'tools/build_macos_package.py'))['stage']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / 'bundle'
            bundle.mkdir()
            (bundle / '_internal').mkdir()
            (bundle / '_internal/runtime-fixture').write_bytes(b'synthetic library')
            for name in ('WMM', 'WMM-Mission-Control'):
                (bundle / name).write_bytes(('synthetic ' + name).encode())
            app = stage(bundle, root / 'Wize Marketing Machine.app')
            with (app / 'Contents/Info.plist').open('rb') as stream:
                info = plistlib.load(stream)
            self.assertEqual(info['CFBundleExecutable'], 'WMM-Mission-Control')
            self.assertEqual(info['CFBundlePackageType'], 'APPL')
            self.assertEqual((app / 'Contents/Frameworks/runtime-fixture').read_bytes(), b'synthetic library')
            self.assertFalse((app / 'Contents/MacOS/_internal').exists())
            for name in ('WMM', 'WMM-Mission-Control'):
                self.assertEqual((app / 'Contents/MacOS' / name).read_bytes(), (bundle / name).read_bytes())
            self.assertIn('not notarized', (app / 'Contents/DEVELOPMENT-PREVIEW.txt').read_text())
            with self.assertRaisesRegex(ValueError, 'destination exists'):
                stage(bundle, app)

    def test_incomplete_bundle_and_external_links_are_rejected(self):
        stage = runpy.run_path(str(ROOT / 'tools/build_macos_package.py'))['stage']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / 'bundle'
            bundle.mkdir()
            with self.assertRaisesRegex(ValueError, 'both native'):
                stage(bundle, root / 'Missing.app')
            for name in ('WMM', 'WMM-Mission-Control'):
                (bundle / name).touch()
            with self.assertRaisesRegex(ValueError, 'runtime libraries'):
                stage(bundle, root / 'Incomplete.app')
            (bundle / '_internal').mkdir()
            (root / 'private-file').write_text('synthetic external file')
            try:
                (bundle / 'external').symlink_to(root / 'private-file')
            except OSError:
                return  # Windows without link privileges; native CI exercises this branch.
            with self.assertRaisesRegex(ValueError, 'external symbolic link'):
                stage(bundle, root / 'Escaped.app')

    def test_mac_build_collects_only_explicit_native_keyring_backend(self):
        command = runpy.run_path(str(ROOT / 'tools/build_desktop.py'))['command']
        with patch('sys.platform', 'darwin'):
            argv = command()
        self.assertIn('keyring.backends.macOS', argv)
        self.assertIn('keyring', argv)
        self.assertNotIn('secretstorage', argv)
        self.assertNotIn('--collect-all=keyring', argv)

    def test_acceptance_refuses_non_mac_or_non_hosted_machine(self):
        main = runpy.run_path(str(ROOT / 'tools/check_macos_bundle.py'))['main']
        with patch('sys.platform', 'darwin'), patch.dict('os.environ', {}, clear=True):
            with self.assertRaisesRegex(SystemExit, 'disposable GitHub runner'):
                main()

    def test_archive_keeps_app_root_and_unix_executable_mode(self):
        archive_app = runpy.run_path(str(ROOT / 'tools/build_macos_package.py'))['archive_app']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = root / 'Wize Marketing Machine.app'
            binary = app / 'Contents/MacOS/WMM'
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b'synthetic executable')
            binary.chmod(0o755)
            output = root / 'package.zip'
            archive_app(app, output)
            with zipfile.ZipFile(output) as archive:
                entry = archive.getinfo('Wize Marketing Machine.app/Contents/MacOS/WMM')
                self.assertEqual(archive.read(entry), b'synthetic executable')
                self.assertEqual((entry.external_attr >> 16) & 0o777, binary.stat().st_mode & 0o777)
            with self.assertRaises(FileExistsError):
                archive_app(app, output)

    def test_native_probe_supplies_isolated_mac_home(self):
        env_fn = runpy.run_path(str(ROOT / 'tools/test_native_desktop_bundle.py'))['isolated_environment']
        with patch.dict('os.environ', {'PATH': 'synthetic', 'KEYCHAIN_PATH': 'foreign',
                                     'GITHUB_TOKEN': 'synthetic'}, clear=True):
            env = env_fn(Path('disposable-home'))
        self.assertEqual(env['HOME'], 'disposable-home')
        self.assertNotIn('KEYCHAIN_PATH', env)
        self.assertNotIn('GITHUB_TOKEN', env)

    def test_ci_declares_both_architectures_without_publishing(self):
        workflow = (ROOT / '.github/workflows/macos-desktop.yml').read_text()
        for value in ('macos-15-intel', 'macos-15', 'x86_64', 'arm64',
                      'tools/check_macos_bundle.py', 'retention-days: 7'):
            self.assertIn(value, workflow)
        self.assertNotIn('contents: write', workflow)
        self.assertNotIn('gh release', workflow)
        self.assertIn('keyring==25.7.0', (ROOT / 'docs/requirements-macos.txt').read_text())


if __name__ == '__main__':
    unittest.main()
