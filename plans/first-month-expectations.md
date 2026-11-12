# Plan: first-month-expectations
Spec: specs/first-month-expectations.md
Architect verdict: PASS

## Logical decomposition
1. Align public expectations and setup guidance.
2. Present the same boundaries in desktop and native introductions.
3. Verify rendered copy and preserve existing workflow behavior.

## Tasks
- [ ] T1 | slice=README.md | files=README.md | verify=`python -m unittest tests.test_onboarding_language tests.test_licensing_plain` | Introduce first-day and regular-use expectations in the repository overview.
- [ ] T2 | slice=docs | files=docs/POSITIONING.md,docs/desktop-first-run.md,docs/index.html | verify=`python -m unittest tests.test_onboarding_language tests.test_licensing_plain` | Align public positioning and first-run guidance.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/index.html,mission_control/static/page-reporting.js | verify=`python tools/test_goal_journey_browser.py` | Update desktop copy with no new effects.
- [ ] T4 | slice=tools | files=tools/test_goal_journey_browser.py | verify=`python tools/test_goal_journey_browser.py` | Verify the current headings and first-month text in the rendered interface.
- [ ] T5 | slice=ios | files=ios/WMM/Workflow/WorkflowNavigation.swift | verify=`python tools/check_platform_receipts.py --ci-contract` | Render native copy with semantic text and 680 point reading width.
- [ ] T6 | slice=tests | files=tests/page_reporting.test.cjs | verify=`node --test tests/page_reporting.test.cjs` | Verify overview expectations preserve source and approval limits.
- [ ] T7 | slice=docs/images | files=docs/images/goal-to-proof.png,docs/images/overview.png,docs/images/provenance.json | verify=`python tools/check_distribution.py` | Refresh actual synthetic overview screenshots from the candidate UI.
