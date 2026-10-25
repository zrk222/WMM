# Plan: subscription-authoring-ui
Spec: specs/subscription-authoring-ui.md
Architect verdict: PASS

## Architecture
Add an isolated module using existing app services and GrowthReview field/report helpers. Structured billing records feed existing exact subscription validators; experiment payloads use selected source configurations. Preserve existing creative experiment and lifecycle paths. No backend semantics or provider writes change.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/static/subscription-authoring.js,tests/subscription_authoring.test.cjs | verify=`node --test tests/subscription_authoring.test.cjs` | Implement billing_authoring, typed_registration, safe_drafts and review_reports.
- [x] T2 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/server.py,tests/test_subscription_authoring_http.py | verify=`python -m unittest tests.test_subscription_authoring_http -v` | Integrate static module, Results controls, form/action dispatch and actual loopback boundaries.
- [x] T3 | slice=tools | files=tools/test_subscription_authoring_browser.py | verify=`python tools/test_subscription_authoring_browser.py` | Implement browser_proof with actual saved configurations, typed preregistration, invalid source handling and reports.

## Acceptance
Bind current sources and real observations to workflow audit; use Node, HTTP, browser/PDF, exact function complexity and prescribed design checks. Make incremental local commits after relevant checks. Full agent, provider and remaining all-page scope stays active.
