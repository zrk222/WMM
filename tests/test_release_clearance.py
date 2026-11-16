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
SCHEMA = cast(str, MODULE.SCHEMA)
check = cast(Callable[[Path, str], list[str]], MODULE.check)

SHA = "a" * 40
HASH = "b" * 64


def receipt(sha: str = SHA) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "candidate_sha": sha,
        "independent_review": {
            "reviewer": "human-reviewer",
            "reviewed_sha": sha,
            "pr": 123,
        },
        "ip_diligence": {"status": "CLEARED", "inventory_sha256": HASH},
        "signing": {
            "windows": "AUTHENTICODE_VERIFIED",
            "verification_receipt_sha256": HASH,
        },
    }


class ReleaseClearanceTests(unittest.TestCase):
    def test_missing_and_incomplete_receipts_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / (SHA + ".json")
            self.assertEqual(
                check(path, SHA),
                [f"Missing release clearance: {path}"],
            )
            path.write_text("{}", encoding="utf-8")
            self.assertIn(
                "Release clearance schema is unsupported",
                check(path, SHA),
            )

    def test_exact_candidate_and_all_clearances_pass(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / (SHA + ".json")
            path.write_text(json.dumps(receipt()), encoding="utf-8")
            self.assertEqual(check(path, SHA), [])

    def test_changed_candidate_or_open_ip_fails(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / (SHA + ".json")
            value = cast(dict[str, object], receipt())
            value["candidate_sha"] = "c" * 40
            ip = cast(dict[str, object], value["ip_diligence"])
            ip["status"] = "OPEN"
            path.write_text(json.dumps(value), encoding="utf-8")
            errors = check(path, SHA)
            self.assertIn(
                "Release clearance does not name the exact candidate SHA",
                errors,
            )
            self.assertIn("IP diligence is not cleared", errors)


if __name__ == "__main__":
    unittest.main()
