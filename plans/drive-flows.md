# Plan: drive-flows
Spec: specs/drive-flows.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/drive_flow_contract.py | verify=`python -m unittest tests.test_drive_flows -v` | Validate frozen setup context and redacted bounded progress using existing app and secret primitives.
- [ ] T2 | slice=mission_control | files=mission_control/drive_flows.py | verify=`python -m unittest tests.test_drive_flows -v` | Persist protected pending flow, one-use claim, live guards, cancellation and bounded expiry without replacing a connection.
- [ ] T3 | slice=tests | files=tests/test_drive_flows.py | verify=`python -m unittest tests.test_drive_flows tests.test_drive_auth tests.test_drive_secrets -v` | Prove concurrent claim, stale context, restart, redaction, candidate cleanup and retained prior connection.
- [ ] T4 | slice=smoke | files=smoke/drive-flows.json | verify=`forge smoke drive-flows --root .` | Require non-hollow context validation and actual lifecycle tests before scoped delivery.
