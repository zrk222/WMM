# Plan: agent-run-checkpoints
Spec: specs/agent-run-checkpoints.md
Architect verdict: PASS

## Logical decomposition (phases)
1. Add an isolated checkpoint table to existing initialization and a transactional trusted-service class using current app roles. Each mutation checks a revision. Maker/checker role versions, app version/hash and expiry are rechecked before claim. No dispatch callback, HTTP endpoint, arbitrary command, credential or automatic retry exists in this packet.

## Tasks (atomic — each independently shippable)
<!-- Rules enforced by `specline tasks`: one slice each, <=4 files,
     explicit verify command, no forward references. -->
- [x] T1 | slice=mission_control | files=mission_control/agent_checkpoints.py,mission_control/db.py,tests/test_agent_checkpoints.py | verify=`python -m unittest tests.test_agent_checkpoints -v` | Implement checkpoint_packet, distinct_checker, single_claim, durable_recovery, stale_authority and checkpoint_history.

## Remaining boundary
This internal lifecycle primitive does not close full autonomous operability. Authenticate adapter callers, issue owner-scoped agent grants, bind operation-specific source validators, implement human review UI and test two clients before enabling agent execution. Checkpoints are not snapshot exports. Local database write access remains trusted.
