# Plan: drive-owner-http
Spec: specs/drive-owner-http.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/drive_http.py,mission_control/server.py | verify=`python -m unittest tests.test_drive_http -v` | Implement owner transport and app-bound callback admission using existing consent and job services.
- [ ] T2 | slice=tests | files=tests/test_drive_http.py | verify=`python -m unittest tests.test_drive_http tests.test_managed_media_http -v` | Exercise actual HTTP happy path and authorization, framing, privacy and cross-app failures.
- [ ] T3 | slice=smoke | files=smoke/drive-owner-http.json | verify=`forge smoke drive-owner-http --root .` | Prove non-hollow admission helpers and actual transport behavior.
