# Plan: campaign-owner-report-ui
Spec: specs/campaign-owner-report-ui.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/campaign-owner-reports.js,mission_control/static/app.js,mission_control/static/index.html,mission_control/static/guided-workflow.js | verify=`node --test tests/campaign_owner_report_ui.test.cjs` | Add private report selection and finite schedule controls.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/ui-stories.js | verify=`node --test tests/ui_stories.test.cjs` | Explain saved source windows and private report outcomes.
- [ ] T3 | slice=mission_control | files=mission_control/server.py,mission_control/worker.py,mission_control/automation_health.py | verify=`python -m unittest tests.test_campaign_owner_reports_integration` | Route protected report actions and local worker snapshots.
- [ ] T4 | slice=tests | files=tests/campaign_owner_report_ui.test.cjs,tests/test_campaign_owner_reports_integration.py | verify=`node --test tests/campaign_owner_report_ui.test.cjs` | Verify exact scope, private projection and integrated source authority.
- [ ] T5 | slice=tools | files=tools/test_campaign_owner_report_browser.py | verify=`python tools/test_campaign_owner_report_browser.py` | Exercise actual owner report capture and background report plan in desktop/mobile browser.
