# Plan: auto-enrolling-ratchets
Spec: specs/auto-enrolling-ratchets.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=tools | files=tools/source_ratchet.py,tools/check_format.py,tools/check_types.py | verify=`python -m unittest tests.test_source_ratchet -q` | Enroll changed source deterministically and check immutable registry history.
- [ ] T2 | slice=tests | files=tests/test_source_ratchet.py,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_source_ratchet tests.test_ci_current_candidate -q` | Verify positive, deleted, rename, unknown base and missing enrollment cases.
- [ ] T3 | slice=tools | files=tools/maintained_files.txt,tools/maintained_js.txt | verify=`python tools/check_format.py` | Enroll this PR and retain sorted append-only paths.
- [ ] T4 | slice=.github/workflows | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_ci_current_candidate -q` | Fetch the exact PR base and enforce the enrollment check before source tests.
- [ ] T5 | slice=docs | files=docs/MAINTAINABILITY.md,docs/MECHANICS-PROGRAM.md | verify=`python -m unittest tests.test_source_ratchet -q` | Document the enrollment command and nine separately verified mechanics PRs.

- [ ] T6 | slice=eslint.config.mjs | files=eslint.config.mjs | verify=`python tools/check_format.py` | Apply baseline syntax-safety lint to every enrolled JavaScript file, preserving stricter dashboard-module rules.
