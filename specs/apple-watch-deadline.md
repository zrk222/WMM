# Spec: apple-watch-deadline
Status: draft

## MUST - Functional core
### Description
Let the owner set a hard stop on the Apple analytics refresh schedule for one app.

### Requirements (EARS)
- When `watch_window` receives an owner-approved enabled schedule with a stop_at field, the system shall store the exact UTC deadline after the first scheduled check and at most 7 days after save.
- When `watch_stop` reaches the deadline, the system shall stop queuing reads, cancel the unclaimed queued read, and reject a claimed read before provider access or persistence.
- When `watch_status` displays a bounded refresh schedule, the system shall show the deadline in local time and indicate that the check window ended.
- When `watch_legacy` encounters a schedule without a deadline, the system shall preserve the existing open-ended cadence. A schema upgrade shall leave existing schedules without a deadline.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: watch_window
  Given the owner saves a deadline
  When `watch_window` compares the deadline against the first check and the 7-day bound
  Then the schedule stores valid input and rejects a deadline at or before the first check or beyond the bound
Scenario: watch_stop
  Given a bounded Apple check has reached its deadline
  When `watch_stop` runs after restarting the scheduler
  Then no new job is created, an unclaimed queued read is cancelled, and a claimed read is denied
Scenario: watch_status
  Given a saved schedule with a deadline
  When `watch_status` renders the owner form
  Then the owner can read the stop time and see that the check window ended
Scenario: watch_legacy
  Given an existing schedule without a deadline
  When `watch_legacy` applies the schema upgrade
  Then the schedule retains its original cadence and next due time
```

## SHOULD - Technical
- Reuse the authenticated owner endpoint and the existing worker, source checks and receipts.
- Keep inventory checks read only. Provider files, counts and publication require their own existing flows.

## Authorized parameters
MAX_SCHEDULE_WINDOW_SECONDS = 604800
