# Plan: production-read-projection
Spec: specs/production-read-projection.md
Architect verdict: PASS

## Architecture
Extract a pure current-version projection shared by transactional context and
listing. Keep SQL predicates, immutable ordering and fresh app checks.
No process-wide cache, pooled connection or change to execution admission.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/production_feasibility.py | verify=`python -m unittest tests.test_production_feasibility -q` | Implement projection_reads and projection_consistency with one loaded history map.
- [ ] T2 | slice=tests | files=tests/test_production_feasibility.py | verify=`python -m unittest tests.test_production_feasibility -q` | Prove projection_freshness, assessment parity and SQL call bounds with populated SQLite fixtures.

## Gates
CF strict, validator mutation and tasks; populated SQLite tests, deliberate
duplicate-read mutation, privacy check and hash-bound workflow audit.
Report query reduction separately from unmeasured production latency.
