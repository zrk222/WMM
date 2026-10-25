# Spec: studio-request-authority
Status: draft

## MUST - Functional core
### Description
Carry authenticated request authority separately from editor attribution. Bind
each operation to the exact envelope and datastore. Studio services must enter
the protected domain before observing or changing native state. Existing routes
remain unchanged; this packet establishes the authority boundary they will use.

### Requirements (EARS)
- The system shall reject protected operations without a current trusted request context or with a changed envelope or datastore through `request_binding`.
- The system shall reject revoked or changed grants, grants with at most 0 seconds remaining, and ordinary calls requiring review through `grant_current`.
- The system shall reject reviewed operations unless their claimed RUNNING checkpoint retains the exact revision and active checker through `review_current`.
- The system shall reject standing operations unless the exact execution remains DISPATCHED under its current policy through `standing_current`.
- The system shall reject human owner operations after local identity logout expiry replacement or app role changes through `human_current`.
- The system shall reject a business transaction before commit when protected authority changes and clear request contexts after success or failure through `commit_current`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: request_binding
  Given no trusted request or a changed app envelope or datastore
  When `request_binding` protects an operation
  Then it rejects without granting native authority
Scenario: grant_current
  Given an admitted grant with its last available call consumed
  When `grant_current` checks during work
  Then current authorization succeeds without another charge and revoked grants reject
Scenario: review_current
  Given a claimed RUNNING reviewed request
  When `review_current` observes cancellation or changed approval dependencies
  Then no protected operation or result commit is admitted
Scenario: standing_current
  Given an admitted standing request
  When `standing_current` observes its current execution and exact envelope
  Then only its DISPATCHED execution is accepted
Scenario: human_current
  Given a freshly verified owner at admission
  When `human_current` checks the local identity session during work
  Then logout expiry identity replacement and role changes reject without network access
Scenario: commit_current
  Given a protected business transaction and revoked authority
  When `commit_current` runs before commit
  Then its writes roll back and contexts do not leak to another request
```

## SHOULD - Boundary
Provider identity is freshly verified at HTTP admission; local mid-operation
checks do not claim instantaneous remote token revocation. Never retain bearer
credentials in native sessions, operation contexts or records. Protected authority
does not grant cleanup ownership or permit resending an uncertain mutation.
