# Plan: native-agent-video
Spec: specs/native-agent-video.md
Architect verdict: PASS

## Architecture
Add fixed native render operations to the existing catalog/runtime. Replace the
native workflow operation blocker with actual operations and current local runtime
identity facts. Bind tool/font hashes in the summary through the shared inventory;
recheck scope before admission/worker and database commits. Existing renderer
runtime and proof checks remain authoritative. Hashing does not prove media
correctness; actual decoded renderer acceptance remains necessary.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_native_agent_video -v` | Implement native_parity and fixed native_clients routes.
- [ ] T2 | slice=mission_control | files=mission_control/automation_requirements.py,mission_control/native_runtime_identity.py,mission_control/complete_automation.py | verify=`python -m unittest tests.test_native_agent_video -v` | Implement native_readiness using current fixed runtime hashes and selected scope binding.
- [ ] T3 | slice=tests | files=tests/test_native_agent_video.py,tests/test_operation_catalog.py,tests/test_automation_requirements.py | verify=`python -m unittest tests.test_native_agent_video -v` | Prove native_parity, runtime changes, native_scope, actual clients and current source checks.
- [ ] T4 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_native_agent_video -v` | Expose the exact native history read through the shared existing app route boundary.
- [ ] T5 | slice=mission_control | files=mission_control/creative_rendering.py,mission_control/workflow_telemetry.py | verify=`python -m unittest tests.test_native_agent_video -v` | Record actual native_parity proof, screen copy, encoding and pre-commit steps with fixed public labels.

## Gates
CF doctor, strict/mutations and pre-code seals; actual native MP4 decode, scoped
SQLite/HTTP and CLI/MCP checks, source mutations and workflow audit. Parent complete
video/editor/discovery/publishing/analytics requirements remain mandatory.
