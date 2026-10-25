# Plan: automation-readiness
Spec: specs/automation-readiness.md
Architect verdict: PASS

## Architecture
Create a closed inventory module using existing operation descriptors and exact
app/owner/connection rows from one SQLite read snapshot. The module is an
executable prerequisite for the complete-automation architecture map. It neither
changes admission policy nor offers an active switch. Every existing operation
must be explicitly mapped; new catalog operations cannot silently inherit scope.
Known absent workflow execution adapters produce explicit blockers, preserving
the complete parent goal. No vault, subprocess, provider or identity-login call
is required to inspect saved public readiness facts. Report freshness and expiry
separately from actual credential availability or invocation readiness.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/automation_requirements.py | verify=`python -m unittest tests.test_automation_requirements -v` | Implement closed_inventory, inference_readiness, social_readiness and owner_inventory as read-only current-state functions.
- [x] T2 | slice=tests | files=tests/test_automation_requirements.py | verify=`python -m unittest tests.test_automation_requirements -v` | Prove exact mappings, closed selection, fresh/stale/future/expired states, selected-app ownership, current revision hashes, no writes and public projection.

## Gates
Current CF doctor, strict requirement mutation and spec/plan seals before code.
Focused SQLite tests, source mutation challenges, full unchanged-source regression,
scoped CF architecture/QA and hash-bound project-neutral workflow audit. UI,
activation, transactional admission/revocation and external acceptance remain
required by the parent complete-automation plan; no scope completion is inferred.
