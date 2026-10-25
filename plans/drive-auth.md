# Plan: drive-auth
Spec: specs/drive-auth.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/drive_auth.py | verify=`python -m unittest tests.test_drive_auth -v` | Compile and validate fixed selected-file OAuth consent, callbacks and token exchanges using existing shared validators.
- [ ] T2 | slice=tests | files=tests/test_drive_auth.py | verify=`python -m unittest tests.test_drive_auth tests.test_play_connections tests.test_social_flows -v` | Prove protocol boundaries, secret redaction, one-attempt transport and unchanged existing connectors.
- [ ] T3 | slice=smoke | files=smoke/drive-auth.json | verify=`forge smoke drive-auth --root .` | Require meaningful behavioral smoke assertions to fail on generated stubs before protocol acceptance.
