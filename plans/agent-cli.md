# Plan: agent-cli
Spec: specs/agent-cli.md
Architect verdict: PASS

## Architecture
Separate pure fixed catalog/envelope validation, bounded loopback HTTP client and CLI input/output. Use the existing WMM server unchanged and in-memory cookie/CSRF bootstrap. Do not expose authentication or approval endpoints. Future MCP invokes this same client/catalog; full scoped agent grants and independent human approval remain separate required integration.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/operation_catalog.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_operation_catalog -v` | Implement fixed_catalog, typed_calls and approval_boundary with exact envelope validation.
- [x] T2 | slice=mission_control | files=mission_control/operator_client.py,tests/test_operator_client.py | verify=`python -m unittest tests.test_operator_client -v` | Implement loopback_client with strict transport, in-memory CSRF and actual server persistence/readback.
- [x] T3 | slice=mission_control | files=mission_control/agent_cli.py,tests/test_agent_cli.py | verify=`python -m unittest tests.test_agent_cli -v` | Implement cli_protocol and real_client_proof using real subprocesses and isolated loopback server.
- [x] T4 | slice=docs | files=docs/agent-cli.md | verify=`python -m mission_control.agent_cli catalog` | Document exact working invocation, operations, error codes and authority limitations without claiming full agent autonomy.

## Acceptance
Run CF/SpecLine/Forge, HTTP/subprocess regression, meaningful source mutations and hash-bound workflow audit. Accessibility is backend/CLI-only here; UI/human review is still required separately. Commit the verified increment locally and preserve unrelated setup-feedback/Google Play files. No push or provider action.
