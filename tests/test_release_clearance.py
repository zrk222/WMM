import hashlib
import importlib.util
import json
import tempfile
import unittest
from collections.abc import Callable
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("check_release_clearance", ROOT / "tools/check_release_clearance.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
snapshot = cast(Callable[[Path, str, str, int, int, str], dict[str, object]], MODULE.snapshot)
fingerprint = cast(Callable[[dict[str, object]], str], MODULE.fingerprint)
candidate_author = cast(Callable[[object, str], int], MODULE.candidate_author)
require_approval = cast(Callable[[object, int, int, int, str, str], str], MODULE.require_approval)

SHA = "a" * 40
SIGNER = "B" * 40
TAG = "v0.1.0-preview.11"
REVIEW = "c" * 64
IP = "d" * 64


def review(user_id: int = 11, login: str = "reviewer", environment: str = "release", digest: str = REVIEW) -> dict:
    return {
        "state": "approved",
        "user": {"id": user_id, "login": login, "type": "User"},
        "environments": [{"name": environment}],
        "comment": f"wmm-preview {digest} IP-CLEARED {IP}",
    }


class ReleaseClearanceTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        for name in (
            "WMM-Setup.exe",
            "wize-marketing-machine_0.1.0_amd64.deb",
            "Linux.json",
            "sbom-Windows.json",
            "sbom-Linux.json",
            "release-attestation.sigstore.json",
            "release-provenance.json",
        ):
            (self.folder / name).write_bytes(b"synthetic payload")
        self.sign()

    def sign(self) -> None:
        path = self.folder / "Windows.json"
        asset = self.folder / "WMM-Setup.exe"
        signature = {
            "thumbprint": SIGNER,
            "installer_sha256": hashlib.sha256(asset.read_bytes()).hexdigest(),
            "installer": "VALID_TIMESTAMPED",
            "uninstaller": "VALID_TIMESTAMPED",
        }
        path.write_text(json.dumps({"lifecycle": {"publisher_signature": signature}}), encoding="utf-8")

    def candidate(self, attempt: int = 1) -> str:
        return fingerprint(snapshot(self.folder, SHA, TAG, 123, attempt, SIGNER))

    def test_candidate_and_approval_do_not_need_an_in_tree_receipt(self) -> None:
        digest = self.candidate()
        self.assertEqual(require_approval([review(digest=digest)], 11, 22, 33, "owner", digest), IP)
        self.assertNotEqual(digest, self.candidate(attempt=2))

    def test_asset_replacement_and_missing_attestation_fail_closed(self) -> None:
        original = self.candidate()
        (self.folder / "WMM-Setup.exe").write_bytes(b"replacement")
        with self.assertRaisesRegex(ValueError, "publisher signatures"):
            self.candidate()
        self.sign()
        with self.assertRaisesRegex(ValueError, "independent approval"):
            require_approval([review(digest=original)], 11, 22, 33, "owner", self.candidate())
        (self.folder / "release-provenance.json").unlink()
        with self.assertRaisesRegex(ValueError, "Stage exactly"):
            self.candidate()

    def test_digest_rejects_stale_release_run(self) -> None:
        stale = self.candidate()
        with self.assertRaisesRegex(ValueError, "independent approval"):
            require_approval([review(digest=stale)], 11, 22, 33, "owner", self.candidate(attempt=2))

    def test_missing_unconfigured_self_and_wrong_environment_approvals_fail(self) -> None:
        for history in ([], [review(user_id=12)], [review(environment="stage")], [review(login="owner")]):
            with self.subTest(history=history), self.assertRaises(ValueError):
                require_approval(history, 11, 22, 33, "owner", REVIEW)
        with self.assertRaisesRegex(ValueError, "independent of the candidate author"):
            require_approval([review()], 11, 11, 33, "owner", REVIEW)

    def test_official_author_metadata_must_name_exact_candidate(self) -> None:
        self.assertEqual(candidate_author({"sha": SHA, "author": {"id": 33}}, SHA), 33)
        for metadata in (
            {"sha": "e" * 40, "author": {"id": 33}},
            {"sha": SHA, "author": None},
            {"sha": SHA, "author": {"id": True}},
        ):
            with self.subTest(metadata=metadata), self.assertRaisesRegex(ValueError, "exact candidate commit"):
                candidate_author(metadata, SHA)

    def test_candidate_author_and_unresolved_author_cannot_approve(self) -> None:
        for candidate_author in (0, 11):
            with (
                self.subTest(author=candidate_author),
                self.assertRaisesRegex(ValueError, "independent of the candidate author"),
            ):
                require_approval([review()], 11, 22, candidate_author, "owner", REVIEW)

    def test_missing_ip_clearance_bot_and_explicit_rejection_fail(self) -> None:
        no_ip = dict(review(), comment=f"wmm-preview {REVIEW}")
        bot = dict(review(), user={"id": 11, "login": "reviewer", "type": "Bot"})
        rejected = dict(review(), state="rejected")
        for approvals in ([no_ip], [bot], [review(), rejected]):
            with self.subTest(approvals=approvals), self.assertRaises(ValueError):
                require_approval(approvals, 11, 22, 33, "owner", REVIEW)

    def test_unknown_or_empty_asset_fails_exact_shape_validation(self) -> None:
        extra = self.folder / "notes.txt"
        extra.touch()
        with self.assertRaisesRegex(ValueError, "Stage exactly"):
            self.candidate()
        extra.unlink()
        (self.folder / "sbom-Linux.json").write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "Invalid prepared asset"):
            self.candidate()


if __name__ == "__main__":
    unittest.main()
