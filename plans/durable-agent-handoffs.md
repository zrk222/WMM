# Plan: durable-agent-handoffs
Spec: specs/durable-agent-handoffs.md
Architect verdict: PASS

## Architecture
Use immutable closed canonical worker-job context with a separate mutable revocation and single-claim lifecycle. Owner and scoped grant checks reuse existing SQLite transactions and role verification. Raw request keys remain only in the job ledger; handoffs expose a digest. No handoff performs job enqueue or provider dispatch or transfers authority. Resume returns original identifiers and status; ordinary downstream operations retain their own authority and review checks.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/agent_handoffs.py,mission_control/db.py,tests/test_agent_handoffs.py | verify=`python -m unittest tests.test_agent_handoffs -v` | Implement handoff_create, handoff_validation, handoff_admission, handoff_recovery, handoff_privacy and handoff_authority.
- [ ] T2 | slice=mission_control | files=mission_control/agent_grant_http.py,mission_control/server.py,mission_control/operation_catalog.py,tests/test_agent_handoff_clients.py | verify=`python -m unittest tests.test_agent_handoff_clients -v` | Implement handoff_clients using the same domain and explicit owner or scoped authority.
- [ ] T3 | slice=mission_control | files=mission_control/static/agent-access.js,mission_control/personal_agent_profiles.py,tests/agent-handoffs-ui.test.js,tests/test_personal_agent_profiles.py | verify=`node --test tests/agent-handoffs-ui.test.js` | Present bounded provenance, status and next action without secrets or vendor API claims.
- [ ] T4 | slice=ios | files=ios/WMM/Agents/NativeAgentAccessView.swift,ios/WMM/Agents/ScopedAgentRuntime.swift,ios/WMMTests/BridgeAgentTests.swift | verify=`python ios/Build/run_simulators.py --family iphone` | Reuse the embedded backend for foreground handoff parity without promising background execution.
- [ ] T5 | slice=mission_control | files=mission_control/operation_runtime.py,mission_control/agent_grants.py,tests/test_batch_authority.py,tests/test_agent_grants.py | verify=`python -m unittest tests.test_batch_authority tests.test_agent_grants -v` | Preserve shared operation dispatch, retained grant checks and owner-only monitoring fences.
- [ ] T6 | slice=mission_control | files=mission_control/ios_agent_access.py,tests/test_agent_handoff_native.py,tests/test_batch_authority_native.py | verify=`python -m unittest tests.test_agent_handoff_native tests.test_batch_authority_native -v` | Reuse the embedded host, fresh owner and exact original grant without reconstructing credentials.
- [ ] T7 | slice=smoke | files=smoke/durable-agent-handoffs.json | verify=`forge verify-tests durable-agent-handoffs specs/durable-agent-handoffs.ssat.yaml --root .` | Prove a behavioral handoff smoke check rejects empty generated stubs.

## Acceptance
Run strict spec, validator challenge, spec and plan seals, architecture gate, scoped regression and hash-bound workflow audit. Local fixtures do not prove physical-device or provider acceptance.
