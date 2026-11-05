# Plan: weekly-review-actions
Spec: specs/weekly-review-actions.md
Architect verdict: PASS

## Architecture
Append bounded review metadata to existing weekly projections after fresh app membership checks. Maintain private-principal cache fences and exact existing inspection routes. Recompute active status from existing immutable checkpoint transitions; retain approval and execution guards. SQL selects only metadata/checkpoint data; full envelopes/results stay out of the inbox.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/weekly_inbox.py | verify=`python -m unittest tests.test_weekly_review_actions` | Add role-scoped source-bound review cards without campaign dependency or mutation.
- [ ] T2 | slice=tests | files=tests/test_weekly_review_actions.py | verify=`python -m unittest tests.test_weekly_review_actions` | Prove real SQLite role/state/expiry/revocation/absence/secret and source boundaries.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/app.js,mission_control/static/page-reporting.js | verify=`node --test tests/weekly_operation_ui.test.cjs tests/page_reporting.test.cjs` | Reuse exact request inspection and fence cached private cards and report counts.
- [ ] T4 | slice=tests | files=tests/weekly_operation_ui.test.cjs,tests/page_reporting.test.cjs | verify=`node --test tests/weekly_operation_ui.test.cjs tests/page_reporting.test.cjs` | Cover exact-resource routing, stale sessions and metadata-only report counts.
- [ ] T5 | slice=tools | files=tools/test_weekly_review_actions_browser.py | verify=`python tools/test_weekly_review_actions_browser.py` | Exercise actual owner/checker weekly recovery and negative maker self-review at desktop/mobile widths with synthetic authentication and data.
- [ ] T6 | slice=.github | files=.github/workflows/checks.yml,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate` | Run actual browser regression in CI while preserving all existing job definitions.
