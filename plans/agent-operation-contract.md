# Plan: agent-operation-contract
Spec: specs/agent-operation-contract.md
Architect verdict: PASS

## Architecture
Use a pure app-scoped discovery projection and existing server boundaries. Explicitly report unimplemented agent execution and independent human approval. Discovery never executes a command. Subsequent packets implement scoped grants and human checkpoints before claiming full operability.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/agent_operations.py,mission_control/server.py,tests/test_agent_operations.py | verify=`python -m unittest tests.test_agent_operations -q` | Expose operation_discovery, checkpoint_boundaries and discovery_scope through the current loopback HTTP service.

## Full user requirement remains open
Cover all WMM domains, versioned request/result schemas, autonomous permitted actions, distinct human approval, durable pause/resume, revocation, cancellation, ambiguous-effect reconciliation and two independent protocol clients. Preserve the separate setup-feedback work. This packet does not close the larger requirement.
