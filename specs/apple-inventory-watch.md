# Spec: apple-inventory-watch
Status: draft

## MUST - Functional core
### Description
Let an app owner schedule Apple report availability checks before a downloads report exists.

### Requirements (EARS)
- When an owner selects report availability and a cadence from 24 through 168 hours, the system shall save exactly one versioned read schedule for the connected app through `watch_enable`.
- When a report availability check is due, the system shall run only the existing Apple inventory read and retain current-source metadata through `watch_read`.
- When a current inventory reports no daily files, the system shall store the next due time without recording any download count through `watch_wait`.
- If the app, connection, schedule, or job lease changes before persistence, the system shall reject the stale inventory through `watch_guard`.
- When an owner opens Apple analytics before a report exists, the system shall return the availability option and the current refresh state through `watch_ui`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: watch_enable
  Given an app with one current Apple connection and no retained inventory
  When `watch_enable` saves the owner selection
  Then the app has a versioned schedule that dispatches only inventory reads
Scenario: watch_read
  Given an enabled app availability schedule whose cadence is due
  When `watch_read` completes the scheduled job
  Then the current app sees the saved inventory and another app sees none
Scenario: watch_wait
  Given a complete Apple inventory with no daily files
  When `watch_wait` reconciles the saved job after restart
  Then the schedule stays enabled without a numeric success or count
Scenario: watch_guard
  Given a scheduled read with an in-flight or expired lease
  When `watch_guard` checks a stale result
  Then the result cannot replace the current inventory
Scenario: watch_ui
  Given an owner with a saved Apple connection and no known downloads report
  When `watch_ui` displays the Apple analytics panel
  Then the schedule form offers report availability and states its effect before save
```

## SHOULD - Technical
- Reuse the existing queue, retry, pause and source binding. Preserve existing numeric schedules.
- Store availability as a reserved local selection that cannot be an Apple report identity.
- Keep report metadata separate from file downloads and campaign authority.

## Authorized parameters
MIN_INTERVAL_HOURS = 24
MAX_INTERVAL_HOURS = 168
