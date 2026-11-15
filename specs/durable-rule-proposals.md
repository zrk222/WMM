# Spec: durable-rule-proposals
Status: approved

## MUST - Functional core

### Requirements (EARS)

- When an owner runs an exact saved rule version for the current app, the system shall save a proposal-only evaluation and its evidence fingerprints in `rule_inbox_retention`. Preview remains read-only.
- When an owner opens or dismisses a proposal, the system shall use `rule_inbox_review` to reject a foreign app or owner. A dismissal retains history and grants no action.
- When an owner explicitly enables `rule_schedule_consent`, the system shall record the exact app version, owner role revision, saved rule version and hash, cadence of 1 to 24 hours, end time within 7 days and a cap of 30 runs. Return OFF, EXPIRED, BLOCKED or EXHAUSTED as applicable.
- When a run is due, the system shall use `rule_schedule_receipt` to atomically save evaluation outcomes and advance the due slot. Restart, missed slots and simultaneous workers must not duplicate a run.
- When an unchanged proposal repeats or its cooldown has not elapsed, the system shall record the suppression cause through `rule_proposal_cooldown`; a suppressed run must not extend the cooldown.
- Where Results shows `rule_inbox_interface`, the system shall put review, unknowns and next action ahead of hashes, preserve app and session selection on late replies, and work on desktop and mobile.
- The system shall return `proposal_only_result` as PROPOSE_ONLY for every operator or worker response. Recommendation evaluation never dispatches an action.

### Acceptance criteria (Gherkin)

```gherkin
Scenario: rule_inbox_retention
  Given an owned app and a verified saved rule version
  When the `rule_inbox_retention` path runs and the owner evaluates it twice against unchanged evidence and reopens the workspace
  Then one proposal and its rule and facts fingerprints survive

Scenario: rule_inbox_review
  Given a retained proposal from another app or owner
  When the `rule_inbox_review` path runs and a request tries to read or dismiss it
  Then the request is rejected without exposing the contents

Scenario: rule_schedule_consent
  Given an exact app, current owner role and an immutable saved version
  When the `rule_schedule_consent` path runs and the finite schedule is turned off, expires, exhausts its quota or loses its bound revision
  Then no further slot is evaluated or retained

Scenario: rule_schedule_receipt
  Given a due rule schedule and two worker polls
  When the `rule_schedule_receipt` path runs and a transaction is interrupted or both polls race
  Then the committed slot produces one receipt and advances only once

Scenario: rule_proposal_cooldown
  Given a saved proposal and a bounded cooldown
  When the `rule_proposal_cooldown` path runs and unchanged and changed facts are evaluated before the next eligible time
  Then unchanged facts never reopen the proposal and a suppressed run does not reset elapsed time

Scenario: rule_inbox_interface
  Given a narrow viewport and a saved recommendation
  When the `rule_inbox_interface` path runs and the owner opens Results
  Then the recommendation shows its reason and review action without horizontal overflow

Scenario: proposal_only_result
  Given an AUTO_WITHIN_GRANT rule that recommends an external action
  When the `proposal_only_result` path runs and the owner or the worker evaluates its saved version
  Then the action is retained as advice and no dispatch or provider request runs
```

## Bounds and decisions

AUTO_WITHIN_GRANT is an existing rule evaluation mode; it does not alter PROPOSE_ONLY inbox behavior.

One schedule per app, explicitly enabled for at most seven days, one to twenty-four hours between runs and at most thirty runs. Keep the exact rule version after newer versions are saved; no implicit upgrade. A missed schedule slot is caught up at most once per worker poll. Support positive bounded ISO duration hours, minutes, or days and an empty cooldown; old rules remain simulatable. No approval-to-execution transport in this feature.
