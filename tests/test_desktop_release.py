"""Synthetic release protocol tests. No builds, credentials or network calls."""

import importlib.util
import io
import json
import os
import runpy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "wmm_release", Path(__file__).resolve().parents[1] / "tools/publish_desktop_release.py"
)
assert spec is not None and spec.loader is not None
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

SHA = "a" * 40
TAG = "v0.1.0-preview.1"


def add_provenance(folder, sha=SHA):
    """Create fixture-only downloadable evidence through the actual staging path."""
    verifier = runpy.run_path(str(Path(__file__).resolve().parents[1] / "tools/verify_release_provenance.py"))
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        stage = root / "stage"
        stage.mkdir()
        for name in verifier["payload_names"]():
            shutil.copyfile(folder / name, stage / name)
        bundle = root / "action-bundle.json"
        bundle.write_text('{"synthetic":"not cryptographic evidence"}')

        def fake_verify(args, **kwargs):
            path = Path(args[3])
            output = [
                {
                    "attestation": {"bundle": "synthetic fixture"},
                    "verificationResult": {
                        "statement": {
                            "predicateType": verifier["PREDICATE"],
                            "subject": [{"name": path.name, "digest": {"sha256": release.digest(path)}}],
                        }
                    },
                }
            ]
            return subprocess.CompletedProcess(args, 0, json.dumps(output), "")

        with patch("subprocess.run", side_effect=fake_verify):
            verifier["verify"](stage, sha, root / "receipt.json", bundle)
        for name in (verifier["BUNDLE_NAME"], verifier["RECEIPT_NAME"]):
            shutil.copyfile(stage / name, folder / name)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        for platform, name in release.ASSETS.items():
            prefix = "windows" if platform == "Windows" else "ubuntu"
            for phase in ("fresh", "upgrade"):
                evidence = self.folder / (prefix + "-" + phase) / "evidence.json"
                evidence.parent.mkdir()
                evidence.write_text(
                    json.dumps(
                        dict(
                            github_sha=SHA,
                            offline_restart="PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE",
                            network="BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE",
                        )
                    )
                )
            asset = self.folder / name
            asset.write_bytes(b"synthetic installer " + platform.encode())
            result = self.folder / "lifecycle.json"
            result.write_text(
                json.dumps(
                    dict(
                        status="PASS",
                        install="VERIFIED",
                        upgrade="VERIFIED",
                        uninstall="VERIFIED",
                        removal="VERIFIED",
                        workspace="SYNTHETIC_PRESERVED",
                    )
                )
            )
            release.receipt(platform, SHA, asset, result, self.folder / (platform + ".json"), self.folder)
            (self.folder / ("sbom-" + platform + ".json")).write_text(
                json.dumps(
                    dict(
                        bomFormat="CycloneDX",
                        specVersion="1.5",
                        version=1,
                        metadata=dict(
                            component=dict(
                                type="application",
                                name="wmm",
                                version=SHA,
                                properties=[
                                    dict(name="wmm:platform", value=platform),
                                    dict(name="wmm:inventory_scope", value="build_environment"),
                                ],
                            )
                        ),
                        components=[],
                    )
                )
            )

    def test_both_passed_assets_and_manifest(self):
        paths = release.validate_assets(self.folder, SHA)
        self.assertEqual(len(paths), 7)
        manifest = (self.folder / "SHA256SUMS.txt").read_text()
        for name in release.ASSETS.values():
            self.assertIn(release.digest(self.folder / name) + "  " + name, manifest)

    def test_missing_or_stale_sbom_refused(self):
        (self.folder / "sbom-Linux.json").unlink()
        with self.assertRaises(ValueError):
            release.validate_assets(self.folder, SHA)
        path = self.folder / "sbom-Windows.json"
        value = json.loads(path.read_text())
        value["metadata"]["component"]["version"] = "b" * 40
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            release.validate_assets(self.folder, SHA)

    def test_duplicate_sbom_property_rejected_before_publication(self):
        path = self.folder / "sbom-Windows.json"
        value = json.loads(path.read_text())
        properties = value["metadata"]["component"]["properties"]
        properties.append(properties[0])
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "duplicated"):
            release.validate_assets(self.folder, SHA)

    def test_missing_platform_refused(self):
        (self.folder / "Linux.json").unlink()
        with self.assertRaises(ValueError):
            release.validate_assets(self.folder, SHA)

    def test_changed_installer_refused(self):
        (self.folder / "WMM-Setup.exe").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            release.validate_assets(self.folder, SHA)

    def test_failed_missing_and_stale_receipts_refused(self):
        path = self.folder / "Windows.json"
        original = json.loads(path.read_text())
        for field, value in [("status", "FAIL"), ("source_sha", "b" * 40), ("asset", "../escape")]:
            path.write_text(json.dumps(dict(original, **{field: value})))
            with self.assertRaises(ValueError):
                release.validate_assets(self.folder, SHA)
        original["lifecycle"]["upgrade"] = "FAIL"
        path.write_text(json.dumps(original))
        with self.assertRaises(ValueError):
            release.validate_assets(self.folder, SHA)

    def test_incomplete_lifecycle_cannot_be_sealed(self):
        path = self.folder / "lifecycle.json"
        path.write_text(json.dumps(dict(status="PASS")))
        with self.assertRaises(ValueError):
            release.receipt("Windows", SHA, self.folder / "WMM-Setup.exe", path, self.folder / "new.json")

    def test_missing_restart_evidence_refused(self):
        (self.folder / "windows-upgrade/evidence.json").unlink()
        with self.assertRaises(FileNotFoundError):
            release.receipt(
                "Windows",
                SHA,
                self.folder / "WMM-Setup.exe",
                self.folder / "lifecycle.json",
                self.folder / "new.json",
                self.folder,
            )

    def test_target_ref_repository_tag_and_exact_sha(self):
        good = [SHA, SHA, "refs/heads/main", release.REPOSITORY, TAG]
        release.validate_target(*good)
        for index, value in [
            (0, "main"),
            (1, "b" * 40),
            (2, "refs/heads/feature"),
            (3, "fork/WMM"),
            (4, "--clobber"),
            (4, "v1.2.3/escape"),
        ]:
            bad = good.copy()
            bad[index] = value
            with self.assertRaises(ValueError):
                release.validate_target(*bad)

    def fake_gh(self, *args):
        self.calls.append(args)
        if args[:2] == ("api", "repos/" + release.REPOSITORY):
            return json.dumps(dict(private=False))
        if "--jq" in args:
            return SHA
        if "matching-refs" in " ".join(args):
            return json.dumps(self.refs)
        if "--paginate" in args:
            return " [[]]"
        if args[:2] == ("release", "view"):
            return json.dumps(
                dict(
                    isDraft=True,
                    isPrerelease=True,
                    targetCommitish=SHA,
                    assets=[
                        dict(name=p.name, size=p.stat().st_size) for p in release.validate_assets(self.folder, SHA)
                    ],
                )
            )
        return ""

    def test_existing_tag_refused_before_any_mutation(self):
        add_provenance(self.folder)
        self.calls, self.refs = [], [dict(ref="refs/tags/" + TAG)]
        with (
            patch.dict(os.environ, GITHUB_REF="refs/heads/main", GITHUB_REPOSITORY=release.REPOSITORY),
            patch.object(release, "gh", self.fake_gh),
            self.assertRaises(ValueError),
        ):
            release.publish(self.folder, SHA, TAG)
        self.assertFalse(any(c[0] == "release" for c in self.calls))

    def test_upload_failure_preserves_draft_and_never_clobbers(self):
        add_provenance(self.folder)
        self.calls, self.refs = [], []

        def failed_upload(*args):
            if args[:2] == ("release", "upload"):
                self.calls.append(args)
                raise RuntimeError("synthetic interrupted upload")
            return self.fake_gh(*args)

        with (
            patch.dict(os.environ, GITHUB_REF="refs/heads/main", GITHUB_REPOSITORY=release.REPOSITORY),
            patch.object(release, "gh", failed_upload),
            self.assertRaises(RuntimeError),
        ):
            release.publish(self.folder, SHA, TAG)
        self.assertTrue(any(c[:2] == ("release", "create") and "--draft" in c for c in self.calls))
        self.assertFalse(any(c[:2] == ("release", "edit") for c in self.calls))
        self.assertNotIn("--clobber", str(self.calls))

    def test_private_repository_refused(self):
        with (
            patch.object(release, "gh", side_effect=[json.dumps(dict(private=True)), SHA]),
            patch.dict(os.environ, GITHUB_REF="refs/heads/main", GITHUB_REPOSITORY=release.REPOSITORY),
            self.assertRaises(ValueError),
        ):
            release.publish(self.folder, SHA, TAG)

    def test_publication_requires_full_anonymous_download_hashes(self):
        add_provenance(self.folder)
        self.calls, self.refs = [], []
        urls = []

        def download(url, timeout):
            urls.append(url)
            return io.BytesIO((self.folder / url.rsplit("/", 1)[-1]).read_bytes())

        with (
            patch.dict(os.environ, GITHUB_REF="refs/heads/main", GITHUB_REPOSITORY=release.REPOSITORY),
            patch.object(release, "gh", self.fake_gh),
            patch.object(release, "urlopen", download),
        ):
            release.publish(self.folder, SHA, TAG)
        self.assertEqual(len(urls), 9)
        self.assertTrue(all(url.startswith("https://github.com/zrk222/WMM/releases/download/") for url in urls))
        self.assertTrue(any(c[:2] == ("release", "edit") for c in self.calls))


if __name__ == "__main__":
    unittest.main()
