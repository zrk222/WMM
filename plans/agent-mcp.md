# Plan: agent-mcp
Spec: specs/agent-mcp.md
Architect verdict: PASS

## Architecture
An optional stdio SDK server projects fixed schemas from operation_catalog, then invokes a fresh OperatorClient per call. It never writes SQLite directly. SDK manages protocol lifecycle and input schema checking; shared request_data and service validators remain authoritative. Independent human checkpoint integration is separate required work.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/agent_mcp.py,tests/test_agent_mcp.py | verify=`python -m unittest tests.test_agent_mcp -v` | Implement mcp_discovery, shared_execution, mcp_validation, stdio_lifecycle, authority_boundary and two_client_proof with real SDK subprocess tests.
- [x] T2 | slice=docs | files=docs/agent-mcp.md,docs/requirements-mcp.txt | verify=`python -m mission_control.agent_mcp --help` | Document exact local connection setup, optional dependencies, effect scope, errors and remaining authorization work.

## Acceptance
Strict SpecLine and requirement mutation gates, Forge scoped QA/architecture/smoke, shared CLI/MCP/HTTP regressions, direct source mutation and hash-bound workflow audit. Preserve unrelated files and commit locally without push or external effects.
