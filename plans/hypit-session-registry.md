# Plan: hypit-session-registry
Spec: specs/hypit-session-registry.md
Architect verdict: PASS

## Architecture
Use an app-owned SQLite registry table with immutable intent and complete bounded
hash-linked state history. BEGIN IMMEDIATE serializes reservations, retries,
datastore-wide capacity checks and versioned transitions. Return launch permission
only to the caller that inserted a new PREPARED reservation; never reconstruct it
from persisted state. Scan and validate bounded records before capacity decisions.
Keep validation and projection separate from transactional methods. Finalization
does not bypass request guards: the future manager must leave its protected
context before narrowly recording already-owned cleanup outcomes.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hypit_studio_registry.py,mission_control/db.py | verify=`python -m unittest tests.test_hypit_studio_registry -v` | Implement registry_once, registry_retry, registry_capacity, registry_integrity, registry_restart and registry_recovery.
- [ ] T2 | slice=tests | files=tests/test_hypit_studio_registry.py | verify=`python -m unittest tests.test_hypit_studio_registry -v` | Prove actual concurrent SQLite reservation, restart ceilings, transition rollback and privacy with synthetic inputs.

## Gates
CF strict/validator/task checks, behavioral guard mutants, current tests and privacy,
independent Astra review and hash-bound workflow QA. Public service, native cleanup
proof, isolated factory, shared clients and full editor remain parent work.
