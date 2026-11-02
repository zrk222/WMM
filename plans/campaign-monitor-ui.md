# Plan: campaign-monitor-ui
Spec: specs/campaign-monitor-ui.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/campaign-monitor.js,mission_control/static/index.html,mission_control/static/app.js,mission_control/static/campaign-execution.js | verify=`node --test tests/campaign_monitor_ui.test.cjs` | Add finite monitoring review, explicit approval, saved progress, OFF and private reporting.
- [ ] T2 | slice=tests | files=tests/campaign_monitor_ui.test.cjs | verify=`node --test tests/campaign_monitor_ui.test.cjs` | Prove exact selections, authority neutrality until activation, stale rejection and report privacy.
- [ ] T3 | slice=tools | files=tools/test_campaign_monitor_browser.py | verify=`python tools/test_campaign_monitor_browser.py` | Exercise protected owner monitor controls and unattended synthetic worker result on desktop/mobile.

- [ ] T4 | slice=mission_control/static | files=mission_control/static/ui-stories.js | verify=`node --test tests/campaign_monitor_ui.test.cjs` | Narrate exact monitor authority and next steps.
- [ ] T5 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_campaign_monitor_integration` | Serve the fixed monitor UI module through the existing public static allowlist.

- [ ] T6 | slice=mission_control/static | files=mission_control/static/guided-workflow.js | verify=`node --test tests/campaign_monitor_ui.test.cjs` | Make monitoring directly reachable from goal-first home.
