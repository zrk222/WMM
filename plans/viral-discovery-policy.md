# Plan: viral-discovery-policy
Spec: specs/viral-discovery-policy.md
Architect verdict: PASS

## Architecture
Normalize closed supplied observations, require exact same creator/platform/format,
select recent prior comparable identities and compute an exact median. Require
both absolute and relative thresholds. The pure policy returns source-bound
receipts, never executes discovery or claims reuse authority. Collection inventory,
freshness and permission verification precede actual queue admission in UPG-09.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/viral_policy.py | verify=`python -m unittest tests.test_viral_policy -v` | Implement creator_baseline, viral_cutoff, observation_validation, qualification_receipt and approval_boundary without network effects.
- [x] T2 | slice=tests | files=tests/test_viral_policy.py | verify=`python -m unittest tests.test_viral_policy -v` | Cover both cutoff boundaries, odd/even medians, zero baseline, insufficient samples, candidate exclusion, creator/platform/format mismatch, duplicates, timestamps and deterministic receipts.

## Acceptance
Strict CF spec/plan and requirement mutations precede implementation; require
source mutants, privacy and workflow evidence afterward. The whole discovery and
editing workflow cannot be claimed complete from this policy function.
