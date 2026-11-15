# Plan: owner-agreement-from-watch
Spec: specs/owner-agreement-from-watch.md
Architect verdict: PASS

- [ ] T1 | slice=mission_control | files=mission_control/static/app-research.mjs,mission_control/static/guided-workflow.mjs | verify=`node --test tests/automation_agreement_ui.test.cjs` | Place the existing agreement in Watch and enforce one shared entry gate before loading owner-only histories.
- [ ] T2 | slice=tests | files=tests/automation_agreement_ui.test.cjs | verify=`node --test tests/automation_agreement_ui.test.cjs` | Verify guest, wrong-role and stale identity behavior without network effects.
- [ ] T3 | slice=docs | files=docs/desktop-first-run.md | verify=`specline strict owner-agreement-from-watch` | Describe where to find the same read-only summary from Watch or Advanced.
