# Plan: hypit-durable-jobs
Spec: specs/hypit-durable-jobs.md
Architect verdict: PASS

## Architecture
Add a separate Hypit persistence service and tables. Queue frozen validated current
brief requests through the existing worker. Persist a private attempt before any
external process, then durably attach its build identity. An uncertain retained
attempt blocks repeat submission. Completed artifacts are app-scoped, immutable,
checksum checked and committed only while both proof and job ownership remain
current. Replay returns verified saved output. This design uses only declarative
local composition and grants no arbitrary code execution or provider access.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_jobs.py,mission_control/db.py,mission_control/worker.py | verify=`python -m unittest tests.test_hypit_jobs -v` | Implement queue_identity, durable_attempt, restart_boundary, atomic_artifact and artifact_scope using the existing owned runtime.
- [ ] T2 | slice=tests | files=tests/test_hypit_jobs.py | verify=`python -m unittest tests.test_hypit_jobs -v` | Prove actual worker and SQLite lifecycle, negative state/byte/app checks and no duplicate submission after recovery.

## Integration still required
The parent goal retains first-class UI and explanations, complete human/agent
editing controls, source approval, selected-agent authoring, CLI/MCP operations,
portable source/media, KPI capture and PDF exports. This packet does not replace
those requirements or establish whole-product readiness.
