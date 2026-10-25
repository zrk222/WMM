# Plan: video-edit-projects
Spec: specs/video-edit-projects.md
Architect verdict: PASS

## Architecture
Closed timeline contract and command service resolve native source IDs through
existing rights/freshness/hash checks. Append-only revisions and a mutable head
provide atomic expected-version edits and durable undo/redo. Replays return the
original revision, never silently change the current head. Shared HTTP/operation
catalog adapters call the same service. Source/rights revalidation and current
standing policy guard every transaction. Rich editor/render requirements remain.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/video_edit_contract.py | verify=`python -m unittest tests.test_video_edit_projects -v` | Implement project_state and project_edits with exact frame/transform contracts.
- [ ] T2 | slice=mission_control | files=mission_control/video_edit_projects.py,mission_control/db.py | verify=`python -m unittest tests.test_video_edit_projects -v` | Implement project_history and atomic project_conflict with current source proofs.
- [ ] T3 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/automation_requirements.py,mission_control/server.py | verify=`python -m unittest tests.test_video_edit_clients -v` | Implement project_clients parity through fixed authenticated routes.
- [ ] T5 | slice=mission_control | files=mission_control/automation_execution.py | verify=`python -m unittest tests.test_video_edit_clients -v` | Retain admitted agent/grant identity for project_clients without secret values or request-supplied provenance.
- [ ] T9 | slice=mission_control | files=mission_control/agent_review_dispatch.py | verify=`python -m unittest tests.test_video_edit_clients -v` | Preserve project_clients admitted identity after exact independent human checkpoint approval.
- [ ] T6 | slice=specs | files=specs/marketer-tool-parity.md | verify=`python -m unittest tests.test_video_edit_projects -v` | Preserve project_clients full marketer requirements and Hypit/OpenCut controls; source inventory is not execution proof.
- [ ] T7 | slice=specs | files=specs/video-edit-projects.ssat.yaml | verify=`forge qa video-edit-projects --ssat specs/video-edit-projects.ssat.yaml --root . --strict` | Hold project_state and shared service scope in the architecture contract.
- [ ] T8 | slice=smoke | files=smoke/video-edit-projects.json | verify=`forge verify-tests video-edit-projects specs/video-edit-projects.ssat.yaml --root .` | Reject hollow project_state smoke against empty service scaffolds.
- [ ] T4 | slice=tests | files=tests/test_video_edit_projects.py,tests/test_video_edit_clients.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_video_edit_projects tests.test_video_edit_clients -v` | Prove actual sources, append-only recovery, conflicts, replay and shared clients.

## Gates
CF strict and requirement mutations, spec/plan seals, source mutation evidence,
current focused tests and project-neutral workflow audit. This backend packet
does not claim human editor UI, edited MP4 execution or full editor completion.
