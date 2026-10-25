# Plan: automation-standing-authority
Spec: specs/automation-standing-authority.md
Architect verdict: PASS

## Architecture
The executable readiness map now covers every fixed operation and retains blockers
for all incomplete families. Build standing policy, exact summary and grant links
on this map. Reuse one DB transaction for owner confirmation and admission. The
central connection context is the interlock for existing fixed local services;
all current SQLite connections use it. Context is request/worker-local, not a
global administrator flag. Domain writes recheck the same policy before commit.
Queue links persist within enqueue; worker dispatch and commits inherit authority.
Policy/grant/control and result-recording transactions execute outside domain
context, preserving revocation and uncertainty receipts. No new external effect
adapter is enabled. Existing manual grants and jobs retain existing behavior.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/complete_automation.py,mission_control/automation_requirements.py,mission_control/db.py | verify=`python -m unittest tests.test_complete_automation -v` | Implement scope_confirmation, atomic_activation and execution_receipts with exact versioned policy/grant/summary bindings and shared inventory snapshot.
- [ ] T2 | slice=mission_control | files=mission_control/automation_execution.py,mission_control/agent_grants.py,mission_control/agent_grant_http.py,mission_control/worker.py | verify=`python -m unittest tests.test_automation_execution -v` | Implement bounded_admission, commit_interlock and worker_scope with durable job links and source-scoped execution context.
- [ ] T3 | slice=tests | files=tests/test_complete_automation.py,tests/test_automation_execution.py,tests/test_automation_requirements.py | verify=`python -m unittest tests.test_complete_automation tests.test_automation_execution tests.test_automation_requirements -v` | Prove every scenario, owner/bearer separation, scope and credential races, queued revocation, uncertain outcomes and unchanged legacy operation behavior.
- [ ] T4 | slice=docs | files=docs/complete-automation-authority.md | verify=`python tools/check_distribution.py` | Record implemented local standing authority accurately while retaining the pending owner UI, full-domain adapters and report requirements.
- [ ] T5 | slice=plans | files=plans/complete-automation.md | verify=`python tools/check_distribution.py` | Update the parent prerequisite status without claiming the complete owner UI and full-domain feature is delivered.

## Gates
CF doctor and pre-code spec/plan seals; strict requirement mutations; actual
isolated SQLite and HTTP gateway tests; deterministic owner/access test adapters;
source mutants, unchanged-source regression and workflow evidence audit. Verify
actual UI, live provider acceptance and parent full-domain scope separately.
