"""Apply Python complexity ceilings with explicit legacy limits."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET = "tools/python-complexity-budget.json"
GENERATED = "mission_control/schema_types.py"
DIAGNOSTIC = re.compile(r"`([^`]+)` is too complex \((\d+) > 10\)")


def function_scores() -> dict[str, int]:
    """Use the pinned Ruff parser and reject malformed diagnostics."""
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--isolated",
            "--no-cache",
            "--ignore-noqa",
            "--no-respect-gitignore",
            "--select",
            "C901",
            "--output-format",
            "json",
            "mission_control",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode not in (0, 1):
        raise ValueError(f"Ruff complexity check failed: {run.stderr.strip()}")
    scores: dict[str, int] = {}
    for item in json.loads(run.stdout):
        match = DIAGNOSTIC.fullmatch(item["message"])
        if item["code"] != "C901" or match is None:
            raise ValueError("Unexpected Ruff complexity diagnostic")
        path = Path(item["filename"]).relative_to(ROOT).as_posix()
        key = f"{path}:{match[1]}"
        score = int(match[2])
        if score > 25 and scores.get(key, 0) > 25:
            raise ValueError(f"Multiple functions share an over-budget name: {key}")
        scores[key] = max(scores.get(key, 0), score)
    return scores


def module_sizes() -> dict[str, int]:
    """Measure physical lines in the Python runtime including newly added modules."""
    return {
        path.relative_to(ROOT).as_posix(): len(path.read_bytes().splitlines())
        for path in (ROOT / "mission_control").rglob("*.py")
        if path.relative_to(ROOT).as_posix() != GENERATED
    }


def verify(observed: dict[str, int], allowed: dict[str, int], warn: int, fail: int, kind: str) -> list[str]:
    """Report new debt and require reduced or resolved legacy entries to be updated."""
    errors = []
    for key in sorted(observed.keys() | allowed.keys()):
        value = observed.get(key, 0)
        ceiling = allowed.get(key, fail)
        if value > ceiling:
            errors.append(f"{kind} {key}: {value} exceeds {ceiling}")
        elif key in allowed and (ceiling <= fail or value < ceiling):
            errors.append(f"{kind} {key}: reduce or remove legacy ceiling {ceiling}; now {value}")
        elif value > warn and key in allowed:
            print(f"Legacy {kind}: {key} ({value}, ceiling {ceiling})")
    warnings = sum(warn < value <= fail for value in observed.values())
    print(f"{kind}: {warnings} above advisory threshold {warn} and at or below {fail}")
    return errors


def legacy_limits(base: str) -> dict[str, dict[str, int]]:
    """Read the original ceilings from the verified base revision."""
    if re.fullmatch(r"[0-9a-f]{40}", base) is None:
        raise ValueError("Expected exact base commit")
    prior = subprocess.run(["git", "show", f"{base}:{BUDGET}"], cwd=ROOT, capture_output=True, text=True, check=False)
    if prior.returncode == 0:
        return json.loads(prior.stdout)
    files = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", base, "--", BUDGET], cwd=ROOT, text=True)
    if files:
        raise ValueError("Cannot read existing budget")
    return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    base = parser.parse_args().base
    baseline = json.loads((ROOT / BUDGET).read_text(encoding="utf-8"))
    prior = legacy_limits(base)
    errors = []
    for category in ("functions", "modules"):
        if prior:
            errors.extend(
                f"{key}: cannot add or raise a legacy ceiling"
                for key, ceiling in baseline[category].items()
                if ceiling > prior[category].get(key, 0)
            )
    errors.extend(verify(function_scores(), baseline["functions"], 15, 25, "Complexity"))
    errors.extend(verify(module_sizes(), baseline["modules"], 600, 1000, "Module lines"))
    if errors:
        print("\n".join(errors), file=sys.stderr)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
