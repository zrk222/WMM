# Plan: local-agent-api
Spec: specs/local-agent-api.md
Architect verdict: PASS

## Architecture
Add a numeric-loopback HTTP adapter using the existing deadline-aware response reader and strict draft parser. Keep public inference pinned to HTTPS and official subscription tools unchanged. Add an explicit local profile/routing mode with optional protected credentials and explicit request consent. Use the current app/source-bound proposal, worker and capability test. Extend existing setup controls and test actual desktop/mobile operation with an isolated compatible HTTP fixture. Local endpoint selection does not prove downstream model locality, billing, quality or provider authorization.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/local_agent_api.py,tests/test_local_agent_api.py | verify=`python -m unittest tests.test_local_agent_api -v` | Implement local_endpoint and bounded_inference with actual HTTP positive, negative and transport limits.
- [x] T2 | slice=mission_control | files=mission_control/agent_contract.py,mission_control/agent_registry.py,mission_control/agent_access.py,mission_control/agent_api.py | verify=`python -m unittest tests.test_local_agent_access tests.test_agent_access tests.test_agent_tasks -v` | Implement local_profiles and approval_currentness while preserving provider_regression.
- [x] T3 | slice=mission_control | files=mission_control/static/agent-access.js,tests/test_local_agent_access.py | verify=`python -m unittest tests.test_local_agent_access -v` | Implement local_interface and protected profile/worker integration.
- [x] T4 | slice=tools | files=tools/test_local_agent_browser.py | verify=`python tools/test_local_agent_browser.py` | Verify actual local setup, test, routing, draft, failure and reporting at desktop/mobile sizes.

## Acceptance
Run scoped CF, meaningful source mutations, full relevant regression, browser/PDF proof, deterministic Prestige audits and hash-bound workflow QA. Keep full product acceptance active and preserve unrelated work.
