# Spec: sqlite-write-serialization
Status: approved

## MUST - Functional core
### Description
Serialize declared SQLite write scopes while retaining read behavior and authority guards.
### Requirements (EARS)
- The system shall start declared write transactions with BEGIN IMMEDIATE before guards and snapshot reads under `write_lock`.
- The system shall return read connections without reserving the writer lock under `read_path`.
- The system shall reject nested declared write transactions without rolling back an existing owner transaction under `rollback`.
- The system shall store committed writes with synchronous FULL and preserve rollback on failures under `durability`.
- The system shall store the updates of two serialized writers deterministically without query-budget regressions under `contention`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: write_lock
 Given an isolated SQLite workspace
 When `write_lock` executes
 Then the declared transaction invariant is verified
Scenario: read_path
 Given an isolated SQLite workspace
 When `read_path` executes
 Then the declared transaction invariant is verified
Scenario: rollback
 Given an isolated SQLite workspace
 When `rollback` executes
 Then the declared transaction invariant is verified
Scenario: durability
 Given an isolated SQLite workspace
 When `durability` executes
 Then the declared transaction invariant is verified
Scenario: contention
 Given an isolated SQLite workspace
 When `contention` executes
 Then the declared transaction invariant is verified
```

## SHOULD - Technical
Use explicit write=True scopes. Keep legacy isolation for unconverted callers, existing explicit BEGIN and query-only snapshots unchanged. Never hold the lock across provider calls. Do not declare full write-call-graph coverage from literal SQL classification.
