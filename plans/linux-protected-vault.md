# Plan: linux-protected-vault
Spec: specs/linux-protected-vault.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/credential_vault.py,mission_control/linux_vault.py | verify=`python -m unittest tests.test_linux_vault -v` | Select native platform backend and exact scoped protected Secret Service operations without fallback.
- [ ] T2 | slice=tests | files=tests/test_linux_vault.py,tests/test_linux_vault_native.py | verify=`python -m unittest tests.test_linux_vault tests.test_measurement_connectors tests.test_drive_secrets -v` | Prove native identity, bounds, lock failures, duplicates, cleanup and unchanged Windows path.
- [ ] T3 | slice=smoke | files=smoke/linux-protected-vault.json | verify=`forge smoke linux-protected-vault --root .` | Retain actual Linux native roundtrip plus non-hollow behavior and scoped CF proof.

- [ ] T4 | slice=docs | files=docs/linux-protected-credentials.md | verify=`python tools/check_distribution.py` | Document explicit native dependency, unlocked desktop requirement, isolated acceptance and remaining platform gaps.
