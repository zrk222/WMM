# Plan: campaign-schedule-ui
Spec: specs/campaign-schedule-ui.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/campaign_http.py | verify=`python -m unittest tests.test_campaign_schedule_http` | Add exact protected owner routes to schedule service.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/campaign-execution.js,mission_control/static/style.css | verify=`node --test tests/campaign_schedule_ui.test.cjs` | Review batch due times, activate exact hash and inspect or stop saved schedule.
- [ ] T3 | slice=tests | files=tests/test_campaign_schedule_http.py,tests/campaign_schedule_ui.test.cjs | verify=`python -m unittest tests.test_campaign_schedule_http` | Exercise ownerHTTP and pureUI contracts with blockednetwork fixtures.

- [ ] T4 | slice=mission_control | files=mission_control/automation_health.py,mission_control/static/ui-stories.js | verify=`python -m unittest tests.test_automation_recovery` | Register scheduled campaign supervision and narrate exact scheduling/readiness forms.

- [ ] T5 | slice=tools | files=tools/test_goal_automation_browser.py | verify=`python tools/test_goal_automation_browser.py` | Exercise owner readiness, exact schedule approval, durable reload and OFF with synthetic provider boundaries.
