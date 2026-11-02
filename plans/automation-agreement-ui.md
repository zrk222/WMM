# Plan: automation-agreement-ui
Spec: specs/automation-agreement-ui.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/app.js,mission_control/static/ui-stories.js | verify=`node --test tests/automation_agreement_ui.test.cjs` | Add protected selected-resource combined summary and sanitized reporting.
- [ ] T2 | slice=tests | files=tests/automation_agreement_ui.test.cjs | verify=`node --test tests/automation_agreement_ui.test.cjs` | Verify authority neutrality, resource selection and stale response denial.

- [ ] T3 | slice=tools | files=tools/test_goal_automation_browser.py | verify=`python tools/test_goal_automation_browser.py` | Exercise saved batch combined agreement and privacy report in actual owner browser.
