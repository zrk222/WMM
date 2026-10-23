# Plan: page-reporting
Spec: specs/page-reporting.md
Architect verdict: PASS

## Architecture
Use a pure, allowlisted JS projection and shared UI renderer. Integrate with the existing ten-view render boundary and explicit same-origin static route. PDF reports use a dedicated sanitized print window and existing browser Save as PDF; no DOM capture, raw profiles or provider requests. Client timestamps mean loaded time, not provider freshness. Every metric retains its source path and coverage. Secondary dialogs and tool pages are a separate required follow-up, not complete from top-level adoption.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/static/page-reporting.js,mission_control/static/page-reporting.css,tests/page_reporting.test.cjs | verify=`node --test tests/page_reporting.test.cjs` | Implement page_explainers, page_analytics, report_scope, pdf_export, report_privacy and report_recovery as a pure model and shared accessible controls.
- [x] T2 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/server.py,tests/test_page_reporting_http.py | verify=`python -m unittest tests.test_page_reporting_http -v` | Wire the shared renderer through every top-level view and serve exact scripts/styles through existing HTTP boundaries.
- [x] T3 | slice=tools | files=tools/test_page_reporting_browser.py | verify=`python tools/test_page_reporting_browser.py` | Verify all ten pages desktop/mobile, keyboard, app switching, error handling, report privacy, actual PDF output and rendered acceptance.
- [x] T4 | slice=mission_control | files=mission_control/static/page-reporting.js,mission_control/static/page-reporting.css,mission_control/static/app.js,tests/page_reporting.test.cjs | verify=`node --test tests/page_reporting.test.cjs` | Implement overview_story using the Nanna mission, guidance, choice and truthful-payoff arc. Show the summary before advanced controls and retain every existing feature.

## Full acceptance remains open
Secondary tool panels, reportable detail dialogs, loading/error states and new subscription-growth pages must receive their own typed context. Complete generic-agent and BYOK/OAuth acceptance independently. No full-product completion or release claim from this packet.

## Story contract
Audience: app founders and operators who want a useful next marketing step. Mission/tension: an app to grow, with facts and ideas scattered across places. Guidance: bring facts, prepare work and learn from observations. Agency: choose the next step and approve consequential changes. Observable payoff: a saved plan, drafts, evidence gaps and reports. Growth outcomes remain unknown until measured. Copy is proposed interface guidance based on currently implemented workspace, preparation, drafts and imported-metric behavior; it does not certify end-to-end autonomous operations. Keep the complete feature set visible and pursue all remaining workflows to full verified acceptance.
