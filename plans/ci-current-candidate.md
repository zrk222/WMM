# Plan: ci-current-candidate
Spec: specs/ci-current-candidate.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=.github/workflows | files=.github/workflows/checks.yml,.github/workflows/platform-checks.yml,.github/workflows/desktop-packages.yml | verify=`python -m unittest tests.test_platform_receipts tests.test_ci_current_candidate` | Keep current candidate jobs with unchanged test scope.
- [ ] T2 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate` | Assert event routing concurrency and preserved matrices.
