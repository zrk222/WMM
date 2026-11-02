# Spec: campaign-schedule-ui
Status: draft

## MUST - Functional core
### Description
Expose existing owner campaign schedule services in protected campaign HTTP and UI; exact finite post batches, no ad scheduler claim.

### Requirements (EARS)
- The system shall reject a scheduled batch mutation without fresh authenticated owner session, exact local origin and CSRF through `owner_http`.
- The system shall display exact post content and due times before owner activation through `exact_batch_review`.
- The system shall display saved batch status and job or intent identities without automatic replay through `durable_status`.
- When the owner selects OFF, the system shall cancel undispatched batch items and display dispatched uncertainty through `stop_control`.
- The system shall reject paid schedule selection until paid scheduled execution is implemented through `no_paid_claim`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: owner_http
 Given a missing or stale owner request
 When `owner_http` checks the scheduled operation
 Then no schedule mutation occurs
Scenario: exact_batch_review
 Given an approved campaign scope and chosen due times
 When `exact_batch_review` checks the scheduled operation
 Then owner activation binds the displayed summary hash
Scenario: durable_status
 Given a saved scheduled batch
 When `durable_status` checks the scheduled operation
 Then reloading displays durable state and no new effects
Scenario: stop_control
 Given an active scheduled batch
 When `stop_control` checks the scheduled operation
 Then future undispatched items are cancelled and dispatched results remain explicit
Scenario: no_paid_claim
 Given a paid campaign plan
 When `no_paid_claim` checks the scheduled operation
 Then no paid schedule activation occurs
```

## SHOULD - Technical
- Reuse same protected campaign owner dispatcher and finite schedule capability. No new generic operation, provider transport, authority or worker engine.
- Default scheduling disabled. No credentials in forms or reports. Expiry within existing campaign scope.
