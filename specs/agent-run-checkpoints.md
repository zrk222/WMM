# Spec: agent-run-checkpoints
Status: draft
SpecFactor-target: 0.75–2.5

## MUST — Functional core
### Description
Persist app-scoped checkpoints for a bounded local operation. This internal trusted-service packet does not authenticate callers, expose execution over HTTP, or execute effects. Adapters must authenticate principals before invoking it.

### User roles
- Trusted adapter maker and distinct checker, authenticated outside this internal module.

### Requirements (EARS)
<!-- Every requirement uses an EARS keyword: shall / When / While / If / Where -->
- The system shall store `checkpoint_packet` with an immutable request, maker role, agent identity, app version and expiry.
- The system shall require `distinct_checker` with a current app role and exact packet hash before claim.
- The system shall reject repeated `single_claim` using a current revision and transactional state change.
- The system shall return `durable_recovery` after restart and reject subsequent claims after ambiguous outcomes or cancellation during execution.
- The system shall reject `stale_authority` after expiry, role revocation or app changes before claim.
- The system shall store `checkpoint_history` without exporting approval authority or calling external providers.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Immutable request
  Given an active maker
  When `checkpoint_packet` is replayed
  Then an identical request retains its identity and changed content is rejected
Scenario: Independent review
  Given a waiting checkpoint
  When `distinct_checker` approves its exact hash
  Then self review is denied and a distinct active checker is recorded
Scenario: Concurrent dispatch
  Given an approved checkpoint
  When `single_claim` is attempted twice
  Then only one caller claims and no effect is dispatched by this module
Scenario: Interrupted action
  Given a claimed checkpoint
  When `durable_recovery` resumes after restart
  Then reconciliation is required and it cannot be claimed again
Scenario: Changed authorization
  Given an approved checkpoint
  When `stale_authority` detects changed roles, app or expiry
  Then dispatch admission is denied
Scenario: Historical boundary
  Given terminal work
  When `checkpoint_history` is inspected
  Then recorded transitions survive without credentials or execution authority
```

## SHOULD — Technical/structural
- Lifetime is greater than zero and at most 24 hours. Input and receipt references use 64 lowercase hexadecimal characters.
- The competing-claim fixture uses two concurrent clients.
- Supported operation identifiers are READ_WORKSPACE, RECOMPUTE_REPORT and PREPARE_DRAFT. Admission does not execute these operations.
- Checkpoints are excluded from portable snapshots. Direct local database access remains a trusted process boundary.
- Cancel before claim is terminal. Cancel during execution requires reconciliation. Terminal outcomes never rearm a claim.

## SHOULD NOT — Implementation details
<!-- Leave the "how" to the plan/tasks unless it is a systemic invariant -->
- Caller-supplied principal names must never be presented as authentication or proof of a human. HTTP authentication, owner-issued agent grants, operation-specific validators, authenticated review UI and independent client conformance remain future packets.

## Decision logic (factory candidates)
<!-- Ordered business rules over extracted facts. specline handoff compiles
     these via HSF instead of letting agents improvise them. -->
| # | if | then |
|---|----|------|

## Authorized parameters
The competing-claim acceptance test must use two workers to test exclusive admission.
max_workers = 2
