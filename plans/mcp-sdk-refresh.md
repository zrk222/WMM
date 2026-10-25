# Plan: mcp-sdk-refresh
Spec: specs/mcp-sdk-refresh.md
Architect verdict: PASS

## Architecture
Keep the existing official SDK server interface and WMM validators unchanged.
Test the 1.30.0 wheel and dependencies in a clean isolated environment before
changing the optional pin. Record current package metadata, actual transport
tests and hashes separately from the existing system Python baseline.

## Tasks
- [ ] T1 | slice=docs | files=docs/requirements-mcp.txt,docs/agent-mcp.md | verify=`python -m unittest tests.test_agent_mcp -v` | Implement sdk_pin and document sdk_boundary against the tested maintenance SDK.
- [ ] T2 | slice=specs | files=specs/agent-mcp.md | verify=`specline strict agent-mcp` | Update the adapter contract to the tested optional SDK baseline.
- [ ] T3 | slice=tests | files=tests/test_agent_mcp.py,tests/test_agent_grant_clients.py,tests/test_agent_review_clients.py,tests/test_customer_workflow_integration.py | verify=`python -m unittest tests.test_agent_mcp tests.test_agent_grant_clients tests.test_agent_review_clients tests.test_customer_workflow_integration -q` | Verify sdk_conformance and sdk_authority with existing real protocol tests; no implementation-mirroring test is added.

## Gates
Current CF doctor/strict/requirement mutations/tasks, clean environment pip check,
real SDK client suite including native media and shared editing workflows,
unchanged default requirements, package wheel hash and hash-bound workflow QA.
Global Python and the running preview remain unchanged. No deployment or activation.
