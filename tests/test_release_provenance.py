"""Exercise provenance admission with a fake official verifier; no cryptographic claims."""

import hashlib
import importlib.util
import io
import json
import runpy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("verify_release_provenance", ROOT / "tools/verify_release_provenance.py")
assert SPEC and SPEC.loader
provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provenance)
SHA = "a" * 40


class ReleaseProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / "release-assets"
        self.folder.mkdir()
        for name in provenance.payload_names():
            (self.folder / name).write_bytes(b"synthetic release payload: " + name.encode("ascii"))
        self.receipt = self.root / "proof" / "receipt.json"
        self.calls: list[list[str]] = []
        self.hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in self.folder.iterdir()}

    def output(self, path: Path) -> str:
        return json.dumps(
            [
                {
                    "attestation": {"bundle": "synthetic verifier fixture"},
                    "verificationResult": {
                        "statement": {
                            "predicateType": "https://slsa.dev/provenance/v1",
                            "subject": [{"name": path.name, "digest": {"sha256": self.hashes[path.name]}}],
                        }
                    },
                }
            ]
        )

    def successful_verifier(self, args, **kwargs):
        self.calls.append(args)
        self.assertEqual(args[:3], ["gh", "attestation", "verify"])
        self.assertEqual(kwargs["encoding"], "utf-8")
        self.assertEqual(kwargs["timeout"], 120)
        self.assertTrue(kwargs["capture_output"])
        self.assertFalse(kwargs["check"])
        return subprocess.CompletedProcess(args, 0, self.output(Path(args[3])), "")

    def test_six_official_verifier_calls_bind_exact_repo_signer_source_and_digests(self):
        with patch.object(provenance.subprocess, "run", side_effect=self.successful_verifier):
            receipt = provenance.verify(self.folder, SHA, self.receipt)
        self.assertEqual(len(self.calls), 6)
        for args in self.calls:
            self.assertEqual(
                args[4:],
                [
                    "--hostname",
                    "github.com",
                    "--repo",
                    "zrk222/WMM",
                    "--signer-workflow",
                    "zrk222/WMM/.github/workflows/desktop-release.yml",
                    "--source-digest",
                    SHA,
                    "--deny-self-hosted-runners",
                    "--format",
                    "json",
                ],
            )
        self.assertEqual({row["name"]: row["sha256"] for row in receipt["assets"]}, self.hashes)
        self.assertTrue(all(row["verification_count"] == 1 for row in receipt["assets"]))
        self.assertEqual(receipt["source_sha"], SHA)
        self.assertEqual(json.loads(self.receipt.read_text()), receipt)
        self.assertFalse((self.folder / "SHA256SUMS.txt").exists())
        publisher = runpy.run_path(str(ROOT / "tools/publish_desktop_release.py"))
        assets = publisher["ASSETS"]
        expected = (
            set(assets.values())
            | {platform + ".json" for platform in assets}
            | {"sbom-" + platform + ".json" for platform in assets}
        )
        self.assertEqual(provenance.payload_names(), expected)

    def test_missing_empty_directory_and_extra_files_reject_before_verifier(self):
        for changed in ("missing", "empty", "directory", "extra", "checksum"):
            with self.subTest(changed=changed):
                path = self.folder / "Windows.json"
                original = path.read_bytes()
                if changed in ("missing", "directory"):
                    path.unlink()
                    if changed == "directory":
                        path.mkdir()
                elif changed == "empty":
                    path.write_bytes(b"")
                else:
                    (self.folder / ("unexpected.txt" if changed == "extra" else "SHA256SUMS.txt")).write_text(
                        "synthetic"
                    )
                with patch.object(provenance.subprocess, "run") as run, self.assertRaises(ValueError):
                    provenance.verify(self.folder, SHA, self.receipt)
                run.assert_not_called()
                self.assertFalse(self.receipt.exists())
                if path.is_dir():
                    path.rmdir()
                path.write_bytes(original)
                for extra in ("unexpected.txt", "SHA256SUMS.txt"):
                    (self.folder / extra).unlink(missing_ok=True)

    def test_symlink_payload_is_rejected(self):
        path = self.folder / "Windows.json"
        original = path.read_bytes()
        target = self.root / "outside.json"
        target.write_bytes(original)
        path.unlink()
        try:
            path.symlink_to(target)
        except OSError:
            self.skipTest("Host does not permit creating a synthetic symlink")
        with patch.object(provenance.subprocess, "run") as run, self.assertRaises(ValueError):
            provenance.verify(self.folder, SHA, self.receipt)
        run.assert_not_called()

    def test_invalid_source_and_receipt_inside_stage_reject_before_verifier(self):
        for sha, receipt in (("main", self.receipt), (SHA.upper(), self.receipt), (SHA, self.folder / "proof.json")):
            with self.subTest(sha=sha, receipt=receipt):
                with patch.object(provenance.subprocess, "run") as run, self.assertRaises(ValueError):
                    provenance.verify(self.folder, sha, receipt)
                run.assert_not_called()

    def test_corrupt_asset_fails_verifier_and_stops_all_remaining_calls(self):
        (self.folder / "Linux.json").write_bytes(b"corrupted synthetic bytes")
        with (
            patch.object(provenance.subprocess, "run", side_effect=self.successful_verifier),
            self.assertRaisesRegex(RuntimeError, "no valid payload proof"),
        ):
            provenance.verify(self.folder, SHA, self.receipt)
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(self.receipt.exists())

    def test_provider_failure_and_malformed_or_empty_results_never_create_receipt(self):
        for code, output in (
            (1, "private token"),
            (0, None),
            (0, ""),
            (0, "[]"),
            (0, "{}"),
            (0, "[{}]"),
            (0, "not JSON"),
        ):
            with self.subTest(code=code, output=output):
                result = subprocess.CompletedProcess([], code, output, "private token")
                with (
                    patch.object(provenance.subprocess, "run", return_value=result) as run,
                    self.assertRaisesRegex(RuntimeError, "^Official provenance verifier"),
                ):
                    provenance.verify(self.folder, SHA, self.receipt)
                self.assertEqual(run.call_count, 1)
                self.assertFalse(self.receipt.exists())

    def test_changed_bytes_during_verification_and_later_asset_processing_are_rejected(self):
        for timing in ("during", "later"):
            with self.subTest(timing=timing):
                self.calls.clear()
                for name in self.hashes:
                    (self.folder / name).write_bytes(b"synthetic release payload: " + name.encode("ascii"))

                def mutating_verifier(args, _timing=timing, **kwargs):
                    result = self.successful_verifier(args, **kwargs)
                    if _timing == "during" or len(self.calls) == 6:
                        (self.folder / "Linux.json").write_bytes(b"changed after verification")
                    return result

                with (
                    patch.object(provenance.subprocess, "run", side_effect=mutating_verifier),
                    self.assertRaisesRegex(ValueError, "changed"),
                ):
                    provenance.verify(self.folder, SHA, self.receipt)
                self.assertFalse(self.receipt.exists())

    def test_timeout_and_decode_failures_are_private_and_block_cli_readiness(self):
        for error in (
            subprocess.TimeoutExpired("synthetic verifier", 120),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "private token"),
        ):
            with self.subTest(error=type(error).__name__):
                with (
                    patch.object(provenance.subprocess, "run", side_effect=error),
                    patch.object(
                        sys,
                        "argv",
                        ["verify", "--folder", str(self.folder), "--sha", SHA, "--receipt", str(self.receipt)],
                    ),
                    patch("sys.stdout", new_callable=io.StringIO) as output,
                ):
                    self.assertEqual(provenance.main(), 1)
                self.assertEqual(output.getvalue(), "Release provenance verification failed; publication is blocked\n")
                self.assertFalse(self.receipt.exists())

    def test_existing_receipt_is_not_overwritten(self):
        self.receipt.parent.mkdir()
        self.receipt.write_text("prior evidence")
        with patch.object(provenance.subprocess, "run") as run, self.assertRaises(ValueError):
            provenance.verify(self.folder, SHA, self.receipt)
        run.assert_not_called()
        self.assertEqual(self.receipt.read_text(), "prior evidence")

    def test_workflow_attests_verifies_and_uploads_proof_before_immutable_publish(self):
        source = (ROOT / ".github/workflows/desktop-release.yml").read_text(encoding="utf-8")
        self.assertIn("actions/attest-build-provenance@96278af6caaf10aea03fd8d33a09a777ca52d62f", source)
        self.assertLess(
            source.index("name: Attest release asset provenance"),
            source.index("run: python tools/verify_release_provenance.py"),
        )
        self.assertLess(
            source.index("run: python tools/verify_release_provenance.py"),
            source.index("name: verified-release-provenance-"),
        )
        self.assertLess(
            source.index("name: verified-release-provenance-"),
            source.index("run: python tools/publish_desktop_release.py publish"),
        )
        self.assertIn('--folder release-assets --sha "$CANDIDATE"', source)
        self.assertIn("path: .factory/release-provenance.json", source)
        self.assertIn("id: provenance", source)
        self.assertIn("ATTESTATION_BUNDLE: ${{ steps.provenance.outputs.bundle-path }}", source)
        self.assertIn('--bundle "$ATTESTATION_BUNDLE"', source)
        self.assertNotIn("continue-on-error", source)

    def test_action_bundle_is_verified_for_every_payload_and_staged_byte_for_byte(self):
        bundle = self.root / "official-action-bundle.json"
        original = b'{"synthetic": "bundle bytes, not cryptographic proof"}\n'
        bundle.write_bytes(original)
        with patch.object(provenance.subprocess, "run", side_effect=self.successful_verifier):
            receipt = provenance.verify(self.folder, SHA, self.receipt, bundle)
        self.assertEqual(len(self.calls), 6)
        for args in self.calls:
            self.assertEqual(args[-2:], ["--bundle", str(bundle.resolve())])
            self.assertIn("--deny-self-hosted-runners", args)
            self.assertEqual(args[args.index("--source-digest") + 1], SHA)
        self.assertEqual((self.folder / provenance.BUNDLE_NAME).read_bytes(), original)
        self.assertEqual(json.loads((self.folder / provenance.RECEIPT_NAME).read_text()), receipt)
        self.assertEqual(receipt["schema"], "wmm.release-provenance.v2")
        self.assertEqual(
            receipt["bundle"],
            {
                "name": provenance.BUNDLE_NAME,
                "sha256": hashlib.sha256(original).hexdigest(),
            },
        )
        self.assertTrue(receipt["deny_self_hosted_runners"])
        for asset in receipt["assets"]:
            self.assertEqual(asset["verification_output"], self.output(self.folder / asset["name"]))
            self.assertEqual(
                asset["verification_output_sha256"],
                hashlib.sha256(asset["verification_output"].encode("utf-8")).hexdigest(),
            )
        self.assertFalse((self.folder / "SHA256SUMS.txt").exists())

    def test_changed_bundle_or_failed_verifier_never_stages_provenance(self):
        bundle = self.root / "official-action-bundle.json"
        for cause in ("changed", "failed"):
            with self.subTest(cause=cause):
                bundle.write_text("synthetic bundle")
                self.calls.clear()

                def verifier(args, _cause=cause, **kwargs):
                    result = self.successful_verifier(args, **kwargs)
                    if _cause == "changed":
                        bundle.write_text("changed bundle")
                        return result
                    return subprocess.CompletedProcess(args, 1, "private failure", "")

                with (
                    patch.object(provenance.subprocess, "run", side_effect=verifier),
                    self.assertRaises((ValueError, RuntimeError)),
                ):
                    provenance.verify(self.folder, SHA, self.receipt, bundle)
                self.assertFalse((self.folder / provenance.BUNDLE_NAME).exists())
                self.assertFalse((self.folder / provenance.RECEIPT_NAME).exists())
                self.assertFalse(self.receipt.exists())

    def test_buyer_commands_preserve_source_signer_constraints_and_unsigned_limits(self):
        guide = (ROOT / "docs/VERIFY-RELEASE.md").read_text(encoding="utf-8")
        for text in (
            "gh attestation verify",
            "--repo zrk222/WMM",
            "--signer-workflow zrk222/WMM/.github/workflows/desktop-release.yml",
            '--source-digest "$SOURCE_SHA"',
            "--deny-self-hosted-runners",
            "checksum file itself has no provenance attestation",
            "unsigned-installer trust prompts",
            "reproducible builds",
        ):
            self.assertIn(text, guide)
        handoff = (ROOT / "docs/release-handoff.md").read_text(encoding="utf-8")
        self.assertIn(".factory/release-provenance.json", handoff)
        self.assertIn("not itself attested", handoff)


if __name__ == "__main__":
    unittest.main()
