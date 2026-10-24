# Plan: workflow-telemetry
Spec: specs/workflow-telemetry.md
Architect verdict: PASS

## Architecture
Persist finite typed progress events alongside actual job attempts. Worker hooks
record start/terminal events; a pipeline callback emits stage start/completion.
Read-only endpoint projects fixed labels and counts from selected-app rows. A
dedicated UI module polls this endpoint with app/view/lifecycle guards. No event
is inferred from elapsed time and no completion event implies a growth result.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/workflow_telemetry.py,mission_control/db.py,mission_control/worker.py,mission_control/pipeline.py | verify=`python -m unittest tests.test_workflow_telemetry -v` | Implement actual_events and attempt_binding through real queue/SQLite callbacks.
- [x] T4 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_workflow_telemetry -v` | Expose the exact selected-app read-only scoped_monitor route.
- [x] T2 | slice=mission_control | files=mission_control/static/workflow-telemetry.js,mission_control/static/app.js,mission_control/static/index.html | verify=`node --test tests/workflow_telemetry.test.cjs` | Implement live_monitor with lifecycle-safe polling, plain stage activity and stale/retry states.
- [x] T3 | slice=tests | files=tests/test_workflow_telemetry.py,tests/workflow_telemetry.test.cjs | verify=`python -m unittest tests.test_workflow_telemetry -v` | Prove real stage events, app and attempt boundaries, public projection and frontend state behavior.

## Gates
CF doctor, strict mutations and pre-code spec/plan seals; focused worker/HTTP and
Node checks, actual desktop/mobile browser proof, Prestige checks, source mutation
and hash-bound workflow audit. Preserve parent whole-goal acceptance.
