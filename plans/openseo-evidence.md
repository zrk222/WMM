# Plan: openseo-evidence
Spec: specs/openseo-evidence.md (approved scope: user requested built-in integration)

- [x] T1 | slice=engine | files=mission_control/web_search_evidence.py,mission_control/growth_review_contract.py,mission_control/operation_catalog.py,tests/test_web_search_evidence.py | verify=`python -m unittest tests.test_web_search_evidence tests.test_market_research` | Validate and project separate app-bound web evidence, preserving unavailable metrics.
- [x] T2 | slice=ui | files=mission_control/static/growth-review.js,tests/market_research_ui.test.cjs,docs/market-research.md | verify=`node --test tests/market_research_ui.test.cjs` | Surface actions, source and units in the preview, saved report, PDF and structured export.
- [x] T3 | slice=verification | files=specs/openseo-evidence.md,plans/openseo-evidence.md | verify=`specline validate openseo-evidence` | Record scope and candidate-bound workflow evidence.
- [x] T4 | slice=native | files=mission_control/openseo_transport.py,mission_control/openseo_read.py,mission_control/insights.py,mission_control/insights_contract.py,mission_control/insights_transport.py,mission_control/insights_http.py | verify=`python -m unittest tests.test_openseo_read tests.test_openseo_transport` | Reuse vault, connection leases and schedules for fixed-endpoint, non-billable native reads.
- [x] T5 | slice=agents | files=mission_control/operation_runtime.py,mission_control/automation_requirements.py,mission_control/marketing_agent_manifest.py,tests/test_openseo_agent.py | verify=`python -m unittest tests.test_openseo_agent.OpenSEOAgentTests` | Require exact scoped agent admission and retained native report bindings.
- [x] T6 | slice=browser | files=mission_control/static/insights.mjs,mission_control/static/openseo-scope.mjs,tsconfig.maintained-js.json,tests/test_openseo_browser.py | verify=`WMM_BROWSER_TEST_PROFILE=1 python -m unittest tests.test_openseo_browser` | Exercise connection, retrieval, save, responsive reports and PDF with synthetic provider responses.


