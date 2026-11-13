# Plan: verified-release-provenance
Spec: specs/verified-release-provenance.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=.github | files=.github/workflows/desktop-release.yml | verify=`python -m unittest tests.test_release_provenance -q` | Verify every staged asset before publication using exact source and signer constraints.
- [ ] T2 | slice=tests | files=tests/test_release_provenance.py | verify=`python -m unittest tests.test_release_provenance -q` | Execute the helper against a fake gh verifier and prove failure stops publish readiness.
- [ ] T3 | slice=docs | files=docs/VERIFY-RELEASE.md,docs/release-handoff.md | verify=`python -m unittest tests.test_release_provenance -q` | Document gh provenance verification and preserve unsigned-preview limits.
- [ ] T4 | slice=tools | files=tools/maintained_files.txt | verify=`python tools/check_types.py` | Enroll the provenance regression tests.
- [ ] T5 | slice=tools | files=tools/verify_release_provenance.py | verify=`python -m unittest tests.test_release_provenance -q` | Verify the exact staged asset set with official gh and retain a source-bound digest receipt.
