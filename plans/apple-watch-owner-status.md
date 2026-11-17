# Plan: apple-watch-owner-status
Spec: specs/apple-watch-owner-status.md
Architect verdict: PASS

## Architecture
Project the bound availability read in the existing Apple readiness summary. Pass only a small outcome and one action to the guided workflow. No additional provider call, campaign scope, or credential change.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/apple_readiness_report.py,mission_control/service.py | verify=`python -m pytest -q tests/test_apple_inventory_watch.py tests/test_apple_readiness_report.py` | Classify the exact saved inventory and distinguish Detailed files from general availability.
- [ ] T2 | slice=mission_control/static | files=mission_control/static/guided-workflow.mjs | verify=`node --test tests/goal_readiness_ui.test.cjs` | Show the labeled Apple repair action for the current workflow.
- [ ] T3 | slice=tests | files=tests/test_apple_inventory_watch.py,tests/goal_readiness_ui.test.cjs | verify=`python -m pytest -q tests/test_apple_inventory_watch.py` | Verify privacy, evidence bounds and visible next actions for the saved read.

## Gates
Code Factory workflow audit, focused regression, current-source and desktop/mobile rendering evidence.
