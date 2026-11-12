"""Exercise enrollment against actual disposable Git histories."""

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "source_ratchet", Path(__file__).resolve().parents[1] / "tools/source_ratchet.py"
)
assert SPEC and SPEC.loader
ratchet = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ratchet)
REGISTRIES, audit, paths = ratchet.REGISTRIES, ratchet.audit, ratchet.paths


class SourceRatchetTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        for name in set(REGISTRIES.values()):
            self.write(name, "# Fixture registry\nold.py\n" if name.endswith("files.txt") else "")
        self.write("old.py", "value = 1\n")
        self.commit()
        self.base = self.git("rev-parse", "HEAD").decode().strip()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], stderr=subprocess.PIPE)

    def write(self, name, text):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture")

    def test_missing_source_fails_and_enrollment_replays_deterministically(self):
        self.write("space name.py", "value = 2\n")
        self.write("ui.mjs", "export const value = 2;\n")
        result = audit(self.root, self.base)
        self.assertFalse(result["ok"])
        self.assertIn("space name.py", str(result["errors"]))
        self.assertTrue(audit(self.root, self.base, write=True)["ok"])
        before = (self.root / "tools/maintained_files.txt").read_bytes()
        self.assertTrue(audit(self.root, self.base, write=True)["ok"])
        self.assertEqual(before, (self.root / "tools/maintained_files.txt").read_bytes())
        self.commit()
        self.assertTrue(audit(self.root, self.base, "HEAD")["ok"])

    def test_deleted_sources_retain_registry_history(self):
        (self.root / "old.py").unlink()
        self.assertTrue(audit(self.root, self.base)["ok"])
        self.write("tools/maintained_files.txt", "")
        self.assertFalse(audit(self.root, self.base)["ok"])
        self.assertTrue(audit(self.root, self.base, write=True)["ok"])
        self.assertIn("old.py", paths((self.root / "tools/maintained_files.txt").read_text()))

    def test_rename_requires_new_name_and_preserves_old_name(self):
        (self.root / "old.py").rename(self.root / "new.py")
        self.assertFalse(audit(self.root, self.base)["ok"])
        self.assertTrue(audit(self.root, self.base, write=True)["ok"])
        self.assertEqual(paths((self.root / "tools/maintained_files.txt").read_text()), {"old.py", "new.py"})

    def test_unknown_base_and_head_write_are_rejected(self):
        with self.assertRaises(subprocess.CalledProcessError):
            audit(self.root, "not-a-ref")
        with self.assertRaises(ValueError):
            audit(self.root, self.base, "HEAD", write=True)

    def test_committed_directory_is_not_a_source_file(self):
        self.write("nested.py/payload.txt", "fixture")
        self.write("tools/maintained_files.txt", "old.py\nnested.py\n")
        self.commit()
        self.assertFalse(audit(self.root, self.base, "HEAD")["ok"])
        self.assertFalse(audit(self.root, self.base)["ok"])

    def test_new_registry_typo_fails(self):
        self.write("tools/maintained_files.txt", "old.py\nabsent.py\n")
        self.assertFalse(audit(self.root, self.base)["ok"])


if __name__ == "__main__":
    unittest.main()
