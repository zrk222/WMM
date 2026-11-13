"""Maintained files stay Ruff-formatted and lint-clean where Ruff is installed."""

import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class FormatRatchetTests(unittest.TestCase):
    def test_maintained_files_are_formatted_and_clean(self) -> None:
        if shutil.which("ruff") is None or not (ROOT / "node_modules/prettier").exists():
            self.skipTest("Formatting tools are installed by the pinned CI job")
        result = subprocess.run([sys.executable, "tools/check_format.py"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_maintained_lists_are_sorted_and_unique(self) -> None:
        for name in ("maintained_files.txt", "maintained_js.txt"):
            lines = [line.strip() for line in (ROOT / "tools" / name).read_text(encoding="utf-8").splitlines()]
            paths = [line for line in lines if line and not line.startswith("#")]
            self.assertEqual(paths, sorted(paths), name)
            self.assertEqual(len(paths), len(set(paths)), name)
            # Registries retain deleted names; enrollment rejects newly invented
            # missing paths against the Git baseline, while tools filter history.
            module = runpy.run_path(str(ROOT / "tools/check_format.py"))
            actual = module["maintained" if name == "maintained_files.txt" else "maintained_js"]()
            self.assertEqual(actual, [path for path in paths if (ROOT / path).is_file()])

    def test_retired_paths_remain_in_history_but_are_not_sent_to_tools(self) -> None:
        module = runpy.run_path(str(ROOT / "tools/check_format.py"))
        with tempfile.TemporaryDirectory(prefix="wmm-format-history-") as folder:
            root = Path(folder)
            (root / "active.py").write_text("pass\n")
            (root / "active.mjs").write_text("export {};\n")
            pylist, jslist = root / "python.txt", root / "javascript.txt"
            pylist.write_text("active.py\nretired.py\n")
            jslist.write_text("active.mjs\nretired.js\n")
            with patch.dict(module["maintained"].__globals__, {"ROOT": root, "LIST": pylist, "JS_LIST": jslist}):
                self.assertEqual(module["maintained"](), ["active.py"])
                self.assertEqual(module["maintained_js"](), ["active.mjs"])
            self.assertIn("retired.py", pylist.read_text())
            self.assertIn("retired.js", jslist.read_text())


if __name__ == "__main__":
    unittest.main()
