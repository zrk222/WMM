# Plan: shrinkable-properties
Spec: specs/shrinkable-properties.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=tests | files=tests/test_parser_properties.py,tests/test_property_profiles.py | verify=`python -m unittest tests.test_parser_properties tests.test_property_profiles -q` | Convert four property families to shrinking strategies and keep named counterexamples.
- [ ] T2 | slice=docs | files=docs/requirements-properties.txt,docs/MAINTAINABILITY.md | verify=`python -m pip install --require-hashes --only-binary :all: -r docs/requirements-properties.txt` | Pin universal test wheels and document permanent regressions.
- [ ] T3 | slice=.github/workflows | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_ci_current_candidate -q` | Provision properties in core profiles and persist synthetic examples with trust- and shard-scoped keys.
- [ ] T4 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate -q` | Retain existing CI job definitions while approving the explicit property profile additions.
- [ ] T5 | slice=tools | files=tools/maintained_files.txt,tools/maintained_js.txt | verify=`python tools/source_ratchet.py --base codex/wmm-sqlite-write-serialization` | Enroll new test source in the existing quality ratchets.

- [ ] T6 | slice=.gitignore | files=.gitignore | verify=`python -m unittest tests.test_property_profiles -q` | Exclude Hypothesis auxiliary caches from source distribution.
