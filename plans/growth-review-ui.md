# Plan: growth-review-ui
Spec: specs/growth-review-ui.md
Architect verdict: PASS

## Architecture
Add a UMD module with pure typed projections and app/version-bound form handlers. Inject the existing application services. Embed a review panel before existing Results content; add script/static allowlist and form/action dispatch only. Reuse sanitized page report rendering with an explicit growth-review model. No provider calls or execution authority.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/static/growth-review.js,tests/growth_review.test.cjs | verify=`node --test tests/growth_review.test.cjs` | Implement review_controls, listing_form, reference_form, comparison_form, editorial_form, safe_recovery and scoped_reports.
- [x] T2 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/server.py,tests/test_growth_review_ui_http.py | verify=`python -m unittest tests.test_growth_review_ui_http -v` | Implement ui_integration with static allowlist, existing modal/dispatch and route regression.
- [x] T3 | slice=tools | files=tools/test_growth_review_ui_browser.py | verify=`python tools/test_growth_review_ui_browser.py` | Verify actual desktop/mobile forms, app switching, error retention, exact-source readback, keyboard and PDF behavior without credentials or external writes.

## Acceptance
Run scoped CF/Forge gates, meaningful source mutations, project-neutral workflow audit and prescribed Prestige audits on rendered captures. Keep original user scope active. No UI-only badge, synthetic fixture or backend test establishes full-product/provider acceptance. The existing unrelated setup-feedback and Google Play work remains preserved.
