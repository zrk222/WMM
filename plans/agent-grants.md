# Plan: agent-grants
Spec: specs/agent-grants.md
Architect verdict: PASS

## Architecture
Keep agent grants distinct from model-provider credentials and human reviews. Persist only random token digests and frozen scope. Use existing verified owner membership for issuance/list/revoke. A loopback bearer gateway reserves quota then dispatches the existing operation service; no grant-management or human-review operation enters the agent catalog. Opt-in CLI/MCP clients use the same gateway and never silently downgrade to browser sessions.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/agent_grants.py,mission_control/db.py,tests/test_agent_grants.py | verify=`python -m unittest tests.test_agent_grants -v` | Implement grant_issue, grant_admission, grant_lifecycle and grant_privacy with transactional service proof.
- [x] T2 | slice=mission_control | files=mission_control/operation_runtime.py,mission_control/agent_grant_http.py,mission_control/server.py,tests/test_agent_grants.py | verify=`python -m unittest tests.test_agent_grants -v` | Implement grant_dispatch and actual HTTP issuance, revocation and fixed-operation execution.
- [x] T3 | slice=mission_control | files=mission_control/operator_client.py,mission_control/agent_cli.py,mission_control/agent_mcp.py,tests/test_agent_grant_clients.py | verify=`python -m unittest tests.test_agent_grant_clients -v` | Implement grant_clients for actual CLI and SDK subprocesses, denied scopes, no-cookie behavior and no fallback.
- [x] T4 | slice=docs | files=docs/agent-grants.md | verify=`python -m mission_control.agent_cli --help` | Document exact owner/client operations, grant boundaries and remaining checkpoint integration.

## Acceptance
Scoped CF, SpecLine, Forge, source mutations and project-neutral hash-bound workflow audit; regression for existing HTTP/identity/checkpoint/CLI/MCP behavior. Preserve unrelated work and commit only this verified increment. No push or external activation.
