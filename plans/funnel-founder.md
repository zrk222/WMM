# Plan: funnel-founder
Spec: specs/funnel-founder.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/funnel_founder_review.py | verify=`python -m unittest tests.test_funnel_founder -v` | Join exact sequential source receipts into bounded founder pages and explicit collection gaps.
- [ ] T2 | slice=mission_control | files=mission_control/funnel_http.py,mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/automation_requirements.py | verify=`python -m unittest tests.test_funnel_founder_clients tests.test_operation_catalog tests.test_automation_requirements -v` | Expose the identical owner and grant read over exact HTTP CLI MCP without public data projection.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/funnel-model.js,mission_control/static/funnel-ui.js,mission_control/static/growth-review.js,mission_control/static/ui-stories.js | verify=`node --test tests/funnel_founder.test.cjs tests/funnel_ui.test.cjs` | Add useful founder explanations, scoped pages, exact detail links and displayed PDF JSON CSV.
- [ ] T4 | slice=tests | files=tests/test_funnel_founder.py,tests/test_funnel_founder_clients.py,tests/test_operation_catalog.py,tests/funnel_founder.test.cjs | verify=`python -m unittest tests.test_funnel_founder tests.test_funnel_founder_clients -v` | Prove current scope, corrupt and stale evidence, page limits, no financial duplication and independent clients.
- [ ] T5 | slice=tools | files=tools/test_funnel_founder_browser.py | verify=`python -X utf8 tools/test_funnel_founder_browser.py` | Exercise real owner desktop1440/mobile390 review detail navigation exports and denied app switch.
- [ ] T6 | slice=smoke | files=smoke/funnel-founder.json | verify=`forge smoke funnel-founder --root .` | Require assertion-based stub rejection and actual guarded source-read acceptance.
