# Spec: content-packaging-t3
Status: scoped domain transport integration

## MUST - Functional core
### Requirements (EARS)
- When `PACKAGING_CALL` is made through owner HTTP, scoped CLI or official MCP, the system shall return the same authoritative app-scoped packaging save, read and 100-row compact summary history behavior. [R1]
- When `INVALID_CALL` has foreign app scope, stale app or document revision, revoked authority, a nonexact path, duplicate JSON keys or forged approval fields, the system shall reject it before the protected domain commit. [R2]
- When `REVIEWED_WRITE` requires human review under its grant, the system shall reject ordinary dispatch and execute only its exact saved envelope after a distinct current checker approves it. [R3]
- When `UNCERTAIN_WRITE` is reconciled, the system shall return MATCHING_REVISION_OBSERVED, DIFFERENT_REVISION_OBSERVED or NO_REVISION_OBSERVED using the exact app, identity and expected next revision, with 0 resubmissions and without claiming which caller committed it. [R4]
- When `AUTOMATION_SCOPE` selects local evidence operations, the system shall return packaging operation descriptors in the existing workflow and domain catalogs without granting execution, publication or spending authority. [R5]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Shared clients
 Given PACKAGING_CALL has current scoped authority
 When PACKAGING_CALL saves and reads a variant and shot list
 Then R1 returns identical immutable documents through each client
Scenario: Fail closed
 Given INVALID_CALL has stale or revoked authority
 When INVALID_CALL reaches the domain boundary
 Then R2 rejects it without another saved revision
Scenario: Reviewed write
 Given REVIEWED_WRITE is frozen under an owner-selected review policy
 When REVIEWED_WRITE receives a separate checker approval
 Then R3 executes its exact envelope once
Scenario: Lost response
 Given UNCERTAIN_WRITE may have committed
 When UNCERTAIN_WRITE is reconciled
 Then R4 reports observed state without resubmission
Scenario: Standing preparation
 Given AUTOMATION_SCOPE selects local evidence
 When AUTOMATION_SCOPE is discovered
 Then R5 includes packaging preparation without effect authority
```

No live YouTube collection, feed preview, rendering, provider access, publication
or paid execution is introduced by this transport packet. Those existing T2/T4-T7
requirements remain separate implementation work. Reconciliation is observation,
not a durable caller attribution or authorization to retry.
