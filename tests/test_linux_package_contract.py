"""Source contract checks do not establish Ubuntu package acceptance."""
import unittest
import io
import tarfile
from pathlib import Path
from unittest.mock import patch

import runpy
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(ROOT / "tools/test_linux_package.py"))
inspect_archive, preflight = SCRIPT["inspect_archive"], SCRIPT["preflight"]


class LinuxPackageContractTests(unittest.TestCase):
    def test_fixed_launcher_metadata_and_no_maintainer_scripts(self):
        folder = ROOT / 'packaging/linux'
        control = (folder / 'control').read_text()
        launcher = (folder / 'wize-marketing-machine').read_text()
        desktop = (folder / 'wize-marketing-machine.desktop').read_text()
        self.assertIn('Package: wize-marketing-machine', control)
        for dependency in ('gnome-keyring', 'dbus-user-session', 'libtk8.6', 'xdg-utils', 'ffmpeg', 'fonts-dejavu-core'):
            self.assertIn(dependency, control)
        self.assertEqual(launcher.strip(), '#!/bin/sh\nexec /usr/lib/wize-marketing-machine/WMM')
        self.assertIn('Exec=/usr/bin/wize-marketing-machine', desktop)
        self.assertEqual({p.name for p in folder.iterdir()}, {'control','wize-marketing-machine','wize-marketing-machine.desktop','wmm-worker.service'})

    def test_non_ci_preflight_rejects_before_package_commands(self):
        commands = unittest.mock.Mock(side_effect=AssertionError('Package commands must not run'))
        with patch('sys.platform', 'linux'), \
             patch('os.geteuid', return_value=0, create=True), \
             patch.dict(preflight.__globals__, {'run': commands}):
            for env in ({'CI':'false'}, {'CI':'true','GITHUB_ACTIONS':'true',
                       'WMM_LINUX_PACKAGE_TEST':'1','WMM_ISOLATED_NATIVE_KEYRING':'1',
                       'DBUS_SESSION_BUS_ADDRESS':'synthetic'}):
                with self.assertRaisesRegex(RuntimeError, 'isolated root Ubuntu'):
                    preflight(env)
            commands.assert_not_called()


    def test_archive_validation_rejects_scripts_and_escaping_payload(self):
        def archive(name, link=None):
            out = io.BytesIO()
            with tarfile.open(fileobj=out, mode='w') as tar:
                item = tarfile.TarInfo(name)
                if link is not None:
                    item.type = tarfile.SYMTYPE
                    item.linkname = link
                tar.addfile(item)
            return out.getvalue()
        inspect_archive(archive('./control'), control=True)
        inspect_archive(archive('./usr/lib/wize-marketing-machine/WMM'))
        inspect_archive(archive('./usr/share/wize-marketing-machine/wmm-worker.service'))
        for value, control in ((archive('./postinst'), True), (archive('./etc/profile'), False),
                               (archive('./usr/lib/wize-marketing-machine/link', '/etc/passwd'), False),
                               (archive('./usr/lib/wize-marketing-machine/../../etc/passwd'), False)):
            with self.assertRaises(RuntimeError):
                inspect_archive(value, control)

    def test_standard_library_archive_has_exact_debian_member_order_and_safe_tars(self):
        builder = runpy.run_path(str(ROOT / 'tools/build_linux_package.py'))
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder) / 'stage'
            (stage / 'DEBIAN').mkdir(parents=True)
            (stage / 'DEBIAN/control').write_text('Package: wize-marketing-machine\n')
            (stage / 'usr/lib/wize-marketing-machine').mkdir(parents=True)
            (stage / 'usr/lib/wize-marketing-machine/WMM').write_bytes(b'synthetic executable')
            target = Path(folder) / 'test.deb'
            builder['archive'](stage, target)
            raw = target.read_bytes()
            self.assertTrue(raw.startswith(b'!<arch>\n'))
            names, cursor = [], 8
            while cursor < len(raw):
                header = raw[cursor:cursor+60]
                self.assertEqual(header[-2:], b'`\n')
                name = header[:16].decode().strip()
                size = int(header[48:58])
                payload = raw[cursor+60:cursor+60+size]
                names.append(name)
                if name == 'debian-binary':
                    self.assertEqual(payload, b'2.0\n')
                else:
                    inspect_archive(payload, control=name.startswith('control'))
                cursor += 60 + size + size % 2
            self.assertEqual(names, ['debian-binary', 'control.tar.gz', 'data.tar.gz'])


if __name__ == '__main__':
    unittest.main()
