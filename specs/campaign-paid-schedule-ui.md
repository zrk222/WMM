# Spec: campaign-paid-schedule-ui
Status: draft

## MUST - Functional core
### Description
Let an owner review and schedule an exact existing verified Page post promotion within a saved active paid campaign scope.

### Requirements (EARS)
- The system shall reject a paid scheduling request without an active paid scope and a saved same-scope verified Page post through `verified_post`.
- The system shall reject a paid schedule outside the approved targeting, budget or expiry through `bounded_review`.
- When an owner reviews a paid schedule, the system shall show the exact post ID, countries, budget, due time, end time and approval hash through `exact_review`.
- If the app, owner, modal or version changes during a request, the system shall reject stale follow-up actions through `stale_guard`.
- When schedule progress is displayed, the system shall show effective state, saved provider IDs and retained commitment through `progress_report`.
- The system shall return a saved schedule report without creative copy or rights prose through `report_privacy`.

- When the progress dialog stays visible, the system shall refresh saved receipt stages with one bounded in-flight read and discard stale app, owner, version or closed-dialog responses through `live_saved_progress`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: verified_post
  Given no verified post in an active paid scope
  When `verified_post` opens scheduling
  Then the system rejects the request before preparation
Scenario: bounded_review
  Given countries or budget outside the saved paid scope
  When `bounded_review` prepares a schedule
  Then the system rejects the request
Scenario: exact_review
  Given a valid paid schedule
  When `exact_review` presents the batch
  Then the exact post, countries, budget, dates and approval hash are visible
Scenario: stale_guard
  Given an owner changes app or closes the modal during preparation
  When `stale_guard` resumes
  Then no stale approval screen or follow-up request is issued
Scenario: progress_report
  Given a saved paid intent with provider IDs and retained commitment
  When `progress_report` displays the batch
  Then the saved state and commitment are shown without claiming app outcomes
Scenario: report_privacy
  Given a saved campaign batch containing creative text
  When `report_privacy` creates a report
  Then creative text and rights prose are omitted
Scenario: live_saved_progress
  Given a visible scheduled progress dialog
  When `live_saved_progress` reads its current saved receipt
  Then the execution stage updates without resetting focus or repeating an effect
```

## SHOULD - Technical
- Reuse the existing schedule endpoints and campaign scope authority.
- The worker must remain running and the scope retains its existing 24-hour expiry.
- No live Meta effects are part of this verification.

## Authorized parameters
MAX_ITEMS = 20
MAX_HOURS = 24
MAX_CAMPAIGN_MINOR = 100000000

Existing scope builder uses max_calls = 500. Synthetic saved scope fixtures use:
max_calls = 500
max_campaign_minor = 100
max_total_minor = 100

timeout = 12000
