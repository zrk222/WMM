# Plan: apple-watch-deadline
Spec: specs/apple-watch-deadline.md
Architect verdict: PASS

## Architecture
Add a nullable deadline through a forward migration. Use the saved deadline in the existing worker enqueue and provider admission guards. The existing owner endpoint and Apple Analytics panel carry the optional time; no new provider calls or job types.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/apple_metrics_schedule.py,mission_control/apple_metrics_http.py,mission_control/migrations/0004_apple_watch_deadline.sql,mission_control/schema_types.py | verify=`python -m unittest tests.test_apple_inventory_watch` | Persist and enforce the owner deadline.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/apple-analytics.js | verify=`node --test tests/apple_analytics_ui.test.cjs` | Display, validate and submit the optional stop time in the owner form.
- [ ] T3 | slice=tests | files=tests/test_apple_inventory_watch.py,tests/test_migrations.py,tests/apple_analytics_ui.test.cjs | verify=`python -m unittest tests.test_apple_inventory_watch tests.test_migrations` | Exercise boundaries, pending jobs, legacy schedule behavior and form submission.
- [ ] T4 | slice=tools | files=tools/test_apple_analytics_browser.py | verify=`python tools/test_apple_analytics_browser.py` | Verify the local time field and exact deadline in desktop and mobile.
- [ ] T5 | slice=mission_control | files=mission_control/apple_readiness_report.py | verify=`python -m unittest tests.test_apple_inventory_watch` | Report the ended window and suppress a due time beyond the deadline.

## Gates
Strict SpecLine, workflow audit, focused worker, owner HTTP and desktop/mobile verification.
