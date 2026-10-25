# Plan: drive-accounts
Spec: specs/drive-accounts.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/drive_account_contract.py | verify=`python -m unittest tests.test_drive_accounts -v` | Validate verified identities, review packets and connection-bound protected contexts.
- [ ] T2 | slice=mission_control | files=mission_control/drive_accounts.py | verify=`python -m unittest tests.test_drive_accounts -v` | Read fixed account identity, stage candidates and adopt only exact owner-confirmed live packets.
- [ ] T3 | slice=mission_control | files=mission_control/drive_connection_state.py | verify=`python -m unittest tests.test_drive_accounts -v` | Return private current account state and version-bound local disconnect with pending-flow cancellation.
- [ ] T4 | slice=tests | files=tests/test_drive_accounts.py | verify=`python -m unittest tests.test_drive_accounts tests.test_drive_flows tests.test_drive_secrets tests.test_drive_auth -v` | Prove exchange/read races, explicit account replacement, secret binding, expiry and cleanup without provider access.
- [ ] T5 | slice=smoke | files=smoke/drive-accounts.json | verify=`forge smoke drive-accounts --root .` | Require meaningful account and binding assertions plus actual durable adoption tests before scoped delivery.
