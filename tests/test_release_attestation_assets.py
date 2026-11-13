"""Downloadable provenance admission; synthetic gh responses are not cryptographic proof."""

import hashlib
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_desktop_release as desktop
from tests import test_verify_release_assets as offline

SHA = desktop.SHA
release = desktop.release


class AttestationAssetsTests(unittest.TestCase):
    folder: Path
    setUp = desktop.ReleaseTests.setUp

    def test_new_publication_requires_downloadable_provenance(self):
        with self.assertRaisesRegex(ValueError, "provenance"):
            release.validate_assets(self.folder, SHA, require_provenance=True)

    def test_partial_provenance_pair_is_rejected(self):
        (self.folder / "release-attestation.sigstore.json").write_text(json.dumps({"synthetic": True}))
        with self.assertRaisesRegex(ValueError, "provenance"):
            release.validate_assets(self.folder, SHA)

    def test_missing_provenance_blocks_publication_before_any_release_mutation(self):
        with (
            patch.dict(os.environ, GITHUB_REF="refs/heads/main", GITHUB_REPOSITORY=release.REPOSITORY),
            patch.object(release, "gh", side_effect=[json.dumps({"private": False}), SHA]) as gh,
            self.assertRaisesRegex(ValueError, "provenance"),
        ):
            release.publish(self.folder, SHA, desktop.TAG)
        self.assertEqual(gh.call_count, 2)
        self.assertTrue(all(call.args[0] == "api" for call in gh.call_args_list))

    def test_new_release_checksums_cover_full_bundle_and_receipt_without_self_reference(self):
        desktop.add_provenance(self.folder)
        paths = release.validate_assets(self.folder, SHA, require_provenance=True)
        self.assertEqual(len(paths), 9)
        manifest = offline.verify_release.checksums(self.folder / "SHA256SUMS.txt")
        self.assertNotIn("SHA256SUMS.txt", manifest)
        self.assertEqual(set(manifest), offline.verify_release.PAYLOADS | offline.verify_release.PROVENANCE)
        value = offline.verify_release.verify_files(paths, SHA)
        self.assertEqual(value["files"], 8)
        self.assertIn("CRYPTOGRAPHIC_VERIFICATION_NOT_RUN", value["provenance"])

    def test_resealed_changed_bundle_or_receipt_is_rejected(self):
        for corruption in ("bundle", "source", "signer", "repository", "runner", "payload", "output", "missing"):
            with self.subTest(corruption=corruption):
                desktop.add_provenance(self.folder)
                path = self.folder / "release-provenance.json"
                data = json.loads(path.read_text())
                if corruption == "bundle":
                    (self.folder / "release-attestation.sigstore.json").write_text("changed bundle")
                elif corruption == "source":
                    data["source_sha"] = "b" * 40
                elif corruption == "signer":
                    data["signer_workflow"] = "fork/WMM/.github/workflows/untrusted.yml"
                elif corruption == "repository":
                    data["repository"] = "fork/WMM"
                elif corruption == "runner":
                    data["deny_self_hosted_runners"] = False
                elif corruption == "payload":
                    data["assets"][0]["sha256"] = "0" * 64
                elif corruption == "output":
                    data["assets"][0]["verification_output"] = "[]"
                    data["assets"][0]["verification_output_sha256"] = hashlib.sha256(b"[]").hexdigest()
                else:
                    data["assets"].pop()
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):
                    release.validate_assets(self.folder, SHA, require_provenance=True)

    def test_partial_or_extra_provenance_is_not_a_legacy_download(self):
        desktop.add_provenance(self.folder)
        paths = release.validate_assets(self.folder, SHA, require_provenance=True)
        with self.assertRaisesRegex(ValueError, "exactly"):
            offline.verify_release.verify_files([p for p in paths if p.name != "release-provenance.json"], SHA)
        extra = self.folder / "unexpected-proof.json"
        extra.write_text("{}")
        with self.assertRaisesRegex(ValueError, "exactly"):
            offline.verify_release.verify_files(paths + [extra], SHA)


if __name__ == "__main__":
    unittest.main()
