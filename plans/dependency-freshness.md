# Plan: dependency-freshness
Spec: specs/dependency-freshness.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=.github | files=.github/dependabot.yml,.github/workflows/dependency-freshness.yml | verify=`python -m unittest tests.test_dependency_freshness -q` | Schedule reviewed grouped proposals and locked vulnerability checks with retained receipts.
- [ ] T2 | slice=tools | files=tools/dependency_freshness.py | verify=`python -m unittest tests.test_dependency_freshness -q` | Validate exact pins and prepare only verified FFmpeg data-file updates.
- [ ] T3 | slice=tests | files=tests/test_dependency_freshness.py | verify=`python -m unittest tests.test_dependency_freshness -q` | Reject unverified assets, baseline drift, malformed metadata and loose pins.
- [ ] T4 | slice=docs | files=docs/requirements-audit.in,docs/requirements-audit.txt | verify=`python -m pip install --dry-run --require-hashes -r docs/requirements-audit.txt` | Lock the audit tool and transitive packages.
- [ ] T5 | slice=.github | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_ci_current_candidate -q` | Allow explicit checked branch/base dispatch for bot-created update PRs.
- [ ] T6 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate -q` | Pin the reviewed dispatch route and preserve remaining job matrices.
- [ ] T7 | slice=docs | files=docs/DEPENDENCY-FRESHNESS.md | verify=`python -m unittest tests.test_dependency_freshness -q` | Explain audit scope, update review and explicit missing-evidence states.
- [ ] T8 | slice=tools | files=tools/maintained_files.txt | verify=`python tools/check_types.py` | Enroll new maintenance source and tests.
- [ ] T9 | slice=tools | files=tools/ffmpeg-pin.json | verify=`python -m unittest tests.test_dependency_freshness -q` | Separate binary version/digest data from workflow permissions so future proposals touch only the pin.
