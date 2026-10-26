# Plan: drive-callback-ui
Spec: specs/drive-callback-ui.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/static/drive-callback.html,mission_control/static/drive-callback.js,mission_control/server.py | verify=`node --test tests/drive_callback.test.cjs` | Implement isolated consent callback, explicit owner login and app/account confirmation with no credential storage.
- [ ] T2 | slice=tests | files=tests/drive_callback.test.cjs,tests/test_drive_callback_http.py | verify=`python -m unittest tests.test_drive_callback_http -v` | Prove actual static callback routing and browser-controller state, consent boundaries and errors.
- [ ] T3 | slice=smoke | files=smoke/drive-callback-ui.json | verify=`forge smoke drive-callback-ui --root .` | Require deterministic UI audits, browser observations and non-hollow behavior before delivery.
