# Plan: funnel-transport
Spec: specs/funnel-transport.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/funnel_http.py,mission_control/server.py,mission_control/funnel_store.py | verify=`python -m unittest tests.test_funnel_clients tests.test_funnel_store -v` | Add exact owner-bound loopback routes with current session and transaction authority; bounded pages and a complete single read.
- [ ] T2 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/automation_requirements.py,mission_control/funnel_contract.py | verify=`python -m unittest tests.test_funnel_clients tests.test_complete_automation tests.test_operation_catalog -v` | Adapt the same services through grants CLI and official MCP with closed pagination and nested input discovery; classify every operation.
- [ ] T3 | slice=tests | files=tests/test_funnel_clients.py,tests/test_funnel_store.py,tests/test_operation_catalog.py | verify=`python -m unittest tests.test_funnel_clients tests.test_funnel_store -v` | Prove shared real-source state, pagination beyond100, stale/revoked/foreign denial, framing and no implicit human approval.
- [ ] T4 | slice=smoke | files=smoke/funnel-transport.json | verify=`forge smoke funnel-transport --root .` | Require real local acceptance and assertion-based scaffold rejection before scoped completion.
