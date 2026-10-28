"""Refresh the current Apple schedule workflow audit bindings."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from factoryline.journey_proof import _digest

root = Path(__file__).resolve().parents[2]
audit_dir = root / ".factory/apple-analytics-t8"
contract_path = audit_dir / "workflow-audit-contract.json"
observations_path = audit_dir / "workflow-audit-observations.json"
test_log = audit_dir / "focused-ecc-tests.log"

sources = [
    ("mission_control/apple_metrics_schedule.py", "source"),
    ("mission_control/automation_health.py", "source"),
    ("mission_control/db.py", "source"),
    ("mission_control/worker.py", "source"),
    ("tests/test_apple_metrics_schedule.py", "test"),
    ("tests/test_automation_recovery.py", "test"),
    ("tests/test_play_collection.py", "test"),
    ("specs/apple-analytics-metrics.md", "contract"),
    ("plans/apple-analytics-metrics.md", "plan"),
    (".factory/apple-analytics-t8/scope-review.md", "review"),
    (".factory/apple-analytics-t8/run-focused-ecc.py", "test"),
    (".factory/apple-analytics-t8/refresh-audit.py", "audit-tool"),
]

contract = json.loads(contract_path.read_text(encoding="utf-8"))
contract["project_id"] = "WMM-apple-analytics-schedule-T8-T9"
contract["candidate"] = [
    {"path": relative, "sha256": sha256((root / relative).read_bytes()).hexdigest(), "kind": kind}
    for relative, kind in sources
]
contract_path.write_text(
    json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

observations = json.loads(observations_path.read_text(encoding="utf-8"))
observations["contract_sha256"] = sha256(contract_path.read_bytes()).hexdigest()
observations["candidate_sha256"] = _digest(contract["candidate"])
recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
artifact = {
    "path": test_log.relative_to(root).as_posix(),
    "sha256": sha256(test_log.read_bytes()).hexdigest(),
    "kind": "log",
}
for row in observations["observations"]:
    row["execution_identity"] = "python .factory/apple-analytics-t8/run-focused-ecc.py"
    row["observed_at"] = recorded_at
    row["artifacts"] = [artifact]
observations_path.write_text(
    json.dumps(observations, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-8",
)

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "factoryline.cli",
        "audit",
        "workflows",
        "--root",
        ".",
        "--contract",
        ".factory/apple-analytics-t8/workflow-audit-contract.json",
        "--observations",
        ".factory/apple-analytics-t8/workflow-audit-observations.json",
        "--json",
    ],
    cwd=root,
    capture_output=True,
    text=True,
    check=False,
)
if result.returncode:
    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    raise SystemExit(result.returncode)
receipt = json.loads(result.stdout)
(audit_dir / "workflow-audit-receipt.json").write_text(
    json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    encoding="utf-16",
)
print(f"candidate_sources={len(contract['candidate'])}")
print(f"observations={len(observations['observations'])}")
print(f"observed_at={recorded_at}")
