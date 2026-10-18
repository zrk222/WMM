# Plan: experiment-tracking
Spec: specs/experiment-tracking.md
Architect verdict: PASS

## Logical decomposition (phases)
1. Freeze provider targets and aggregate observation semantics.
2. Persist approved reads, guarded execution, replay and cancellation.
3. Wire the worker, app-scoped endpoints, readable Pipeline controls and agent feedback.
4. Test actual desktop/mobile workflows and full regressions before scoped release.

## Tasks (atomic — each independently shippable)
- [x] T1 | slice=mission_control | files=mission_control/tracking_contract.py,mission_control/tracking_posthog.py,tests/test_tracking_contract.py | verify=`python -m unittest tests.test_tracking_contract -q` | Derive fixed provider setup and validate aggregate observations without subjects.
- [x] T2 | slice=mission_control | files=mission_control/experiment_tracking.py,mission_control/db.py,tests/test_experiment_tracking.py | verify=`python -m unittest tests.test_experiment_tracking -q` | Persist exact approval, authority, replay and cancellation.
- [x] T3 | slice=mission_control | files=mission_control/worker.py,mission_control/server.py,mission_control/service.py,tests/test_tracking_http.py | verify=`python -m unittest tests.test_tracking_http -q` | Connect guarded worker execution and protected routes to workspace history.
- [x] T4 | slice=mission_control | files=mission_control/static/experiment-tracking.js,mission_control/static/automatic-preparation.js,mission_control/static/index.html,mission_control/agent_feedback.py | verify=`node --check mission_control/static/experiment-tracking.js` | Add review, progress, cancellation and explicit evidence limits.
- [x] T5 | slice=tools | files=tools/test_tracking_browser.py | verify=`python tools/test_tracking_browser.py` | Exercise desktop/mobile approval and recovery with isolated provider fixtures.
- [x] T6 | slice=smoke | files=smoke/experiment-tracking.json | verify=`forge smoke experiment-tracking --root .` | Prove non-hollow runtime behavior.
- [x] T7 | slice=README.md | files=README.md | verify=`python tools/check_distribution.py` | Explain permitted reads, instrumentation, recovery and unimplemented launch boundaries.
