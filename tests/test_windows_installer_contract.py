"""Static packaging boundaries; these do not prove installed behavior."""
import unittest
from pathlib import Path
from unittest.mock import patch

import runpy

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = runpy.run_path(str(ROOT / 'tools/test_windows_installer.py'))
compiler, main = SCRIPT['compiler'], SCRIPT['main']


class WindowsInstallerContractTests(unittest.TestCase):
    def test_per_user_no_startup_no_workspace_delete_or_forced_close(self):
        text = (ROOT / 'packaging/windows/WMM.iss').read_text(encoding='utf-8')
        lower = text.lower()
        for required in ('privilegesrequired=lowest', 'defaultdirname={localappdata}\\programs',
                         'closeapplications=no', 'restartapplications=no', 'skipifsilent',
                         '{sys}\\wscript.exe', 'open wmm.vbs'):
            self.assertIn(required, lower)
        for forbidden in ('[uninstalldelete]', '[registry]', 'taskkill', 'schtasks',
                          '{userstartup}', '{commonstartup}', 'powershell', 'http://', 'https://'):
            self.assertNotIn(forbidden, lower)
        self.assertNotIn('mission-control.sqlite3', lower)

    def test_missing_compiler_and_non_ci_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'ISCC.exe'):
            compiler({})
        with patch('sys.platform', 'win32'), \
             patch.dict('os.environ', {'CI':'false','WMM_INSTALLER_TEST':'1'}):
            with self.assertRaisesRegex(RuntimeError, 'isolated Windows CI'):
                main()


if __name__ == '__main__':
    unittest.main()
