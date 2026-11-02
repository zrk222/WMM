# Plan: goal-connection-wizard
Spec: specs/goal-connection-wizard.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/app.js | verify=`node --test tests/goal_readiness_ui.test.cjs` | Add read-only owner connection wizard using existing readiness route.
- [ ] T2 | slice=tests | files=tests/goal_readiness_ui.test.cjs | verify=`node --test tests/goal_readiness_ui.test.cjs` | Verify exact selection, noauthority, stale readback and fixed repair routes.
