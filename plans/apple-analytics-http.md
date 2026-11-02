# Plan: apple-analytics-http
Spec: specs/apple-analytics-http.md
Architect verdict: PASS

## Architecture
The exact app-bound local HTTP adapter reuses fresh-owner protection, the existing sync queue, saved Apple inventory and the existing scheduler. Source and manifest expectations are revalidated inside each underlying write transaction by an optional trusted callback, constructed by the adapter and never accepted from HTTP input. Existing callers omit the callback. Inventory and responses expose only bounded metadata.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/apple_metrics_http.py | verify=`python -m unittest tests.test_apple_metrics_http -v` | Implement the exact owner-only adapter and source-bound projection.
- [ ] T2 | slice=tests | files=tests/test_apple_metrics_http.py | verify=`python -m unittest tests.test_apple_metrics_http -v` | Exercise correct selection, malformed and stale inputs, authority and redaction.
- [ ] T3 | slice=mission_control | files=mission_control/apple_metrics_schedule.py,mission_control/service.py,mission_control/worker.py | verify=`python -m unittest tests.test_apple_metrics_http tests.test_apple_metrics_schedule -v` | Invoke the optional source check inside each scheduler and queue write transaction.
- [ ] T4 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_apple_metrics_http_route -v` | Register the exact owner-domain route.
- [ ] T5 | slice=tests | files=tests/test_apple_metrics_http_route.py | verify=`python -m unittest tests.test_apple_metrics_http_route -v` | Exercise the owner route through a real loopback server with synthetic identities.

## Gates
Run strict spec checks, focused tests and hash-bound workflow audit. Real owner login and provider access are separate acceptance dependencies.
