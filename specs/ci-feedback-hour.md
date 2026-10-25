# Spec: ci-feedback-hour
Status: implementation

## MUST - Functional core
### Description
Make feedback history fixtures independent of the wall-clock collection hour while retaining stale approval rejection.

### Requirements (EARS)
- The system shall return a fixed UTC collection time per feedback fixture through `history_clock` while preserving real artifact timestamps.
- When the collection hour changes, the system shall reject the old proposal without enqueuing and accept a newly reviewed proposal through `hour_reapproval`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: history_clock
  Given feedback history tests
  When `history_clock` fixes collection time within the fixture
  Then both history inspections complete across real wall-clock hours
Scenario: hour_reapproval
  Given a proposal read at 09:59:59 UTC
  When `hour_reapproval` advances collection time to 10:00:00 UTC
  Then the old proposal is rejected without a job and the newly read proposal queues one job
```

## WON'T - Out of scope
No production authority, retry, hash, collection-window, or CI test-selection changes.
