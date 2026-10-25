# Plan: automation-owner-ui
Spec: specs/automation-owner-ui.md
Architect verdict: PASS

## Architecture
Add a dedicated owner UI module using existing fresh-owner routes and exact
standing policy services. Extend owner status with public workflow catalog and
grant usage counters so the UI has no duplicated authorization map. Mount an
owner-only launch control next to permission controls; open status, setup and
confirmation within the shared dialog. Existing modal lifecycle clears token
delivery and cancels stale tickets. Only server-issued confirmation shows ON.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/static/complete-automation.js,mission_control/static/ui-stories.js | verify=`node --test tests/complete_automation_ui.test.cjs tests/ui_stories.test.cjs` | Implement owner_status, onboarding_scope, confirm_scope, owner_off, scope_lifecycle and automation_reports with plain guidance.
- [ ] T2 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/server.py,mission_control/complete_automation.py | verify=`python -m unittest tests.test_complete_automation tests.test_automation_execution -q` | Wire fixed asset/lifecycle routes and public status/catalog counters while retaining owner authentication.
- [ ] T3 | slice=tests | files=tests/complete_automation_ui.test.cjs,tests/test_complete_automation.py | verify=`node --test tests/complete_automation_ui.test.cjs` | Prove explicit confirmation, report privacy, exact scope and public status shape.

## Gates
Current CF doctor, strict/mutated requirements and pre-code seals; focused real
owner HTTP and Node tests; actual owner desktop/mobile activation/OFF with only
synthetic credentials; stale/blocker/secret/report proof; Prestige and workflow
evidence. Whole-domain automation is not proven by a bounded local workflow.
