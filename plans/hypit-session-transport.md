# Plan: hypit-session-transport
Spec: specs/hypit-session-transport.md
Architect verdict: PASS

## Architecture
Instantiate one Manager in Service. Add finite catalog descriptors and early fixed
Studio dispatch to operation_runtime. Existing owner grants and reviewed/standing
dispatch bind request-local authority before the manager enters protected(). Human
routes perform exact framing, fresh owner identity and bound_owner around the same
manager dispatch. Server close records manager shutdown before socket resource
close. Existing CLI/MCP operation schema generation picks up the new descriptors.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/service.py,mission_control/operation_catalog.py,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_hypit_studio_clients tests.test_operation_catalog -v` | Implement transport_shared and transport_agent through the existing fixed dispatcher.
- [ ] T2 | slice=mission_control | files=mission_control/hypit_studio_routes.py,mission_control/server.py | verify=`python -m unittest tests.test_hypit_studio_clients -v` | Implement transport_owner, transport_unknown and transport_shutdown without generic native endpoints.
- [ ] T3 | slice=tests | files=tests/test_hypit_studio_clients.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_hypit_studio_clients tests.test_operation_catalog -v` | Prove real HTTP/CLI/MCP calls, exact owner/grant scopes, reviewed unknown/no replay, shutdown receipt and schema closure.
- [ ] T4 | slice=mission_control | files=mission_control/operator_client.py,mission_control/agent_cli.py,mission_control/agent_mcp.py | verify=`python -m unittest tests.test_hypit_studio_clients tests.test_operator_client -v` | Implement transport_clients with fixed observation deadlines and preserved typed uncertainty in CLI/MCP errors.
- [ ] T5 | slice=mission_control | files=mission_control/automation_requirements.py | verify=`python -m unittest tests.test_automation_requirements tests.test_hypit_studio_clients -v` | Keep transport_agent policy mapping complete without expanding executable standing approval scope.

## Gates
CF strict/validator/task checks, scoped Forge architecture/QA/nonhollow/smoke,
behavioral guard mutations, independent Astra review, actual installed synthetic
human/agent client lifecycle probe and hash-bound workflow audit. Preserve source
and failure evidence. Restart reconciliation, complete UI/editor controls and all
other parent workflows remain required; no deployment/provider-spend permission.
