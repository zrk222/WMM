# Spec: workflow-telemetry
Status: draft

## MUST - Functional core
### Description
Show actual worker stage and step progression in a live app-scoped monitor.
Preserve the complete automation owner toggle and credential onboarding work.

### Requirements (EARS)
- The system shall store ordered job-attempt events for actual worker start, stage start, stage completion and terminal outcome through `actual_events`.
- The system shall reject progress emitted for a cancelled or replaced worker attempt through `attempt_binding`.
- The system shall return at most 100 recent selected-app job summaries and 200 events per job without exposing raw job input, result or credentials through `scoped_monitor`.
- The system shall display current stage, step, activity, event time, completion counts and stale connection state with a 2 second polling interval through `live_monitor`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: actual_events
  Given a queued local pipeline
  When `actual_events` execute its stages
  Then ordered stage events reflect actual execution and preserve blocked outcomes
Scenario: attempt_binding
  Given a cancelled or replaced worker lease
  When `attempt_binding` emits progress
  Then no event is accepted
Scenario: scoped_monitor
  Given two apps and private job payloads
  When `scoped_monitor` is read
  Then only selected-app public progress is returned
Scenario: live_monitor
  Given an active workflow and a failed status request
  When `live_monitor` refreshes
  Then current stage activity is visible and failed refresh is labeled stale
```

## SHOULD - Technical
- Use durable SQLite event rows linked to actual jobs. Fixed event codes and
  application-authored descriptions exclude model text, keys and raw errors.
- Pipeline stage callbacks run before/after actual packet preparation. Completion
  counts are processed stages, not an estimate of time or business success.
- Shared monitor UI appears on workflow, agents and activity views. Poll only
  while mounted, discard responses after app changes, preserve keyboard focus,
  stop on hidden pages and display failure/retry without erasing saved progress.
- Existing local trusted-session reads apply; monitoring grants no execution
  authority. Publication, spend, full provider telemetry and owner switch remain
  separate parent requirements.

## Authorized parameters
MAX_JOBS = 100
MAX_EVENTS = 200
POLL_MS = 2000
