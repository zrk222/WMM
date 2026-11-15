"""Synthetic metadata proposals preserve reviewed pins; no provider writes or binaries."""

import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("dependency_freshness", ROOT / "tools/dependency_freshness.py")
assert SPEC and SPEC.loader
freshness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freshness)
CHECKS = ".github/workflows/checks.yml"
CI_TEST = "tests/test_ci_current_candidate.py"
CURRENT = freshness.load_pin(ROOT)
CURRENT_VERSION, CURRENT_DIGEST = CURRENT["version"], CURRENT["sha256"]
PARTS = tuple(map(int, CURRENT_VERSION.split(".")))
NEW = f"{PARTS[0]}.{PARTS[1]}.{PARTS[2] + 1}"
LATER = f"{PARTS[0]}.{PARTS[1]}.{PARTS[2] + 2}"
DIGEST = ("a" if CURRENT_DIGEST != "a" * 64 else "b") * 64


def metadata(version=NEW, digest=DIGEST):
    name = "ffmpeg-" + version + "-full_build.zip"
    return {
        "tag_name": version,
        "draft": False,
        "prerelease": False,
        "html_url": "https://github.com/GyanD/codexffmpeg/releases/tag/" + version,
        "assets": [
            {
                "name": name,
                "browser_download_url": "https://github.com/GyanD/codexffmpeg/releases/download/"
                + version
                + "/"
                + name,
                "digest": "sha256:" + digest,
            }
        ],
    }


class DependencyFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in (
            *freshness.LOCKS,
            "docs/requirements-audit.in",
            "package.json",
            "package-lock.json",
            CHECKS,
            CI_TEST,
            freshness.PIN,
        ):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        self.workflow, self.test = self.root / CHECKS, self.root / CI_TEST
        self.pin = self.root / freshness.PIN
        self.original = self.workflow.read_bytes(), self.test.read_bytes(), self.pin.read_bytes()

    def assert_unchanged(self):
        self.assertEqual((self.workflow.read_bytes(), self.test.read_bytes(), self.pin.read_bytes()), self.original)

    def test_verified_metadata_changes_only_pin_json_and_preserves_workflow_baseline_bytes(self):
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        }
        result = freshness.prepare(self.root, metadata())
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob("*") if path.is_file()
        }
        self.assertTrue(result["changed"])
        self.assertEqual([name for name in before if before[name] != after[name]], [freshness.PIN])
        self.assertEqual(freshness.load_pin(self.root), {"version": NEW, "sha256": DIGEST})
        self.assertEqual((self.workflow.read_bytes(), self.test.read_bytes()), self.original[:2])
        self.assertTrue(freshness.prepare(self.root, metadata(LATER, "c" * 64))["changed"])

    def test_missing_digest_wrong_origin_url_version_and_ambiguous_assets_never_write(self):
        baseline = metadata()
        for changed in ("digest", "url", "tag", "origin", "draft", "prerelease", "duplicate", "filename", "malformed"):
            with self.subTest(changed=changed):
                value = copy.deepcopy(baseline)
                if changed == "digest":
                    value["assets"][0].pop("digest")
                elif changed == "url":
                    value["assets"][0]["browser_download_url"] = "https://example.invalid/ffmpeg.zip"
                elif changed == "tag":
                    value["tag_name"] = "9.0.3-rc1"
                elif changed == "origin":
                    value["html_url"] = "https://github.com/other/repo/releases/tag/9.0.3"
                elif changed in ("draft", "prerelease"):
                    value[changed] = True
                elif changed == "duplicate":
                    value["assets"].append(copy.deepcopy(value["assets"][0]))
                elif changed == "filename":
                    value["assets"][0]["name"] = "ffmpeg-9.0.2-full_build.zip"
                else:
                    value["assets"][0]["digest"] = "sha256:short"
                with self.assertRaises(ValueError):
                    freshness.prepare(self.root, value)
                self.assert_unchanged()

    def test_downgrade_and_same_version_digest_replacement_reject_but_exact_noop_is_clean(self):
        current = freshness.load_pin(self.root)
        version, digest = current["version"], current["sha256"]
        for value in (metadata("0.0.0"), metadata(version, DIGEST)):
            with self.assertRaises(ValueError):
                freshness.prepare(self.root, value)
            self.assert_unchanged()
        self.assertFalse(freshness.prepare(self.root, metadata(version, digest))["changed"])
        self.assert_unchanged()

    def test_unrelated_workflow_drift_rejects_without_changing_any_source(self):
        self.workflow.write_text(self.workflow.read_text().replace("timeout-minutes: 15", "timeout-minutes: 16", 1))
        mutated = self.workflow.read_bytes(), self.test.read_bytes(), self.pin.read_bytes()
        with self.assertRaisesRegex(ValueError, "baseline drift"):
            freshness.prepare(self.root, metadata())
        self.assertEqual((self.workflow.read_bytes(), self.test.read_bytes(), self.pin.read_bytes()), mutated)

    def test_pin_schema_rejects_extra_url_fields_bad_versions_and_malformed_hashes(self):
        for value in (
            {"version": "9.0.2", "sha256": DIGEST, "url": "https://other.invalid"},
            {"version": "9.0.2; command", "sha256": DIGEST},
            {"version": "9.0.2", "sha256": "bad"},
            [],
        ):
            with self.subTest(value=value):
                self.pin.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    freshness.load_pin(self.root)
        self.pin.write_bytes(self.original[2])

    def test_failed_pin_readback_rolls_back_original_data(self):
        original = freshness.load_pin
        calls = 0

        def fail_after_write(root):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError("synthetic pin readback failure")
            return original(root)

        with (
            patch.object(freshness, "load_pin", side_effect=fail_after_write),
            self.assertRaisesRegex(ValueError, "synthetic"),
        ):
            freshness.prepare(self.root, metadata())
        self.assert_unchanged()

    def test_proposed_pin_can_run_its_checks_and_prepare_a_later_update(self):
        freshness.prepare(self.root, metadata())
        for name in (
            "tools/dependency_freshness.py",
            "tests/test_dependency_freshness.py",
            ".github/dependabot.yml",
            ".github/workflows/dependency-freshness.yml",
        ):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / "tests/test_dependency_freshness.py"),
                "DependencyFreshnessTests.test_verified_metadata_changes_only_pin_json_and_preserves_workflow_baseline_bytes",
                "DependencyFreshnessTests.test_downgrade_and_same_version_digest_replacement_reject_but_exact_noop_is_clean",
                "-q",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_loose_python_or_npm_pins_missing_hashes_and_lock_integrity_are_rejected(self):
        cases = {
            "requirements.txt": "tzdata>=2025.3 --hash=sha256:" + DIGEST + "\n",
            "docs/requirements-dev.txt": "ruff==0.14.10\n",
            "docs/requirements-audit.in": "pip-audit>=2.10.1\n",
            "docs/requirements-properties.txt": "hypothesis==6.148.7 --hash=sha256:bad\n",
        }
        for name, text in cases.items():
            target = self.root / name
            original = target.read_bytes()
            target.write_text(text)
            with self.subTest(name=name), self.assertRaises(ValueError):
                freshness.validate_pins(self.root)
            target.write_bytes(original)
        audit_lock = self.root / "docs/requirements-audit.txt"
        original = audit_lock.read_bytes()
        exact = next(
            line
            for line in (self.root / "docs/requirements-audit.in").read_text().splitlines()
            if line.startswith("pip-audit==")
        )
        audit_lock.write_text(audit_lock.read_text().replace(exact, exact + "0", 1))
        with self.assertRaises(ValueError):
            freshness.validate_pins(self.root)
        audit_lock.write_bytes(original)
        package = self.root / "package.json"
        value = json.loads(package.read_text())
        value["devDependencies"]["eslint"] = "^9.39.1"
        package.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            freshness.validate_pins(self.root)
        shutil.copyfile(ROOT / "package.json", package)
        lock = self.root / "package-lock.json"
        value = json.loads(lock.read_text())
        value["packages"]["node_modules/eslint"].pop("integrity")
        lock.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            freshness.validate_pins(self.root)

    def test_native_proposals_audits_and_explicit_ci_dispatch_preserve_review_gates(self):
        dependabot = (ROOT / ".github/dependabot.yml").read_text()
        for item in (
            "package-ecosystem: pip",
            "directories: ['/', '/docs']",
            "package-ecosystem: npm",
            "package-ecosystem: github-actions",
        ):
            self.assertIn(item, dependabot)
        self.assertEqual(dependabot.count("interval: weekly"), 3)
        self.assertEqual(dependabot.count("open-pull-requests-limit: 2"), 3)
        source = (ROOT / ".github/workflows/dependency-freshness.yml").read_text()
        for item in (
            "--require-hashes --strict --disable-pip",
            "-r docs/requirements-audit.txt",
            "npm ci --ignore-scripts",
            "npm audit --json",
            "if: always()",
            'exit "$status"',
            "pull-requests: write",
            "actions: write",
            "refs/heads/main",
            "gh auth setup-git --hostname github.com",
            '--force-with-lease="refs/heads/$BRANCH:"',
            'gh workflow run checks.yml --repo zrk222/WMM --ref "$BRANCH" -f "base_sha=$BASE"',
        ):
            self.assertIn(item, source)
        self.assertLess(source.index("gh pr create"), source.index("gh workflow run checks.yml"))
        self.assertIn("git add -- tools/ffmpeg-pin.json", source)
        self.assertIn('[ "$(git diff --cached --name-only)" = "tools/ffmpeg-pin.json" ]', source)
        self.assertNotIn("git add -- .github", source)
        self.assertNotIn("--auto", source)
        self.assertNotIn("continue-on-error", source)
        self.assertNotIn("git merge", source)


if __name__ == "__main__":
    unittest.main()
