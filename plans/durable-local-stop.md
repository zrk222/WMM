# Plan: durable-local-stop
Spec: specs/durable-local-stop.md
Architect verdict: PASS for one additive receipt over the existing exact local Stop transaction. Broader goal activation/Stop remains separate.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/db.py | verify=`python -m unittest tests.test_complete_automation` | Add a policy-keyed immutable local Stop receipt to the shared SQLite schema.
- [ ] T2 | slice=mission_control | files=mission_control/complete_automation.py | verify=`python -m unittest tests.test_complete_automation` | Preserve the existing input and output shape, save a receipt atomically with OFF and return it only for the exact active owner replay.
- [ ] T3 | slice=tests | files=tests/test_complete_automation.py | verify=`python -m unittest tests.test_complete_automation tests.test_automation_agreement` | Test concurrency, reopen, caller scope, legacy OFF, immutable receipt, grant denial and rollback after receipt insertion.
- [ ] T4 | slice=docs | files=docs/complete-automation-authority.md | verify=`python tools/check_distribution.py` | Explain safe retry and the boundary between local Stop and provider effects.
