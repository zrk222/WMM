# Plan: agent-reviewed-dispatch
Spec: specs/agent-reviewed-dispatch.md
Architect verdict: PASS

## Architecture
Reuse grant validation and durable Checkpoints; add separate immutable policy/request/result tables excluded from portable exports. Gate ordinary operation dispatch when a policy requires review. Freeze exact input and binding to a specific grant. A reviewed dispatcher revalidates grant and checkpoint, exclusively claims saved input, invokes the existing domain runtime, and records the result plus terminal checkpoint transition. No alternate domain validator or human identity mechanism.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/db.py,mission_control/agent_grants.py,mission_control/agent_review_policy.py,tests/test_agent_review_policy.py | verify=`python -m unittest tests.test_agent_review_policy -v` | Implement review_policy and enforced_checkpoint through immutable grant policy and ordinary admission rejection.
- [x] T2 | slice=mission_control | files=mission_control/agent_checkpoints.py,mission_control/agent_review_dispatch.py,tests/test_agent_review_dispatch.py | verify=`python -m unittest tests.test_agent_review_dispatch -v` | Implement frozen_request, reviewed_admission, reviewed_execution and reviewed_recovery through existing checkpoint lifecycle and authoritative services.

## Acceptance
CF doctor, strict SpecLine, requirement mutation/drift, scoped Forge QA/architecture/smoke, behavior mutants and hash-bound workflow audit. Keep HTTP/client/human UI integration explicitly unfinished. Do not merge a failing or incomplete packet. Preserve unrelated work; no push or provider effects.
