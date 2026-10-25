# Plan: agent-review-transport
Spec: specs/agent-review-transport.md
Architect verdict: PASS

## Architecture
One pure finite review protocol feeds the HTTP gateway, CLI and optional MCP. Agent bearer endpoints reuse exact loopback framing checks and ReviewedDispatch. A separate CSRF-protected human adapter uses fresh verified session principals and existing Checkpoints. No approve/login action is exposed to agents. All new routes use exact bodies and current app scope.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/agent_review_protocol.py,mission_control/agent_review_http.py,mission_control/server.py,tests/test_agent_review_http.py | verify=`python -m unittest tests.test_agent_review_http -v` | Implement review_protocol, agent_gateway, human_gateway, human_inspection and review_recovery.
- [x] T2 | slice=mission_control | files=mission_control/agent_grant_http.py,mission_control/operator_client.py,mission_control/agent_cli.py,tests/test_agent_review_http.py | verify=`python -m unittest tests.test_agent_review_http -v` | Share exact framing and finite review client transport without session fallback.
- [x] T3 | slice=mission_control | files=mission_control/agent_mcp.py,tests/test_agent_review_clients.py | verify=`python -m unittest tests.test_agent_review_clients -v` | Implement review_clients with real CLI and official SDK MCP subprocess lifecycle and independent checker HTTP approval.
- [x] T4 | slice=docs | files=docs/agent-review-transport.md | verify=`python -m mission_control.agent_cli --help` | Document actual owner/checker and agent commands, pagination, authority and remaining UI work.
- [x] T5 | slice=mission_control | files=mission_control/agent_review_dispatch.py,tests/test_agent_review_dispatch.py,tests/test_agent_review_http.py | verify=`python -m unittest tests.test_agent_review_dispatch tests.test_agent_review_http -v` | Bind status/resume lookup to the exact grant before reading request details and prove uniform denial for existing and missing request IDs.

## Acceptance
Scoped CF/SpecLine/Forge, real HTTP/client regressions, mutation proof and hash-bound workflow audit. Preserve unrelated files. The user has authorized merging the fully tested local increment; overall product/release assurance remains incomplete. No provider effects or push.
