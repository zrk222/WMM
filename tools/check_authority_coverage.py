"""Enforce separate line and branch floors for the enrolled authority module."""

import json
import sys
from pathlib import Path

MODULE = "mission_control/campaign_schedule_authority.py"
LINE_FLOOR = 85
BRANCH_FLOOR = 70


def main(path: Path) -> int:
    """Reject missing measurements and compare using exact integer counts."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["meta"]["branch_coverage"] is not True:
            raise ValueError("Expected branch coverage")
        files = {name.replace("\\", "/"): result for name, result in report["files"].items()}
        summary = files[MODULE]["summary"]
        results = (
            ("line", summary["covered_lines"], summary["num_statements"], LINE_FLOOR),
            ("branch", summary["covered_branches"], summary["num_branches"], BRANCH_FLOOR),
        )
        for name, covered, total, floor in results:
            if type(covered) is not int or type(total) is not int or not 0 <= covered <= total or total == 0:
                raise ValueError("Expected nonempty coverage counts")
            print(f"{MODULE} {name}: {covered}/{total} ({100 * covered / total:.2f}%, floor {floor}%)")
    except (OSError, KeyError, TypeError, ValueError):
        print("Missing or invalid schedule authority coverage", file=sys.stderr)
        return 2
    return int(any(100 * covered < floor * total for _, covered, total, floor in results))


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
