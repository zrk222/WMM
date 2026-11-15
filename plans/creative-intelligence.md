# Plan: creative-intelligence
Spec: specs/creative-intelligence.md
Architect verdict: PASS

- [x] T1 | slice=mission_control | files=mission_control/creative_intelligence.py,mission_control/organic_video_collector.py | verify=`python -m unittest tests.test_organic_video_discovery tests.test_organic_video_collector` | Derive a bounded evidence-ranked shortlist from the checked app research submission.
- [x] T2 | slice=mission_control | files=mission_control/static/organic-research.js | verify=`node --test tests/organic_research_ui.test.cjs` | Surface shared reasons, promising-pattern state and an exact existing source review action.
- [x] T3 | slice=tests | files=tests/test_organic_video_discovery.py,tests/organic_research_ui.test.cjs | verify=`python -m unittest tests.test_organic_video_discovery` | Prove distinct creators, stable ordering, tiers and unchanged admission.
- [x] T4 | slice=mission_control | files=mission_control/organic_video_collector.py | verify=`python -m unittest tests.test_organic_research_http` | Verify the current app-scoped owner and agent retention boundaries.

Follow-up work: first-run app profiling, saved per-app subscriptions to research, source coverage by terms and access, creative evaluation plus reporting, and a timed dogfood experiment. Keep coverage and data permissions separate from delivery and commercial outcomes.
