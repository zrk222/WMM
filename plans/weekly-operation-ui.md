# Plan: weekly-operation-ui
Spec: specs/weekly-operation-ui.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_weekly_operation_http` | Use trusted local identity for owner-only exceptions.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/app.js | verify=`node --test tests/weekly_operation_ui.test.cjs` | Hide stale private exceptions and dispatch fixed recovery controls.
- [ ] T3 | slice=tests | files=tests/weekly_operation_ui.test.cjs,tests/test_weekly_operation_http.py | verify=`node --test tests/weekly_operation_ui.test.cjs` | Reject signed-out and mismatched cached private operations.

- [ ] T4 | slice=tools | files=tools/test_campaign_monitor_browser.py | verify=`python tools/test_campaign_monitor_browser.py` | Exercise owner exception recovery and cached-card removal after signout at desktop/mobile widths.
