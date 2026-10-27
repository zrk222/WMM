# Spec: subscription-growth
Status: approved

## MUST — Functional core
### Description
Add source-grounded subscription decisions to the existing local growth workspace.
UPG-00 through UPG-06 remain separate implementation and proof packets.

### User roles
- Local founder reviewing app-scoped evidence.

### Requirements (EARS)
- The system shall return `journey_counts` for onboarding completion, paywall exposure, trial start, first payment and renewal using unique opaque subjects in one app and cohort.
- The system shall reject `journey_invalid` events with unsupported metadata versions, private subjects, invalid hashes or missing product and offer bindings.
- The system shall return `journey_maturity` as unavailable for missing stage denominators or immature cohorts without counting trial starts as purchases.
- The system shall retain `journey_history` hashes and duplicate identities across SQLite restart and workspace export and restore.
- The system shall reject `variant_invalid` experiments with changed configurations, stale sources or incompatible product eligibility without authorizing provider changes.
- The system shall return `aso_fields` with Apple name/subtitle 30 characters and keywords limited to 100 characters, while showing the UTF-8 byte count and explicitly identifying Apple's conflicting 100-byte reference; Google title 30 characters, short description 80 characters and full description 4000 characters, plus supported experiment surfaces.
- The system shall return `benchmark_scope` as incompatible when dataset period, metric denominator, currency or placement differs.
- The system shall store `customer_links` from proposed workflows to source observations with a maximum of 100 rows and explicit excluded features without certifying generated demand.
- The system shall return `review_status` with 3 distinct evidence states for local evidence, provider verification and outcomes, with 0 external writes.

### Data model
Data model: workflow outputs (journey_counts, journey_invalid, journey_maturity, journey_history, variant_invalid, aso_fields, benchmark_scope, customer_links, review_status)

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Journey accounting
  Given imported trial events
  When `journey_counts` are calculated
  Then trial starts do not increase first payment counts

Scenario: Invalid bindings
  Given unsupported metadata versions
  When `journey_invalid` events are imported
  Then the complete batch is rejected

Scenario: Unavailable conversion
  Given an immature cohort
  When `journey_maturity` is inspected
  Then conversion remains unavailable

Scenario: History restoration
  Given a saved event snapshot
  When `journey_history` is restored after restart
  Then hashes and duplicate identities remain unchanged

Scenario: Configuration changed
  Given changed product eligibility
  When `variant_invalid` is evaluated
  Then the experiment cannot yield a winning decision

Scenario: Store fields
  Given a platform-specific listing
  When `aso_fields` are inspected
  Then each field reports its documented limit and supported test surface

Scenario: Apple keyword byte limit
  Given an Apple keyword field with localized Unicode text
  When `aso_fields` counts the payload
  Then the 100-character limit and Apple 100-byte reference appear separately, and over-100-byte Unicode text requests the current locale counter instead of claiming provider acceptance

Scenario: Incompatible reference
  Given different benchmark currencies
  When `benchmark_scope` is compared
  Then comparison remains incompatible

Scenario: Customer trace
  Given a proposed workflow
  When `customer_links` are inspected
  Then source observations and feature exclusions remain explicit

Scenario: Founder review
  Given local fixture evidence
  When `review_status` is inspected
  Then provider verification and outcomes remain unverified
```

## SHOULD — Technical/structural
- Preserve legacy event JSON/CSV contracts and snapshot hashes.
- Reuse existing experiments, research, reporting and local review.
- Use isolated synthetic test data; forbid external writes and ad spending.

## Authorized parameters
Apple title/subtitle and Google title use 30 characters. Apple product-page
guidance lists 100 keyword characters while an App Store Connect reference lists
100 bytes; show both counts and ask for the locale counter when they differ. Both full
descriptions use 4000 characters, Apple promotional text 170, Google short text 80.
- LIMITS = 30
- LIMITS = 100
- LIMITS = 4000
- LIMITS = 170
- LIMITS = 80

## SHOULD NOT — Implementation details
- No live checkout, automatic winner deployment, provider mutation or growth promises.

## Decision logic (factory candidates)
<!-- Ordered business rules over extracted facts. specline handoff compiles
     these via HSF instead of letting agents improvise them. -->
| # | if | then |
|---|----|------|
