# Spec: surface-stopped-rule-schedules
Status: approved

## MUST - Functional core

### Requirements (EARS)

- When the saved rule schedule of an owned app blocks or its active app or owner revision changes, the system shall return one `rule_schedule_exception` with a fixed explanation and a Results recovery action.
- When a schedule is assigned to another principal, or is healthy, off, expired or exhausted, the system shall return exactly 0 items through `rule_exception_privacy` card for that schedule.
- When the current owner selects the recovered card, the system shall display `rule_exception_navigation` for the same app and open its saved recommendations. This action does not activate, extend, or change authorization.

### Acceptance criteria (Gherkin)

```gherkin
Scenario: rule_schedule_exception
  Given an owned schedule that blocks or has stale active authority
  When the `rule_schedule_exception` path runs in the weekly review
  Then the owner sees a plain-language reason and a supported next step even without campaign tables

Scenario: rule_exception_privacy
  Given a healthy, off, expired, exhausted, or foreign schedule
  When the `rule_exception_privacy` path runs
  Then no private rule exception is disclosed

Scenario: rule_exception_navigation
  Given a signed-in owner reviewing a retained exception on a narrow or wide screen
  When the `rule_exception_navigation` path runs and the current app or identity changes
  Then stale recovery is rejected or ignored and the schedule never changes
```

## Bounds

Use one app-scoped row and the existing Results recovery and signed-in portfolio routes. Healthy schedules continue silently. The privacy projection contains stable status and revision evidence only. Nothing changes an approval, issues credentials, or contacts a provider through this path.
