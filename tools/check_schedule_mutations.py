"""Challenge selected schedule authority decisions in a fresh local test process."""

import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mission_control import campaign_schedule_authority as authority
from tests.test_schedule_authority_boundary import ScheduleAuthorityBoundaryTests

CHECKS = {
    "batch": (
        'if summary["batch_id"] != row["batch_id"]:',
        "if False:",
        "test_a_matching_scope_cannot_authorize_a_different_batch",
    ),
    "approval": (
        'summary["scope_hash"] != scope["approval_hash"]',
        "False",
        "test_a_matching_batch_cannot_replace_scope_approval",
    ),
    "deadline": (
        "iso_time(expiry).timestamp() <= time.time()",
        "iso_time(expiry).timestamp() < time.time()",
        "test_reviewed_deadline_denies_at_equality",
    ),
    "lease": ('row["lease"] <= time.time()', 'row["lease"] < time.time()', "test_worker_lease_denies_at_equality"),
}


def run_witness(test: str) -> tuple[unittest.TestResult, str]:
    output = io.StringIO()
    suite = unittest.TestSuite([ScheduleAuthorityBoundaryTests(test)])
    result = unittest.TextTestRunner(stream=output).run(suite)
    return result, output.getvalue()


def main() -> int:
    source_path = Path(authority.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    failed = False
    import tests.test_schedule_authority_boundary as witnesses

    for name, (original, replacement, test) in CHECKS.items():
        if source.count(original) != 1:
            print(f"{name}: expected exactly one reviewed mutation site", file=sys.stderr)
            return 2
        changed = compile(source.replace(original, replacement, 1), str(source_path), "exec")
        environment = vars(authority).copy()
        exec(changed, environment)  # noqa: S102 - fixed mutation of local checked-out source in this test process
        function = "check_lease" if name == "lease" else "check_deadline" if name == "deadline" else "check_scope"
        baseline, log = run_witness(test)
        if baseline.testsRun != 1 or not baseline.wasSuccessful() or baseline.skipped:
            print(log, file=sys.stderr)
            return 2
        original_function = getattr(witnesses, function)
        try:
            setattr(witnesses, function, environment[function])
            result, log = run_witness(test)
        finally:
            setattr(witnesses, function, original_function)
        killed = (
            result.testsRun == 1
            and len(result.failures) == 1
            and not result.errors
            and "PermissionError not raised" in result.failures[0][1]
        )
        print(f"{name}: {'KILLED' if killed else 'NOT KILLED'}")
        if not killed:
            print(log, file=sys.stderr)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
