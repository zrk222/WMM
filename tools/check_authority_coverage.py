"""Enforce separate line and branch floors for each enrolled danger-zone module."""

import json
import sys
from pathlib import Path

MODULES = ("mission_control/campaign_schedule_authority.py", "mission_control/http_body.py")
LINE_FLOOR = 95
BRANCH_FLOOR = 90


def main(path: Path) -> int:
    """Reject missing measurements and compare using exact integer counts."""
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report["meta"]["branch_coverage"] is not True:
            raise ValueError("Expected branch coverage")
        files = {name.replace("\\", "/"): result for name, result in report["files"].items()}
        below_floor = False
        for module in MODULES:
            summary = files[module]["summary"]
            results = (
                ("line", summary["covered_lines"], summary["num_statements"], LINE_FLOOR),
                ("branch", summary["covered_branches"], summary["num_branches"], BRANCH_FLOOR),
            )
            for name, covered, total, floor in results:
                if type(covered) is not int or type(total) is not int or not 0 <= covered <= total or total == 0:
                    raise ValueError("Expected nonempty coverage counts")
                print(f"{module} {name}: {covered}/{total} ({100 * covered / total:.2f}%, floor {floor}%)")
                below_floor |= 100 * covered < floor * total
    except (OSError, KeyError, TypeError, ValueError):
        print("Missing or invalid danger-zone coverage", file=sys.stderr)
        return 2
    return int(below_floor)


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
