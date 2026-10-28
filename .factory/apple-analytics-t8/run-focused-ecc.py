"""Run hash-bound Apple schedule and manifest regression suites."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
log_path = root / ".factory/apple-analytics-t8/focused-ecc-tests.log"
command = [
    sys.executable,
    "-m",
    "unittest",
    "tests.test_automation_recovery",
    "tests.test_apple_metrics_schedule",
    "tests.test_play_collection",
    "-v",
]
with log_path.open("wb") as log:
    result = subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=False)
print(f"exit_code={result.returncode}")
print(f"log={log_path.relative_to(root).as_posix()}")
raise SystemExit(result.returncode)
