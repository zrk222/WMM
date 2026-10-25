# Plan: agent-media-sources
Spec: specs/agent-media-sources.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/managed_media_store.py,mission_control/managed_media_http.py | verify=`python -m unittest tests.test_agent_media_sources -v` | Project bounded redacted source descriptors through current owner reads.
- [ ] T2 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_agent_media_sources -v` | Add one read-only source operation through existing grants and CLI/MCP adapters.
- [ ] T3 | slice=tests | files=tests/test_agent_media_sources.py | verify=`python -m unittest tests.test_agent_media_sources -v` | Prove actual owner HTTP/CLI/MCP parity, redaction, foreign scope and missing-grant denial.
