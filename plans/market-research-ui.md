# Plan: market-research-ui
Architect verdict: PASS

Reuse GrowthReviews, current owner/agent transport, reports and existing modal.
Raw JSON travels inside the exact server envelope, retaining duplicate-key checks.
Use a reviewed-file summary followed by explicit save, immutable identity and
current app/version validation. No new authority or state engine.

- [x] T1 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/meta_media_buyer.py,mission_control/static/growth-review.js,mission_control/static/ui-stories.js | verify=`node --test tests/market_research_ui.test.cjs` | Add catalog schema and source-aware keyword review/import/details/report controls.
- [x] T2 | slice=tests | files=tests/market_research_ui.test.cjs,tests/test_market_research_browser.py,tests/test_market_research_clients.py | verify=`python -m unittest tests.test_market_research_browser tests.test_market_research_clients -v` | Exercise actual owner HTTP/UI at desktop and mobile, raw validation, immutable save, scoped CLI/MCP and report downloads.
- [x] T3 | slice=.github | files=.github/workflows/checks.yml,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate -v` | Add actual browser acceptance to existing provisioned CI profile and bind reviewed job guard.
