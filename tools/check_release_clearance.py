"""Require a human clearance receipt for the exact public release candidate."""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "wmm.release-clearance.v1"
SHA256 = re.compile(r"[a-f0-9]{64}")
COMMIT = re.compile(r"[a-f0-9]{40}")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check(path: Path, sha: str) -> list[str]:
    if not COMMIT.fullmatch(sha):
        return ["Release clearance requires a 40-character lowercase commit SHA"]
    if not path.is_file():
        try:
            label = path.relative_to(ROOT).as_posix()
        except ValueError:
            label = str(path)
        return [f"Missing release clearance: {label}"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["Release clearance is not readable JSON"]
    if not isinstance(value, dict):
        return ["Release clearance must be a JSON object"]
    errors: list[str] = []
    if value.get("schema") != SCHEMA:
        errors.append("Release clearance schema is unsupported")
    if value.get("candidate_sha") != sha:
        errors.append("Release clearance does not name the exact candidate SHA")
    review = value.get("independent_review")
    if not isinstance(review, dict):
        errors.append("Independent human review is missing")
    else:
        if not _text(review.get("reviewer")):
            errors.append("Independent reviewer identity is missing")
        if review.get("reviewed_sha") != sha:
            errors.append("Independent review does not cover the exact candidate SHA")
        if not isinstance(review.get("pr"), int):
            errors.append("Independent review pull request number is missing")
    ip = value.get("ip_diligence")
    if not isinstance(ip, dict):
        errors.append("IP diligence is missing")
    else:
        if ip.get("status") != "CLEARED":
            errors.append("IP diligence is not cleared")
        inventory = ip.get("inventory_sha256")
        if not isinstance(inventory, str) or not SHA256.fullmatch(inventory):
            errors.append("IP diligence inventory hash is missing or malformed")
    signing = value.get("signing")
    if not isinstance(signing, dict):
        errors.append("Signing evidence is missing")
    else:
        if signing.get("windows") != "AUTHENTICODE_VERIFIED":
            errors.append("Windows Authenticode verification is not recorded")
        receipt = signing.get("verification_receipt_sha256")
        if not isinstance(receipt, str) or not SHA256.fullmatch(receipt):
            errors.append("Signing verification receipt hash is missing or malformed")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    path = ROOT / "docs/release-clearances" / (args.sha + ".json")
    errors = check(path, args.sha)
    print(
        json.dumps(
            {
                "schema": "wmm.release-clearance-check.v1",
                "sha": args.sha,
                "ok": not errors,
                "errors": errors,
            },
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
