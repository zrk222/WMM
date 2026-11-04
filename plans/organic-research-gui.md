# Plan: organic-research-gui

Architect verdict: PASS

Bounded architecture review: reuse the fresh-owner HTTP envelope and existing
collector/intake tables. Add only app-and-owner-scoped readback for durable GUI
history; preserve exact downstream validation and separate scoped agent gateway.
The static module reuses product dialogs, styles, source taxonomy and report
services. No new worker, provider adapter or standing grant is introduced.
This verdict covers this packet, not full commercial GUI or hosted readiness.

- [ ] T1 | slice=mission_control | files=mission_control/organic_video_collector.py,mission_control/organic_video_http.py,tests/test_organic_research_http.py | verify=`python -m unittest tests.test_organic_research_http tests.test_organic_video_policy_http -v` | Add exact fresh-owner task history and intake readback on existing routes, with app/owner scope, bounded pagination and no secret fields.
- [ ] T2 | slice=mission_control | files=mission_control/static/organic-research.js,mission_control/static/style.css,tests/organic_research_ui.test.cjs | verify=`node --test tests/organic_research_ui.test.cjs` | Add structured task assignment, result classification, inspection/adoption, inline validation and exact uncertain-write recovery using existing services, roles and styles.
- [ ] T3 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,tests/test_organic_research_browser.py | verify=`python -m unittest tests.test_organic_research_browser -v` | Integrate actual Research controls and exercise desktop/mobile rendered owner flows, stale context, keyboard, reports and error recovery.
- [ ] T4 | slice=mission_control | files=mission_control/server.py,tests/test_organic_research_http.py | verify=`python -m unittest tests.test_organic_research_http -v` | Serve the named research script through the existing exact static allowlist without accepting arbitrary files.
- [ ] T5 | slice=.github | files=.github/workflows/checks.yml,tests/test_organic_research_browser.py | verify=`python -m unittest tests.test_organic_research_browser -v` | Run the real owner research browser suite in the existing provisioned browser CI profile while ordinary shards retain explicit profile skips.
- [ ] T6 | slice=mission_control | files=mission_control/static/ui-stories.js,tests/ui_stories.test.cjs | verify=`node --test tests/ui_stories.test.cjs` | Replace generic repeated research dialog prose with concise stage-specific purpose, effect and next-step guidance through the existing story framework.
