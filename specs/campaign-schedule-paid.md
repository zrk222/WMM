# Spec: campaign-schedule-paid
Status: draft

## MUST - Functional core
### Description
Extend finite exact owner-reviewed scheduling to fixed Meta engagement promotions of an existing verified Page post. Existing scopes and protective controls remain independent.

### Requirements (EARS)
- The system shall reject a changed scheduled operation or request outside its owner-reviewed batch and current campaign scope through `typed_binding`.
- When a paid item is prepared, the system shall require a verified saved Page post and approved targeting, rights, content, finite budget and end time through `paid_review`.
- When the worker starts a paid item, the system shall reuse existing campaign budget admission and check the retained exact operation at every provider boundary through `paid_admission`.
- If a paid operation is interrupted, the system shall store its commitment and reject automatic mutation replay through `paid_recovery`.
- When an existing owner requests pause or reconciliation, the system shall invoke the separately authorized campaign controls with at most 160 provider checks per category through `protective_controls`.
- The system shall return the original post-only batch meaning and effective delivery state with the raw job state through `status_compatibility`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: typed_binding
  Given an approved scheduled promotion
  When `typed_binding` detects a changed operation or request
  Then no provider effect is admitted
Scenario: paid_review
  Given an unverified Page post or unapproved targeting
  When `paid_review` evaluates a promotion
  Then the owner cannot approve the scheduled promotion
Scenario: paid_admission
  Given concurrent due promotions and one remaining commitment allowance
  When `paid_admission` reserves both promotions
  Then at most one commitment is admitted
Scenario: paid_recovery
  Given a provider mutation whose response is lost
  When `paid_recovery` examines the interrupted intent
  Then its commitment remains held and it is not automatically replayed
Scenario: protective_controls
  Given an expired or revoked paid scope
  When `protective_controls` admits a separately authorized owner pause
  Then the existing provider readback path remains available
Scenario: status_compatibility
  Given an older post-only batch and saved provider receipt
  When `status_compatibility` reads the batch
  Then the original post meaning and effective receipt state remain visible
```

## SHOULD - Technical
- Schedule only fixed existing verified Page posts, not generated future content.
- Preserve maximum 20 batch items and expiry within the existing 24-hour campaign scope.
- Reuse campaign intent IDs, account-level commitment holds and existing protective controls.
- Live provider acceptance is NOT_RUN.

## Authorized parameters
MAX_ITEMS = 20
MAX_HOURS = 24
MAX_DUE_PER_TICK = 20
