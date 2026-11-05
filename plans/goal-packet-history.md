# Plan: goal-packet-history
Spec: specs/goal-packet-history.md
Architect verdict: PASS

## Architecture
Existing durable pipeline job stores server-generated goal snapshot on successful preparation. Exact source/version checks precede preparation. Request key binds app/goal/source and existing queue handles replay and restart. Historical packets are readable references, never current authority. Missing output remains explicit. Existing page-report utility provides PDF.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/automatic_preparation.py,mission_control/service.py,mission_control/worker.py | verify=`python -m unittest tests.test_goal_packet_history` | Validate fixed goal input and bind server-generated snapshot to existing pipeline worker.
- [ ] T2 | slice=tests | files=tests/test_goal_packet_history.py | verify=`python -m unittest tests.test_goal_packet_history` | Prove input/source boundaries, app isolation, idempotency and actual queue restart retention.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/automatic-preparation.js | verify=`node --test tests/goal_packet.test.cjs` | Save/reopen scoped local history with queued/failed/stale states and existing JSON/PDF controls.
- [ ] T4 | slice=tests | files=tests/goal_packet.test.cjs | verify=`node --test tests/goal_packet.test.cjs` | Prove stale controls, source escaping, bounded goal history and no implicit effects.
- [ ] T5 | slice=tools | files=tools/test_goal_packet_history_browser.py | verify=`python tools/test_goal_packet_history_browser.py` | Exercise save/reopen/restart/history/PDF using real Chromium at 1440 and390 with synthetic data.
- [ ] T6 | slice=.github | files=.github/workflows/checks.yml,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate` | Add the real saved-packet browser regression to CI and retain existing pinned job contract checks.
