# Plan: goal-first-automation
Spec: specs/goal-first-automation.md
Architect verdict: PASS

## Architecture
Pure frontend projection over current workspace facts. Retain existing routes and authority. Local goal choice is app-scoped presentation only. Backend slices need their own contracts.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/app.js,mission_control/static/index.html,mission_control/static/style.css | verify=`node --test tests/goal_journey.test.cjs` | Implement three-choice navigation and app-scoped goal guidance.
- [ ] T2 | slice=tests | files=tests/goal_journey.test.cjs | verify=`node --test tests/goal_journey.test.cjs` | Prove app isolation, unknown preference rejection, storage recovery, source escaping and no automatic effects.

- [ ] T3 | slice=tools | files=tools/test_goal_journey_browser.py | verify=`python tools/test_goal_journey_browser.py` | Exercise default home, explicit selection, advanced tools, app isolation and report in actual desktop/mobile browser.

## Full goal roadmap
1. Goal-first navigation and fixed outcome selection.
2. Outcome setup inventory and repairs through existing Readiness.report.
3. Unified owner-facing agreement wrapping distinct enforced scopes.
4. Persistent approved campaign batches and bounded monitoring, measurement and owner reports through existing worker.
5. Packaged desktop first-use and optional authenticated always-on worker. Preserve standalone native iOS.

## Gates
CF doctor and strict SpecLine/validator/spec/plan seals before implementation. Focused tests, actual desktop/mobile browser, Prestige and hash-bound workflow audit before slice completion. Provider/unattended acceptance awaits its own implementation. Full goal remains active.
