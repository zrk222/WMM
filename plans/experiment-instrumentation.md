# Plan: experiment-instrumentation
Spec: specs/experiment-instrumentation.md
Architect verdict: PASS

- [x] T1 | slice=mission_control | files=mission_control/sdk/experiment-client.mjs | verify=`node --test tests/instrumentation.test.mjs` | Implement guarded fresh assignment, atomic sticky state and truthful capture status.
- [x] T2 | slice=mission_control | files=mission_control/instrumentation.py | verify=`python -m unittest tests.test_instrumentation -q` | Derive deterministic source-bound credential-free installation bundles.
- [x] T3 | slice=mission_control | files=mission_control/server.py,mission_control/static/experiment-tracking.js | verify=`python -m unittest tests.test_instrumentation_http -q` | Expose exact review/download with no installation or launch claim.
- [x] T4 | slice=tests | files=tests/instrumentation.test.mjs,tests/test_instrumentation.py,tests/test_instrumentation_http.py | verify=`python -m unittest discover -s tests -q` | Verify boundaries and regressions.
- [x] T5 | slice=tools | files=tools/test_instrumentation_browser.py | verify=`python tools/test_instrumentation_browser.py` | Test actual browser state, cross-tab behavior and desktop/mobile package review.
- [x] T6 | slice=README.md | files=README.md | verify=`python tools/check_distribution.py` | Explain setup, delivery uncertainty and remaining platform/pilot limits.
- [x] T7 | slice=smoke | files=smoke/experiment-instrumentation.json | verify=`forge smoke experiment-instrumentation --root .` | Reject empty installer behavior.
- [x] T8 | slice=.github | files=.github/workflows/checks.yml | verify=`node --test tests/instrumentation.test.mjs` | Include actual browser-adapter logic tests in public CI with its supplied Node runtime.
