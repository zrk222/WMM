# Plan: safe-branch-hygiene
Spec: specs/safe-branch-hygiene.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=tools | files=tools/branch_hygiene.py | verify=`python -m unittest tests.test_repo_hygiene -q` | Plan exact eligible refs and recheck authority before remote deletion.
- [ ] T2 | slice=tests | files=tests/test_repo_hygiene.py | verify=`python -m unittest tests.test_repo_hygiene -q` | Prove all exclusion and stale-head paths prevent deletion.
- [ ] T3 | slice=.github | files=.github/workflows/hygiene.yml | verify=`python -m unittest tests.test_repo_hygiene -q` | Retain manifest artifact before deletion and default scheduled cleanup on.
- [ ] T4 | slice=tools | files=tools/maintained_files.txt | verify=`python tools/check_types.py` | Enroll hygiene source and tests.
- [ ] T5 | slice=docs | files=docs/REPOSITORY-HYGIENE.md | verify=`python -m unittest tests.test_repo_hygiene -q` | Document eligibility, dry-run, receipts and residual provider race.
