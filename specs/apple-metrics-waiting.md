# Spec: apple-metrics-waiting
Status: draft

## MUST - Functional core
### Description
Preserve an enabled Apple downloads refresh when a complete current source inventory has no daily instance.

### Requirements (EARS)
- When the selected complete report contains no daily instance, the system shall return a source-bound unknown observation through `waiting_read`.
- When a verified waiting observation completes, the system shall retain the schedule cadence and reject numeric success through `waiting_schedule`.
- If the source or observation identity changes, the system shall reject the waiting result through `source_guard`.
- When a provider read or coverage check fails, the system shall reject the read and retain at most 3 attempts through `failure_limits`.
- When a saved waiting job is reconciled, the system shall store the same waiting classification through `waiting_reconcile`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: waiting_read
  Given a complete current downloads report without a daily instance
  When `waiting_read` completes
  Then the result records unknown metrics and no downloaded partitions
Scenario: waiting_schedule
  Given an enabled daily schedule and a verified empty report
  When `waiting_schedule` completes repeatedly
  Then the schedule stays enabled without recording numeric success
Scenario: source_guard
  Given the source changes during a read
  When `source_guard` checks completion
  Then the waiting result is rejected
Scenario: failure_limits
  Given a partial or failed provider read
  When `failure_limits` processes the failure
  Then existing retry and blocking rules remain enforced
Scenario: waiting_reconcile
  Given a saved waiting result for the current schedule
  When `waiting_reconcile` runs after restart
  Then the result stays waiting and cannot become numeric success
```

## SHOULD - Technical
- Use the existing atomic prepared-result persistence path with no metric partitions.
- Preserve any earlier real numeric success and reject malformed or foreign waiting metadata.
- Use synthetic test data and no provider credentials.

## Authorized parameters
INTERVAL_HOURS = 24
MAX_FAILURES = 3
