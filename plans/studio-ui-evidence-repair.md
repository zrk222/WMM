# Plan: studio-ui-evidence-repair
Spec: specs/studio-ui-evidence-repair.md
Architect verdict: PASS

## Architecture
Keep protected operations and source/view/request identities unchanged. Render
confirmed terminal state from returned data; retain receipt time on each snapshot.
Use native focus on replaced content or the edited parameter input.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/studio-controls.js | verify=`node --test tests/studio_controls.test.cjs` | Repair closed_truth, missing_evidence, snapshot_time and focus_transition.
- [ ] T2 | slice=tests | files=tests/studio_controls.test.cjs | verify=`node --test tests/studio_controls.test.cjs` | Exercise truth, absence boundaries, timestamps and focus regression cases.

## Gates
Strict spec, validator mutations, atomic tasks, scoped Node tests and hash-bound
workflow evidence. Parent owner retains real browser/native, privacy, Prestige,
full-suite and release gates; this scoped repair does not close those gates.
