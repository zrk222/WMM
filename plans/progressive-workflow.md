# Plan: progressive-workflow
Spec: specs/progressive-workflow.md
Architect verdict: PASS

## Architecture
Reuse current source-bound guide data and guidedStep rendering. An HTML details
element discloses remaining stages with native keyboard support. Critical findings
are projected outside disclosure and escaped. No stored evidence, stage evaluator,
approval or execution behavior changes. No gain in user task time is claimed.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js | verify=`node --test tests/progressive_workflow.test.cjs` | Implement progressive_focus, progressive_blockers, progressive_states and progressive_complete.
- [ ] T2 | slice=tests | files=tests/progressive_workflow.test.cjs | verify=`node --test tests/progressive_workflow.test.cjs` | Verify collapsed and complete journeys, escaping, all stage controls and non-claim labels.

## Gates
CF strict/validator/tasks, meaningful Node tests, rendered desktop/mobile keyboard
observations and prescribed Prestige checks, privacy and hash-bound workflow audit.
This resolves a workflow presentation slice; all other report requirements remain.
