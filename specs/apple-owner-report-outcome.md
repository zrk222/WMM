# Spec: apple-owner-report-outcome
Status: draft

## MUST - Functional core
### Description
Carry Apple first-time download evidence into the existing private owner report. Keep delivery, missing data and attributed counts distinct.

### User roles
- A current owner capturing a private report or approving a finite private report plan.

### Requirements (EARS)
- When the current owner selects the exact approved UTC date window and an uppercase two-letter App Store storefront, the system shall read only the saved Apple App Downloads Detailed daily partitions for that app, current connection revision, exact campaign token and storefront through `apple_source`. The event window starts at 00:00 UTC and has an exclusive end at 00:00 UTC, spans 1 to 31 calendar days and cannot be widened from the approved plan.
- If the campaign lacks one verified Page post for the exact approved tag and dates, the system shall leave its campaign outcome unknown through `apple_delivery`. Another app, mismatched link, second post sharing the tag and missing or uncertain receipts do not establish delivery.
- When any selected event day has no saved file, no exact row or a selected partition processed less than two days after the event, the system shall retain row status and source dates, and leave the total unknown through `apple_coverage`. Only an explicit zero count is zero.
- When every selected day has a ready-to-review exact row and exact delivery is verified, the system shall return the sum of first-time download counts, storefront, coverage, processing dates, source fingerprints and delivery fingerprint through `apple_total`. The highest processing date replaces observations for the same event date. The report does not infer subscriptions, revenue or causal lift.
- When an Apple plan cannot produce a report metric, the system shall return one actionable reason in the private report through `apple_guidance`. Uncertain campaign effects and unresolved protective pause retain priority. Existing report capture, first-party outcome ingestion and finite report plans retain their current authority and private storage behavior.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: apple_source
  Given an approved Apple plan for Jan 1 through Jan 2 exclusive and saved US, CA and foreign-app rows
  When the current owner captures a report for the US storefront and Jan 1 through Jan 2 exclusive through `apple_source`
  Then results contain only the selected app and US exact-token Jan 1 row and its processing date
Scenario: apple_delivery
  Given a mature exact Apple observation and no verified post readback for its approved link
  When the current owner captures a private report through `apple_delivery`
  Then no campaign total is reported and the next action identifies the missing verified delivery
Scenario: apple_coverage
  Given two event dates with one explicit zero and one provisional or missing exact row
  When the current owner captures a private report through `apple_coverage`
  Then the explicit zero remains visible, the other day is distinguished, and the total is unknown
Scenario: apple_total
  Given one verified exact post, two mature exact rows of 0 and 5, and an earlier superseded Apple partition
  When the current owner captures a private report for the exact app, storefront and dates through `apple_total`
  Then the report retains two date observations totaling 5, both source fingerprints and the verified delivery fingerprint without claiming growth
Scenario: apple_guidance
  Given an Apple scope with unavailable Detailed data, and a non-Apple scope with an existing first-party receipt
  When the current owner captures their private reports through `apple_guidance`
  Then the Apple report explains the next tracking action and the non-Apple report retains its existing receipt without any provider request
```

## SHOULD - Technical
- Use the existing protected private owner report route and the same Apple retained-partition projection as the Apple Analytics panel.
- Keep storefront optional for legacy callers; without it, ask for the storefront instead of assuming a country. Add no new scheduler, provider reader, entitlement or publication route.
- Retain the existing report plan comparison, ownership, digest and repair boundaries. An Apple capture does not acquire or renew any publication authority.
