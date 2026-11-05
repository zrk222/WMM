# Spec: durable-local-stop
Status: owner-authorized automation recovery increment

## MUST - Functional core
### Description
Return a saved result when an owner retries the same local OFF request after an interrupted response. Reuse the existing owner route, SQLite writer transaction, admission guard, grant revocation and job cancellation. This is one building block for a later cross-scope Stop.

### Requirements (EARS)
- When a current owner switches an active policy OFF at its exact revision, the system shall return 1 durable local result through `stop_commit`, atomically with local revocation, cancellation and the existing audit event.
- When the same current owner and role revision submit the exact app, policy and prior revision after restart or concurrent dispatch, the system shall return 1 original receipt through `stop_replay`, with 0 repeat writes or effects.
- If the app, owner membership, prior policy revision or receipt binding differs, the system shall reject replay through `stop_scope`, with 0 disclosed receipts or new authority.
- If the local writer fails before commit, the system shall return 0 durable partial receipts through `stop_rollback` and preserve the original policy and grant state.
- If an already-off policy has no matching saved result, the system shall reject replay through `legacy_stop`, with 0 fabricated receipts or repeated cancellation.
- If an OFF request contains provider instructions, the system shall reject it through `stop_boundary` with 0 provider calls.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: stop_commit
 Given a synthetic active local standing approval
 When `stop_commit` switches it OFF at its current revision
 Then the local result and revoked authority persist together
Scenario: stop_replay
 Given the exact original OFF request
 When `stop_replay` retries concurrently or after reopening the database
 Then all successful responses are equal and the grant remains revoked
Scenario: stop_scope
 Given a changed app, owner role or prior revision
 When `stop_scope` attempts replay
 Then no receipt is returned and no state is changed
Scenario: stop_rollback
 Given an injected error before the writer commits
 When `stop_rollback` interrupts the request
 Then the policy and grant stay active and the receipt is absent
Scenario: legacy_stop
 Given an OFF policy from before receipt support
 When `legacy_stop` is retried
 Then no result is invented and cancellation does not run again
Scenario: stop_boundary
 Given a local OFF request with a provider instruction
 When `stop_boundary` checks the request
 Then it rejects the extra instruction without a provider effect
```

## Architecture and limits
One append-only receipt per policy. Capture the original version, current app and owner role version, timestamp and exact local canceled-job count. Reconstruct the existing OFF response shape from the receipt, including `dispatched_effects=INSPECT_RECEIPTS_NOT_UNDONE`. Enforce the original owner-only boundary on each call. Keep provider state, budgets, broader campaigns and cross-scope binding outside this increment.

## Authorized parameters
Synthetic concurrency test: 2 workers with a 5-second barrier timeout. No runtime policy change.
max_workers = 2
timeout = 5
