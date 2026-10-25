# Plan: ci-test-sharding
Spec: specs/ci-test-sharding.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=tools | files=tools/run_ci_tests.py | verify=`python -m unittest tests.test_ci_runner -v` | Implement complete_inventory, balanced_assignment, invalid_shards, visible_execution and planning_only.
- [ ] T2 | slice=tests | files=tests/test_ci_runner.py | verify=`python -m unittest tests.test_ci_runner -v` | Exercise miniature CLI runs, exact duplicate occurrence assignment, import errors, empty selections and planning without execution.

## Gates
CF strict, validator mutations, task lint, meaningful assignment sabotage tests,
focused unittest and hash-bound workflow audit. Root owns hosted workflow matrix,
45 minute timeout and existing profile. No runtime test exclusions or fake skips.
Plan-only repository discovery is inventory evidence, not a full-suite pass.
