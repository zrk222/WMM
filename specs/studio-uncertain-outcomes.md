# Spec: studio-uncertain-outcomes
Status: draft

## MUST - Functional core
### Description
Preserve uncertain native effects through reviewed and standing execution. An
upstream edit may change files without a corresponding WMM business commit.
Explicit uncertainty must override ordinary validation and cancellation outcomes.
This packet does not expose public Studio operations or infer safe resend.

### Requirements (EARS)
- The system shall return a fixed public uncertain-effect error after a prepared Studio edit cannot confirm its result through `studio_uncertain`.
- The system shall store UNKNOWN for a reviewed uncertain effect and reject another execution of the claimed request through `review_uncertain`.
- The system shall store UNKNOWN for a standing uncertain effect even with 0 local write commits or cancellation through `standing_uncertain`.
- The system shall store definitive validation failures as FAILED and return verified native acceptance or rejection receipts through `known_outcomes`.
- The system shall reject exposure of raw native errors and retain durable unresolved attempts without another native send through `uncertain_privacy`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: studio_uncertain
  Given a prepared edit and an unconfirmed response or revoked authority
  When `studio_uncertain` handles the error after preparation
  Then a typed uncertain effect preserves inspection requirements
Scenario: review_uncertain
  Given an approved exact reviewed request
  When `review_uncertain` receives a typed uncertain effect
  Then its checkpoint is UNKNOWN and repeated execution is rejected
Scenario: standing_uncertain
  Given a dispatched standing request with no local business commit
  When `standing_uncertain` receives a typed uncertain effect during cancellation
  Then its saved outcome remains UNKNOWN
Scenario: known_outcomes
  Given validation before native intent or a verified native result
  When `known_outcomes` classifies the operation
  Then existing definitive outcomes remain unchanged
Scenario: uncertain_privacy
  Given a private native error and retained uncertain attempt
  When `uncertain_privacy` exposes the error and inspects an identical retry
  Then private diagnostics are absent and another native send does not occur
```

## Authorized parameters
NATIVE_SENDS_PER_ATTEMPT = 1
