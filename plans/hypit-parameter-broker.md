# Plan: hypit-parameter-broker
Spec: specs/hypit-parameter-broker.md
Architect verdict: PASS

## Architecture
The broker retains one actual StudioProcess object, app manifest identity, private
opaque-view key and exact compiled closure. A trusted authority callback is
rechecked before and during operations. The process still owns its child/listener
and cleanup. Parameter transport uses a fixed endpoint and bounded native body.
The ledger linearizes intent before send, then source observation/result/head
commit before adopting changed process source hashes. Ambiguity remains durable;
inspection is distinct from approval or safe automatic reconciliation.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_parameter_broker.py,mission_control/hypit_studio_http.py,mission_control/hypit_source_ledger.py | verify=`python -m unittest tests.test_hypit_parameter_broker -v` | Implement broker_authority, broker_view, broker_once, broker_transport, broker_result, broker_uncertainty and broker_inspection.
- [ ] T2 | slice=tests | files=tests/test_hypit_parameter_broker.py | verify=`python -m unittest tests.test_hypit_parameter_broker tests.test_hypit_source_ledger tests.test_hypit_studio_process -v` | Prove real controlled loopback calls, competing requests, source adoption, normalized/no-op values, rollback and uncertainty without provider credentials.

## Gates
Current CF strict/validator/tasks, focused regressions and source mutations,
independent Astra review, actual installed local Hypit transaction/readback/owned
cleanup, privacy and hash-bound workflow QA. No UI/public operation is added in
this internal packet; full shared human/agent workflow remains mandatory.
