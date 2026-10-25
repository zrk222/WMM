# Plan: hypit-workflow-interface
Spec: specs/hypit-workflow-interface.md
Architect verdict: PASS

## Architecture
Use the existing validated Hypit service and fixed operation catalog. Add a
workspace history entry and exact routes for queue and scoped byte delivery.
Reuse current video range response behavior with a fixed internal renderer
selection. Native routes stay unchanged. The client renderer selector chooses
one of two fixed endpoints, not a path supplied by an agent. CLI/MCP derive their
tools from the shared catalog. Domain validation remains server authoritative.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_jobs.py,mission_control/service.py,mission_control/server.py | verify=`python -m unittest tests.test_hypit_interface -v` | Implement workspace_history, shared_queue and artifact_delivery using existing scope and artifact checks.
- [ ] T2 | slice=mission_control | files=mission_control/static/creative-rendering.js | verify=`node --test tests/hypit-interface.test.js` | Implement renderer_choice, actual saved Hypit history, preview/download and job cancellation with plain output explanations and current app binding.
- [ ] T3 | slice=tests | files=tests/test_hypit_interface.py,tests/hypit-interface.test.js,tests/test_hypit_jobs.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_hypit_interface -v` | Prove source-scoped HTTP, range/download, native compatibility, bearer scopes and two client adapters; keep launcher fixture and catalog count current; run browser and accessibility proof separately.
- [ ] T4 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_hypit_interface -v` | Implement agent_interface in the existing shared catalog and domain dispatcher.

## Gates
CF strict/mutations and seals before implementation. Focused real HTTP and client
tests, current browser/desktop/mobile evidence, Prestige audits, existing frontend
and Python regressions, source mutations and hash-bound workflow audit. Full
autonomy and parent video functionality remain required; these routes are a
dependency for operation coverage, not a completed whole-product claim.
