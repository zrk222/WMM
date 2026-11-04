# Plan: organic-policy-gui
Architect verdict: PASS

Reuse the actual owner policy routes and current domain checks. A separate
read-only owner service supplies bounded context/history; it grants no policy.
Use existing app/session role snapshots and report renderer. Preserve uncertain
requests until exact hash-bound readback and explicit identical replay.

- [x] T1 | slice=mission_control | files=mission_control/organic_video_http.py,mission_control/server.py | verify=`python -m unittest tests.test_organic_policy_gui_http -v` | Expose bounded policy context/history through the existing fresh-owner boundary and allowlist the actual script.
- [x] T7 | slice=mission_control | files=mission_control/organic_video_policy.py,tests/test_organic_policy_gui_http.py | verify=`python -m unittest tests.test_organic_policy_gui_http -v` | Validate reviewed app, Page, owner role and session atomically in the existing policy create transaction while preserving the legacy owner request shape.
- [x] T2 | slice=mission_control | files=mission_control/static/organic-policy.js,mission_control/static/app.js,mission_control/static/index.html | verify=`node --test tests/organic_policy_ui.test.cjs` | Implement typed evidence/template/limit review, exact saved revalidation, revoke, uncertainty recovery and reports.
- [x] T6 | slice=mission_control | files=mission_control/static/ui-stories.js,mission_control/static/style.css | verify=`node --test tests/organic_policy_ui.test.cjs` | Add concise task guides and scoped validation styling to the actual owner dialog.
- [x] T3 | slice=tests | files=tests/organic_policy_ui.test.cjs,tests/test_organic_policy_gui_http.py,tests/test_organic_policy_gui_browser.py | verify=`python -m unittest tests.test_organic_policy_gui_browser -v` | Prove actual owner desktop/mobile forms, role negatives, stale context, lost responses, reports and immutable saves.
- [x] T4 | slice=.github | files=.github/workflows/checks.yml,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate -v` | Run actual policy browser acceptance in provisioned CI and bind the exact workflow guard.
- [x] T5 | slice=docs | files=docs/gui-coverage.md | verify=`python -m unittest tests.test_organic_policy_gui_http -v` | Update only proven policy-control coverage; retain remaining organic execution GUI work.
