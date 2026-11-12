"""Reject newly tracked large evidence and growth in existing large evidence files."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_EVIDENCE_BYTES = 512 * 1024


def tracked_sizes(commit: str) -> dict[str, int]:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected an exact 40-character Git commit")
    data = subprocess.check_output(["git", "ls-tree", "-rlz", commit, "--", ".factory"], cwd=ROOT)
    sizes = {}
    for row in data.split(b"\0"):
        if row:
            info, path = row.split(b"\t", 1)
            size = info.split()[-1]
            if size.isdigit():
                sizes[path.decode("utf-8", errors="surrogateescape")] = int(size)
    return sizes


def oversized_additions(base: dict[str, int], candidate: dict[str, int]) -> dict[str, int]:
    return {
        path: size for path, size in sorted(candidate.items()) if size > MAX_EVIDENCE_BYTES and size > base.get(path, 0)
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="Exact base commit")
    parser.add_argument("candidate", help="Exact candidate commit")
    args = parser.parse_args()
    try:
        violations = oversized_additions(tracked_sizes(args.base), tracked_sizes(args.candidate))
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    for path, size in violations.items():
        print(f"{path!r}: {size} bytes exceeds the 512 KiB tracked evidence budget")
    if violations:
        return 1
    print("PASS: no new or enlarged oversized tracked evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
