# Plan: discovery-transport
Spec: specs/discovery-transport.md
Architect verdict: PASS

- [x] T1 | slice=mission_control | files=mission_control/discovery_access.py,mission_control/discovery_http.py,mission_control/server.py | verify=`python -m unittest tests.test_discovery_clients -v` | Add exact owner routes and paged immutable research currentness reads.
- [x] T2 | slice=mission_control | files=mission_control/discovery_contract.py,mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/automation_requirements.py | verify=`python -m unittest tests.test_discovery_clients tests.test_operation_catalog tests.test_complete_automation -v` | Share all research operations through scoped clients and discoverable nested contracts while retaining blockers.
- [x] T3 | slice=tests | files=tests/test_discovery_clients.py | verify=`python -m unittest tests.test_discovery_clients tests.test_discovery_intelligence -v` | Prove real owner grant CLI and official MCP parity plus stale revoked foreign and malformed denial.
- [x] T4 | slice=smoke | files=smoke/discovery-transport.json | verify=`forge smoke discovery-transport --root .` | Require actual non-hollow behavior evidence and all scoped gates before completion.

Transport acceptance uses123 local tests including official MCP and scoped CLI. UI, downstream brief/editor/Hypit adaptation, authorized collectors/schedules and real provider/device proof remain required parent-goal work.
