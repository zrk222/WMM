# Plan: apple-inventory-watch
Spec: specs/apple-inventory-watch.md
Architect verdict: PASS

## Architecture
Use an explicit owner choice and the current Apple scheduler. A reserved internal report selection maps to the existing Apple inventory adapter. The worker verifies the current lease and schedule in the transaction that retains the result. Metadata does not become a measurement or authorize a post.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/apple_metrics_http.py,mission_control/apple_metrics_schedule.py,mission_control/worker.py | verify=`python -m pytest -q tests/test_apple_inventory_watch.py tests/test_apple_metrics_schedule.py tests/test_apple_metrics_http.py` | Persist and run a read-only availability schedule through the existing worker.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/apple-analytics.js | verify=`node --test tests/apple_analytics_ui.test.cjs` | Offer report availability before a report selection is possible.
- [ ] T3 | slice=tests | files=tests/test_apple_inventory_watch.py,tests/apple_analytics_ui.test.cjs | verify=`python -m pytest -q tests/test_apple_inventory_watch.py tests/test_apple_metrics_schedule.py tests/test_apple_metrics_http.py` | Verify current-source projection, cadence, scope, lease and owner control.

- [ ] T4 | slice=tools | files=tools/test_apple_analytics_browser.py | verify=`python tools/test_apple_analytics_browser.py` | Exercise opt-in before report discovery and manual selection after it in the existing desktop and mobile harness.

## Gates
Strict SpecLine, workflow audit and focused worker, owner HTTP and desktop/mobile verification.
