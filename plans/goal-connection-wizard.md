# Plan: goal-connection-wizard
Spec: specs/goal-connection-wizard.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/app.js | verify=`node --test tests/goal_readiness_ui.test.cjs` | Add read-only owner connection wizard using existing readiness route.
- [ ] T2 | slice=tests | files=tests/goal_readiness_ui.test.cjs | verify=`node --test tests/goal_readiness_ui.test.cjs` | Verify exact selection, noauthority, stale readback and fixed repair routes.
- [ ] T3 | slice=mission_control | files=mission_control/automation_requirements.py,mission_control/social_connections.py,mission_control/social_setup.py | verify=`python -m unittest tests.test_automation_requirements tests.test_social_connections tests.test_social_setup tests.test_complete_automation -v` | Project the shared channel catalog and compatible connection path; include YouTube's read-first setup packet while keeping exact owner publication approval and read-only readiness.
- [ ] T4 | slice=tests | files=tests/test_automation_requirements.py,tests/test_goal_readiness_http.py | verify=`python -m unittest tests.test_automation_requirements tests.test_goal_readiness_http -v` | Verify all supported channels, incompatible or stale accounts, no publication authority and secret-free owner readback.
- [ ] T5 | slice=tests | files=tests/goal_journey.test.cjs,tests/test_social_connections.py,tests/test_publication_browser.py,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_social_connections tests.test_publication_browser tests.test_ci_current_candidate -v` | Verify catalog projection and actual goal-to-readiness-to-channel-review at desktop and mobile widths using the provisioned browser profile.
- [ ] T6 | slice=tools | files=tools/test_goal_journey_browser.py | verify=`python tools/test_goal_journey_browser.py` | Preserve the existing first-packet journey with channel-neutral empty-state wording.
- [ ] T7 | slice=.github/workflows | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_ci_current_candidate -v` | Execute the full goal-first packet journey in the provisioned cloud browser lane.
- [ ] T8 | slice=tests | files=tests/goal_packet.test.cjs,tests/test_social_setup.py | verify=`python -m unittest tests.test_social_setup -v` | Preserve exact packet routing and verify every provider setup packet remains read-first with no credential or effect grant.
