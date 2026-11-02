# Spec: durable-agent-handoffs
Status: approved

## MUST - Durable replacement-agent handoff
### Description
Provide immutable secret-free task context for an existing app-owned canonical worker job. A handoff transfers no execution authority and never enqueues or dispatches work. Native jobs outside the worker ledger are explicitly unsupported until separately implemented.

### Requirements (EARS)
- The system shall store an existing worker job identifier, action, immutable job fingerprint and request-key digest, current app revision and hash, policy hash, catalog hash, allowlisted referenced-resource revision fingerprint, selected operation names, recipient and expiry through `handoff_create`.
- The system shall accept a current verified owner without a source grant or a current scoped agent with a source grant, and reject foreign jobs, unknown fields, stale context and revoked source grants through `handoff_validation`.
- The system shall reject a missing current scoped grant for the designated recipient and return only the intersection of the selected operations with that grant through `handoff_admission`.
- The system shall preserve the original job identifier and request-key digest, return a stable claim receipt for an exact retry within 24 hours and never enqueue or resend a job on resume through `handoff_recovery`.
- The system shall expose owner inspection and optimistic revocation and return only allowlisted secret-free task fields through `handoff_privacy`.
- The system shall retain downstream authorization and human review checks and represent running or uncertain work as requiring inspection through `handoff_authority`.
- The system shall return the same durable identifiers and current job status to local owner and scoped agent clients through `handoff_clients`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: handoff_create
  Given an existing isolated worker job and current owner or source grant
  When `handoff_create` freezes the selected job
  Then its original identifier, request-key digest and context hashes are immutable
Scenario: handoff_validation
  Given a foreign job, stale revision or revoked source grant
  When `handoff_validation` checks the request
  Then the handoff is rejected before admission
Scenario: handoff_admission
  Given a current separately issued grant for the designated recipient
  When `handoff_admission` checks the current grant and frozen task scope
  Then one claim is recorded without creating or widening authority
Scenario: handoff_recovery
  Given concurrent resume requests for the same handoff
  When `handoff_recovery` returns the existing job
  Then the same recipient obtains the same claim and no job is re-enqueued
Scenario: handoff_privacy
  Given an owner revokes a handoff and inspects its public data
  When `handoff_privacy` returns the record
  Then credentials and raw request keys are excluded and future claims are denied
Scenario: handoff_authority
  Given an existing running job with uncertain completion
  When `handoff_authority` describes the next action
  Then the job is inspected and no execution approval is inferred
Scenario: handoff_clients
  Given owner and scoped clients in an isolated workspace
  When `handoff_clients` use the bounded contract
  Then they observe matching durable identifiers and current status
```

## SHOULD - Technical
- Limits: maximum handoff lifetime is 24 hours; source grant expiry additionally bounds agent-created handoffs. Existing grant call ceilings remain 1 through 10000. The caller supplies no job payload, prompt, raw request key or credential in the handoff object.
- Current grant admission consumes only the existing actual operation call. A claim transaction revalidates source, recipient, app, policy, catalog, job identity, immutable job fingerprint and allowlisted referenced-resource revisions. Unknown resource identifier fields are counted as unverified; downstream validation is still required. Different claimants are rejected; a same-grant retry is idempotent after fresh admission. Revocation blocks future claims, while admitted work is not cancelled.
- Resume reports RESUME_ADMITTED and the existing job state, not execution completion. Native job tables not represented by the worker ledger remain explicitly unsupported. No background execution, external effect, provider support, human acceptance or physical-device claim is implied.

## Authorized parameters
MAX_HANDOFF_HOURS = 24
max_calls = 1
max_calls = 10000
limit = 100
timeout = 15
