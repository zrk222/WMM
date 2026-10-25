# Plan: marketer-gap-integration
Spec: specs/marketer-gap-integration.md
Architect verdict: PASS

## Architecture
Source-bound documentation only; extend the active goal without runtime changes.

## Tasks
- [ ] T1 | slice=specs | files=specs/wmm-marketer-gap-review.json,specs/marketer-gap-integration.md | verify=`python work/check_marketer_goal.py` | Record marketer_coverage and marketer_accuracy.
- [ ] T2 | slice=docs | files=docs/WMM-MARKETER-WORKFLOWS.md | verify=`python work/check_marketer_goal.py` | Verify marketer_goal preserves earlier scope.

## Gates
CF strict, validator mutation, tasks, report/source hashes and workflow audit.
Verification script runs from chat workspace with exact WMM root.
