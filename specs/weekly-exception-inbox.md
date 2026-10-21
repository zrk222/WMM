# Spec: weekly-exception-inbox
Status: draft

## MUST — Functional core
### Description
Add one cross-app weekly exception review to the local Mission Control UI.
Reuse saved app evidence, authoritative pipeline evaluation, weekly decision
controls and existing action routes. Specialist measurement remains linked source
evidence. No new provider reads, approvals, spend or publication occurs in a review.

### Requirements (EARS)
- The system shall return an app-bound `exception_inbox` containing readiness, measurement, economics and retention exceptions from saved workspace evaluations.
- When one workspace evaluation fails, the system shall retain an `UNAVAILABLE` exception for that workspace and continue evaluating the other workspaces.
- The system shall display `source_receipt` fields with app identity, manifest version, source hash and observation time beside each exception.
- The system shall provide a `resolution_route` to the existing app-scoped tool and retain missing evidence as unknown instead of inventing a successful result.
- The system shall return `NO_EXECUTION_AUTHORITY` and false spending, scale and learning-pilot authority for the read-only inbox.
- The system shall render an accessible `weekly_review` at desktop1440x900 and mobile390x844 without horizontal overflow or JavaScript errors.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Cross-app exception review
  Given two apps with different missing evidence
  When the founder opens the `exception_inbox`
  Then each exception retains its own app identity and recovery action

Scenario: Source outage is visible
  Given one failed workspace and one readable workspace
  When the review is prepared
  Then the failed workspace shows `UNAVAILABLE`
  And the readable workspace still produces its exceptions

Scenario: Reproducible evidence
  Given a saved app and evidence version
  When an exception is displayed
  Then its `source_receipt` identifies the app, version, hash and observation time

Scenario: Direct recovery
  Given a missing retention cohort
  When the founder chooses its `resolution_route`
  Then the existing retained-value tool opens in the matching app
  And no missing value becomes zero or success

Scenario: Review does not authorize execution
  Given every local prerequisite is ready
  When the inbox is read
  Then the response reports `NO_EXECUTION_AUTHORITY`
  And spending, scale and learning-pilot authority remain false

Scenario: Device review
  Given viewports desktop1440x900 and mobile390x844
  When the founder uses the `weekly_review` with keyboard and pointer
  Then the controls have accessible names and visible focus
  And there is no horizontal overflow or JavaScript error
```

## SHOULD — Workflow and evidence boundaries
Show why each exception matters, what changed when an earlier receipt exists,
the next evidence-producing action, unknown costs and the responsible app.
Collapse routine local-ready checks into a dated expandable digest. Do not infer
that an alert is new without a prior observation. Keep critical findings ahead
of ordinary missing evidence. Do not silently cap the portfolio: if review is
bounded, expose pagination or coverage explicitly. App switching must finish
before opening a route; stale asynchronous responses must not open another app.

## SHOULD NOT — Unproven claims
Do not claim the three-minute or50-percent time-saving targets are achieved.
The founder usability benchmark, persisted snooze/reopen policy, experiment and
listing memory, write-adapter gates and live pilot remain required follow-on
scope. A read-only inbox does not complete F01-F04 or the original full goal.
