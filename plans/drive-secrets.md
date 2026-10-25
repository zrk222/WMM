# Plan: drive-secrets
Spec: specs/drive-secrets.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/db.py,mission_control/drive_secrets.py | verify=`python -m unittest tests.test_drive_secrets -v` | Add private Drive schema and native field staging, binding checks, attachment guards and recoverable retirement.
- [ ] T2 | slice=tests | files=tests/test_drive_secrets.py | verify=`python -m unittest tests.test_drive_secrets tests.test_social_secrets tests.test_play_storage -v` | Prove source isolation, schema reopening, export exclusion, interruption, staging expiry, active-reference protection and bounded recovery.
- [ ] T3 | slice=smoke | files=smoke/drive-secrets.json | verify=`forge smoke drive-secrets --root .` | Require behavioral assertions to fail on generated stubs and record disposable real-native storage acceptance separately.
