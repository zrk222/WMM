# Plan: video-edit-render
Spec: specs/video-edit-render.md
Architect verdict: PASS

## Architecture
Use shared project validation and exact state, existing native subprocess lifecycle,
DB/worker authority guards and fixed operation catalog. A separate immutable edit
artifact table avoids presenting native source renders as edited projects. Real
frame comparisons prove behavior, not only filter-string equality. User-facing
full controls remain next integration; this packet executes current typed edits.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/video_edit_rendering.py | verify=`python -m unittest tests.test_video_edit_render -v` | Implement edit_output with fixed internal media compilation and decoded validation.
- [ ] T2 | slice=mission_control | files=mission_control/video_edit_jobs.py,mission_control/db.py | verify=`python -m unittest tests.test_video_edit_render -v` | Implement edit_proof and edit_jobs frozen inputs, source/rights checks and artifact commit.
- [ ] T3 | slice=mission_control | files=mission_control/worker.py,mission_control/workflow_telemetry.py | verify=`python -m unittest tests.test_video_edit_render -v` | Reuse edit_jobs durable ownership, cancellation and real encoding-step telemetry.
- [ ] T4 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/automation_requirements.py,mission_control/server.py | verify=`python -m unittest tests.test_video_edit_render_clients -v` | Implement edit_clients through fixed local APIs and exact preview/download boundaries.
- [ ] T5 | slice=tests | files=tests/test_video_edit_render.py,tests/test_video_edit_render_clients.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_video_edit_render tests.test_video_edit_render_clients -v` | Prove edit_output decoded controls, edit_proof failures, cancellation and real client parity.
- [ ] T6 | slice=mission_control | files=mission_control/service.py | verify=`python -m unittest tests.test_video_edit_render_clients -v` | Reject generic edit_jobs queue bypass and require the exact validated project render request.
- [ ] T7 | slice=specs | files=specs/video-edit-render.ssat.yaml | verify=`forge qa video-edit-render --ssat specs/video-edit-render.ssat.yaml --root . --strict` | Declare edit_output compiler and durable artifact architecture.
- [ ] T8 | slice=smoke | files=smoke/video-edit-render.json | verify=`forge verify-tests video-edit-render specs/video-edit-render.ssat.yaml --root .` | Prove actual edit_output smoke rejects empty scaffolds.

## Gates
CF doctor, strict requirement mutations, task/spec/plan gates, real MP4 acceptance,
source mutations and hash-current workflow audit. Do not call complete editor,
all marketer tools or the parent goal complete from this bounded renderer.
