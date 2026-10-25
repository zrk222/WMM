# Spec: hypit-parameter-broker
Status: draft

## MUST - Functional core
### Description
Connect the existing owned Studio process, opaque compiled controls and durable
source ledger through one internal parameter transaction broker. Public grant,
checkpoint, UI/CLI/MCP wiring and preview isolation remain required parent work.
The trusted caller supplies a fresh authority callback; request data cannot
establish identity or execution approval.

### Requirements (EARS)
- The system shall reject Studio start, read and edit operations after app context or trusted caller authority changes through `broker_authority`.
- The system shall return app/session-scoped opaque compiled controls with the exact durable source head and reject stale view, source and field bindings through `broker_view`.
- The system shall store an edit intent before sending exactly 1 native parameter mutation and return saved identical retry receipts without sending again through `broker_once`.
- The system shall send only the fixed owned loopback mutation route with at most 1048576 request bytes and a 20 second deadline while checking the owned child job, listener and immutable runtime/source identities through `broker_transport`.
- The system shall store APPLIED only after a valid native success revision equals a fresh compiled snapshot and its exact source closure matches disk; no-op revisions and native value normalization remain valid through `broker_result`.
- The system shall store REJECTED only after a definitive rejection and a healthy observed snapshot with unchanged source bytes, and retain PREPARED or UNCERTAIN otherwise without automatic resend through `broker_uncertainty`.
- The system shall return inspect-only current controls and source hashes for unresolved edits, omit source text, native IDs and diagnostics from public results, and stop only its owned child job through `broker_inspection`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: broker_authority
  Given a running owned Studio and changed app context or revoked caller
  When `broker_authority` is checked before dispatch or during response read
  Then no new mutation is admitted and ambiguous work remains inspectable
Scenario: broker_view
  Given a current compiled view and durable source head
  When `broker_view` receives stale or foreign parameter identities
  Then it rejects without sending a native mutation
Scenario: broker_once
  Given racing requests with the same frozen retry key
  When `broker_once` prepares and executes the edit
  Then at most one native send occurs and retries return its retained result
Scenario: broker_transport
  Given a foreign listener or an expired observation deadline
  When `broker_transport` operates
  Then the request stops without following another destination
Scenario: broker_result
  Given native success or an accepted no-op with normalized parameter values
  When `broker_result` verifies the source and snapshot
  Then the exact observed source revision is retained before process hash adoption
Scenario: broker_uncertainty
  Given a timeout malformed response failed rollback or revision mismatch
  When `broker_uncertainty` records the outcome
  Then another edit cannot silently resend or replace the unresolved attempt
Scenario: broker_inspection
  Given an unresolved edit or revoked caller
  When `broker_inspection` reads or closes the session
  Then authorized inspection excludes private source metadata and owned cleanup remains possible
```

## Authorized parameters
MUTATION_SECONDS = 20
MAX_MUTATION_BYTES = 1048576
MAX_RESPONSE_BYTES = 8388608

## SHOULD - Acceptance
Use upstream schema, author-value conversion and preimage transactions. Do not
require submitted display values to equal compiled public author values. Preserve
actual normalized values and source hashes. Confirm success against the exact
returned revision; a later revision is not attributed to this edit. Unresolved
reconciliation must not infer completion from an old snapshot or restart a PID.
An internal callback is not a public authentication or approval implementation.
